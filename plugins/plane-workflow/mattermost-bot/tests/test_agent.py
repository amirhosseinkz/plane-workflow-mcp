from __future__ import annotations

from types import SimpleNamespace
import tempfile
import unittest
from pathlib import Path

from agent import PlaneBotAgent
from codex_router import CodexDecision
from drafts import DraftStore
from workflow_adapter import ToolExecution, WorkflowAdapterError


class _Workflow:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, object]]] = []
        self.tools: list[dict[str, object]] = []

    def execute_confirmed(self, name: str, arguments: dict[str, object]) -> dict[str, object]:
        self.calls.append((name, arguments))
        return {"status": "created", "work_item": {"name": "Improve player"}}


class _Attachments:
    def upload(self, **arguments: object) -> dict[str, object]:
        return {"status": "attached", "arguments": arguments}


class _UncertainWorkflow:
    def execute_confirmed(self, name: str, arguments: dict[str, object]) -> dict[str, object]:
        raise WorkflowAdapterError("Plane did not confirm the update")


class _PreviewWorkflow:
    def __init__(self) -> None:
        self.tools = []
        self.calls: list[tuple[str, dict[str, object], bool]] = []

    def execute(self, name: str, arguments: dict[str, object], *, preview: bool) -> ToolExecution:
        self.calls.append((name, arguments, preview))
        return ToolExecution(
            name=name,
            result={"status": "preview", "name": arguments["outcome"]},
            requires_confirmation=True,
            arguments=arguments,
        )


class _ModuleWorkflow:
    def __init__(self) -> None:
        self.tools = []
        self.calls: list[tuple[str, dict[str, object], bool]] = []

    def execute(self, name: str, arguments: dict[str, object], *, preview: bool) -> ToolExecution:
        self.calls.append((name, arguments, preview))
        return ToolExecution(
            name=name,
            result={"status": "preview", "module": {"name": arguments["module_name"]}},
            requires_confirmation=True,
            arguments=arguments,
        )


class _RejectedModuleWorkflow:
    def execute(self, name: str, arguments: dict[str, object], *, preview: bool) -> ToolExecution:
        raise WorkflowAdapterError("The configured Plane project does not allow that module.")


class _Router:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    def route(self, **arguments: object) -> CodexDecision:
        self.calls.append(arguments)
        return CodexDecision(
            action="create_standard_work_item",
            arguments={
                "outcome": "Improve player quality selection",
                "acceptance_criteria": ["A viewer can choose a quality"],
            },
            message="",
        )

    def diagnose(self) -> None:
        return None


class AgentConfirmationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.store = DraftStore(Path(self.temporary_directory.name) / "drafts.sqlite3")
        self.workflow = _Workflow()
        self.agent = PlaneBotAgent(
            SimpleNamespace(
                codex_command="codex",
                codex_timeout_seconds=30,
                draft_ttl_minutes=15,
                plane_project_identifier="EXAMPLE",
                data_dir=Path(self.temporary_directory.name),
            ),
            self.workflow,
            self.store,
            _Attachments(),
        )

    def tearDown(self) -> None:
        self.store.close()
        self.temporary_directory.cleanup()

    def test_confirmation_executes_once(self) -> None:
        draft = self.store.create(
            requester_id="user-1",
            action="create_standard_work_item",
            arguments={"outcome": "Improve player"},
            preview={"status": "preview"},
            ttl_minutes=15,
        )

        reply = self.agent.handle(requester_id="user-1", message=f"confirm {draft.draft_id}")

        self.assertIn("Applied draft", reply)
        self.assertEqual(len(self.workflow.calls), 1)
        duplicate_reply = self.agent.handle(requester_id="user-1", message=f"confirm {draft.draft_id}")
        self.assertIn("already been applied", duplicate_reply)
        self.assertEqual(len(self.workflow.calls), 1)

    def test_uncertain_confirmation_is_locked_for_review(self) -> None:
        draft = self.store.create(
            requester_id="user-1",
            action="update_standard_work_item",
            arguments={"work_item_id": "work-item-1", "priority": "high"},
            preview={"status": "preview"},
            ttl_minutes=15,
        )
        self.agent.workflow = _UncertainWorkflow()

        reply = self.agent.handle(requester_id="user-1", message=f"confirm {draft.draft_id}")

        self.assertIn("locked for review", reply)
        retry = self.agent.handle(requester_id="user-1", message=f"confirm {draft.draft_id}")
        self.assertIn("manual Plane review", retry)

    def test_language_request_creates_a_confirmation_draft(self) -> None:
        workflow = _PreviewWorkflow()
        self.agent.workflow = workflow
        self.agent.router = _Router()

        reply = self.agent.handle(requester_id="user-1", message="Create a task for quality selection")

        self.assertIn("Draft", reply)
        self.assertEqual(len(workflow.calls), 1)
        self.assertTrue(workflow.calls[0][2])
        self.assertEqual(len(self.agent.router.calls), 1)

    def test_module_request_creates_a_draft_without_routing(self) -> None:
        workflow = _ModuleWorkflow()
        self.agent.workflow = workflow

        reply = self.agent.handle(requester_id="user-1", message="Create a new module called App Monitoring")

        self.assertIn("Draft", reply)
        self.assertEqual(workflow.calls, [("ensure_module", {"module_name": "App Monitoring", "create_if_missing": True}, True)])

    def test_module_request_returns_a_safe_plane_error(self) -> None:
        self.agent.workflow = _RejectedModuleWorkflow()

        reply = self.agent.handle(requester_id="user-1", message="Create a module called App Monitoring")

        self.assertIn("does not allow", reply)
