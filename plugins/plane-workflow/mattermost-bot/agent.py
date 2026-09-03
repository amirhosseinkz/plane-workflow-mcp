"""Natural-language routing and confirmation handling for the Mattermost bot."""

from __future__ import annotations

import json
import re
from typing import Any

from attachments import AttachmentService
from codex_router import CodexRouter, CodexRouterError
from config import BotConfig
from drafts import DraftError, DraftStore
from workflow_adapter import ToolExecution, WorkflowAdapter, WorkflowAdapterError


CONFIRM_PATTERN = re.compile(r"^\s*confirm\s+([a-z0-9_-]+)\s*$", re.IGNORECASE)
CANCEL_PATTERN = re.compile(r"^\s*cancel\s+([a-z0-9_-]+)\s*$", re.IGNORECASE)
MODULE_REQUEST_PATTERN = re.compile(
    r"^\s*(?:create|add|make)\s+(?:a\s+)?(?:new\s+)?module(?:\s+(?:called|named))?\s+(?P<name>.+?)\s*[.!]?\s*$",
    re.IGNORECASE,
)


ATTACHMENT_TOOL = {
    "type": "function",
    "name": "attach_uploaded_file",
    "description": "Draft attaching one file uploaded to the current Mattermost message to an existing Plane work item.",
    "parameters": {
        "type": "object",
        "properties": {
            "work_item_id": {"type": "string", "description": "Work-item UUID."},
            "file_id": {"type": "string", "description": "One of the file IDs attached to the current message."},
            "max_size_mb": {"type": "integer", "minimum": 1, "maximum": 100},
        },
        "required": ["work_item_id", "file_id"],
        "additionalProperties": False,
    },
}


class PlaneBotAgent:
    def __init__(self, config: BotConfig, workflow: WorkflowAdapter, drafts: DraftStore, attachments: AttachmentService) -> None:
        self.config = config
        self.workflow = workflow
        self.drafts = drafts
        self.attachments = attachments
        self.router = CodexRouter(config, [*workflow.tools, ATTACHMENT_TOOL])

    def diagnose_backend(self) -> None:
        self.router.diagnose()

    def handle(self, *, requester_id: str, message: str, file_ids: tuple[str, ...] = ()) -> str:
        text = message.strip()
        if match := CONFIRM_PATTERN.fullmatch(text):
            return self._confirm(match.group(1), requester_id)
        if match := CANCEL_PATTERN.fullmatch(text):
            return self._cancel(match.group(1), requester_id)
        if text.casefold() in {"help", "?", "start"}:
            return self._help_text()
        if direct_reply := self._try_direct_request(requester_id=requester_id, message=text):
            return direct_reply
        if not text and not file_ids:
            return self._help_text()
        try:
            return self._route_with_codex(requester_id=requester_id, message=text, file_ids=file_ids)
        except CodexRouterError as error:
            return str(error)

    def _try_direct_request(self, *, requester_id: str, message: str) -> str | None:
        match = MODULE_REQUEST_PATTERN.fullmatch(message)
        if not match:
            return None
        module_name = match.group("name").strip().rstrip(".!?")
        if not module_name:
            return "Please tell me the name of the new module."
        try:
            execution = self.workflow.execute(
                "ensure_module",
                {"module_name": module_name, "create_if_missing": True},
                preview=True,
            )
        except WorkflowAdapterError as error:
            return str(error)
        return self._render_execution(requester_id, execution)

    def _route_with_codex(self, *, requester_id: str, message: str, file_ids: tuple[str, ...]) -> str:
        tool_results: list[dict[str, Any]] = []
        for _ in range(3):
            decision = self.router.route(message=message, file_ids=file_ids, tool_results=tool_results)
            if decision.action is None:
                if decision.message:
                    return decision.message
                if tool_results:
                    return self._format_result(tool_results[-1]["result"])
                return "I could not determine a safe Plane action from that message."
            try:
                execution = self._execute_preview(decision.action, decision.arguments, file_ids)
            except WorkflowAdapterError as error:
                return str(error)
            if execution.requires_confirmation:
                return self._render_execution(requester_id, execution)
            tool_results.append({"action": execution.name, "result": execution.result})
        if tool_results:
            return self._format_result(tool_results[-1]["result"])
        return "I could not determine a safe Plane action from that message."

    def _render_execution(self, requester_id: str, execution: ToolExecution) -> str:
        if not execution.requires_confirmation:
            return self._format_result(execution.result)
        draft = self.drafts.create(
            requester_id=requester_id,
            action=execution.name,
            arguments=execution.arguments,
            preview=execution.result,
            ttl_minutes=self.config.draft_ttl_minutes,
        )
        return self._format_draft(draft.draft_id, execution)

    def _confirm(self, draft_id: str, requester_id: str) -> str:
        try:
            draft = self.drafts.begin_execution(draft_id, requester_id)
        except DraftError as error:
            return str(error)
        try:
            result = (
                self.attachments.upload(**draft.arguments)
                if draft.action == "upload_mattermost_attachment"
                else self.workflow.execute_confirmed(draft.action, draft.arguments)
            )
            self.drafts.mark_completed(draft_id, requester_id)
        except WorkflowAdapterError as error:
            self.drafts.mark_requires_review(draft_id, requester_id)
            return (
                f"I could not verify the result of draft `{draft_id}`: {error}\n\n"
                "To avoid applying the change twice, this draft is now locked for review. Check Plane, then request a fresh draft if needed."
            )
        except Exception:
            self.drafts.mark_requires_review(draft_id, requester_id)
            return (
                f"I could not verify the result of draft `{draft_id}`.\n\n"
                "To avoid applying the change twice, this draft is now locked for review. Check Plane, then request a fresh draft if needed."
            )
        return f"**Applied draft `{draft_id}`**\n{self._format_result(result)}"

    def _cancel(self, draft_id: str, requester_id: str) -> str:
        try:
            self.drafts.cancel(draft_id, requester_id)
        except DraftError as error:
            return str(error)
        return f"Draft `{draft_id}` was cancelled. No Plane data was changed."

    def _execute_preview(self, name: str, arguments: dict[str, Any], file_ids: tuple[str, ...]) -> ToolExecution:
        if name != "attach_uploaded_file":
            return self.workflow.execute(name, arguments, preview=True)
        file_id = str(arguments.get("file_id") or "")
        work_item_id = str(arguments.get("work_item_id") or "")
        if not file_id or not work_item_id:
            raise WorkflowAdapterError("A work_item_id and file_id are required to attach a Mattermost file.")
        if file_id not in file_ids:
            raise WorkflowAdapterError("The requested file was not attached to this Mattermost message.")
        max_size_mb = int(arguments.get("max_size_mb", 25))
        preview = self.attachments.preview(work_item_id=work_item_id, file_id=file_id, max_size_mb=max_size_mb)
        return ToolExecution(
            name="upload_mattermost_attachment",
            result=preview,
            requires_confirmation=True,
            arguments={"work_item_id": work_item_id, "file_id": file_id, "max_size_mb": max_size_mb},
        )

    def _format_draft(self, draft_id: str, execution: ToolExecution) -> str:
        return (
            f"**Draft `{draft_id}`**\n{self._format_result(execution.result)}\n\n"
            f"Reply `confirm {draft_id}` to apply it, or `cancel {draft_id}` to discard it. "
            f"This draft expires in {self.config.draft_ttl_minutes} minutes."
        )

    @staticmethod
    def _format_result(result: dict[str, Any]) -> str:
        status = result.get("status")
        if status == "duplicate_detected":
            duplicate = result.get("duplicate", {})
            return f"A matching task already exists: **{duplicate.get('name', 'Unknown')}**. No new task was drafted."
        if status == "similarity_review_required":
            candidates = result.get("candidates", [])
            lines = [f"- {candidate.get('work_item', {}).get('name', 'Unknown')}" for candidate in candidates[:5] if isinstance(candidate, dict)]
            return "Similar tasks need review before creating another one:\n" + "\n".join(lines)
        rendered = json.dumps(result, ensure_ascii=False, indent=2, default=str)
        if len(rendered) > 5500:
            rendered = rendered[:5500] + "\n..."
        return f"```json\n{rendered}\n```"

    @staticmethod
    def _help_text() -> str:
        return (
            "Tell me what you need in Plane, for example:\n"
            "- `Create a bug for the media player: quality selection is missing.`\n"
            "- `Create a module called Observability.`\n"
            "- `Audit the current project backlog.`\n"
            "- `Show me what needs attention in this project.`\n"
            "- `Mark EXAMPLE-4 as blocked by EXAMPLE-2.`\n"
            "- `Find EXAMPLE-4 and change its priority to high.`\n"
            "I will show a draft before changing Plane."
        )
