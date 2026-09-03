from __future__ import annotations

from types import SimpleNamespace
import unittest
from unittest.mock import patch

import workflow_adapter
from workflow_adapter import WorkflowAdapter, WorkflowAdapterError


class _PlaneResponse:
    ok = True
    content = b"{}"

    @staticmethod
    def json() -> dict[str, object]:
        return {}


class _PlaneSession:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str, object, object, int]] = []

    def request(self, method: str, url: str, *, params: object, json: object, timeout: int) -> _PlaneResponse:
        self.calls.append((method, url, params, json, timeout))
        return _PlaneResponse()


class _ModuleApi:
    def __init__(self) -> None:
        self.payload: dict[str, object] | None = None

    @staticmethod
    def modules(project_id: str) -> list[dict[str, object]]:
        return []

    def create_module(self, project_id: str, payload: dict[str, object]) -> dict[str, object]:
        self.payload = payload
        return {"id": "module-id", "name": payload["name"]}


class WorkflowAdapterTests(unittest.TestCase):
    def setUp(self) -> None:
        self.adapter = WorkflowAdapter(SimpleNamespace(plane_project_id="example-project"))

    def test_read_action_is_bound_to_the_configured_project(self) -> None:
        captured: dict[str, object] = {}

        def find_work_items(**arguments: object) -> dict[str, object]:
            captured.update(arguments)
            return {"status": "ok"}

        with patch.object(workflow_adapter.workflow, "find_work_items", find_work_items):
            result = self.adapter.execute("find_work_items", {"query": "EXAMPLE-4"})

        self.assertEqual(captured, {"project_id": "example-project", "query": "EXAMPLE-4"})
        self.assertFalse(result.requires_confirmation)

    def test_write_action_is_previewed_before_confirmation(self) -> None:
        captured: dict[str, object] = {}

        def create_standard_work_item(**arguments: object) -> dict[str, object]:
            captured.update(arguments)
            return {"status": "preview"}

        with patch.object(workflow_adapter.workflow, "create_standard_work_item", create_standard_work_item):
            result = self.adapter.execute(
                "create_standard_work_item",
                {"outcome": "Improve player", "acceptance_criteria": ["A user can choose quality"]},
            )

        self.assertEqual(captured["project_id"], "example-project")
        self.assertTrue(captured["dry_run"])
        self.assertTrue(result.requires_confirmation)
        self.assertNotIn("project_id", result.arguments)
        self.assertNotIn("dry_run", result.arguments)

    def test_lifecycle_actions_are_previewed_before_confirmation(self) -> None:
        captured: list[tuple[str, dict[str, object]]] = []

        def start_standard_work_item(**arguments: object) -> dict[str, object]:
            captured.append(("start", arguments))
            return {"status": "preview"}

        def complete_standard_work_item(**arguments: object) -> dict[str, object]:
            captured.append(("complete", arguments))
            return {"status": "preview"}

        with patch.object(workflow_adapter.workflow, "start_standard_work_item", start_standard_work_item), patch.object(
            workflow_adapter.workflow, "complete_standard_work_item", complete_standard_work_item
        ):
            start = self.adapter.execute("start_standard_work_item", {"work_item_id": "item-id"})
            complete = self.adapter.execute(
                "complete_standard_work_item",
                {"work_item_id": "item-id", "summary": "Finished", "verification": ["Tests pass"]},
            )

        self.assertTrue(start.requires_confirmation)
        self.assertTrue(complete.requires_confirmation)
        self.assertTrue(captured[0][1]["dry_run"])
        self.assertTrue(captured[1][1]["dry_run"])

    def test_v05_actions_are_project_bound_and_writes_are_previewed(self) -> None:
        captured: list[tuple[str, dict[str, object]]] = []

        def get_project_briefing(**arguments: object) -> dict[str, object]:
            captured.append(("briefing", arguments))
            return {"status": "briefing"}

        def add_work_item_relation(**arguments: object) -> dict[str, object]:
            captured.append(("relation", arguments))
            return {"status": "preview"}

        def cancel_standard_work_item(**arguments: object) -> dict[str, object]:
            captured.append(("cancel", arguments))
            return {"status": "preview"}

        with patch.object(workflow_adapter.workflow, "get_project_briefing", get_project_briefing), patch.object(
            workflow_adapter.workflow, "add_work_item_relation", add_work_item_relation
        ), patch.object(workflow_adapter.workflow, "cancel_standard_work_item", cancel_standard_work_item):
            briefing = self.adapter.execute("get_project_briefing", {})
            relation = self.adapter.execute(
                "add_work_item_relation",
                {"work_item_id": "item-id", "relation_type": "blocked_by", "related_work_item_ids": ["blocker-id"]},
            )
            cancellation = self.adapter.execute(
                "cancel_standard_work_item", {"work_item_id": "item-id", "reason": "Superseded"}
            )

        self.assertFalse(briefing.requires_confirmation)
        self.assertTrue(relation.requires_confirmation)
        self.assertTrue(cancellation.requires_confirmation)
        self.assertEqual(captured[0][1]["project_id"], "example-project")
        self.assertTrue(captured[1][1]["confirm"] is False)
        self.assertTrue(captured[2][1]["dry_run"])

    def test_unknown_action_is_rejected(self) -> None:
        with self.assertRaisesRegex(WorkflowAdapterError, "not available"):
            self.adapter.execute("delete_everything", {})

    def test_plane_api_uses_trailing_slashes_for_write_routes(self) -> None:
        settings = workflow_adapter.workflow.PlaneSettings(
            base_url="https://tasks.example.test",
            api_key="test-key",
            workspace="workspace",
        )
        api = workflow_adapter.workflow.PlaneApi(settings)
        session = _PlaneSession()
        api.session = session

        api.create_module("project-id", {"name": "Monitoring", "status": "backlog"})
        api.create_work_item_comment("project-id", "item-id", {"comment_html": "<p>Done</p>"})

        self.assertEqual(
            session.calls[0][1],
            "https://tasks.example.test/api/v1/workspaces/workspace/projects/project-id/modules/",
        )
        self.assertEqual(
            session.calls[1][1],
            "https://tasks.example.test/api/v1/workspaces/workspace/projects/project-id/work-items/item-id/comments/",
        )

    def test_module_creation_omits_empty_optional_fields(self) -> None:
        api = _ModuleApi()

        result = workflow_adapter.workflow._module(
            api,
            "project-id",
            "Monitoring",
            allow_create=True,
            description=None,
        )

        self.assertEqual(result, {"id": "module-id", "name": "Monitoring"})
        self.assertEqual(api.payload, {"name": "Monitoring", "status": "backlog"})
