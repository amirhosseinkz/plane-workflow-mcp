"""Shared Plane Workflow adapter for Mattermost conversations."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

# Provided by the declared editable ``plane-workflow-mcp`` dependency.
import server as workflow

from config import BotConfig


class WorkflowAdapterError(RuntimeError):
    """Raised for an action the bot can safely explain to a user."""


@dataclass(frozen=True)
class ToolExecution:
    name: str
    result: dict[str, Any]
    requires_confirmation: bool
    arguments: dict[str, Any]


def _string(description: str) -> dict[str, Any]:
    return {"type": "string", "description": description}


def _string_list(description: str) -> dict[str, Any]:
    return {"type": "array", "items": {"type": "string"}, "description": description}


def _object(description: str, properties: dict[str, Any], required: list[str] | None = None) -> dict[str, Any]:
    schema: dict[str, Any] = {"type": "object", "description": description, "properties": properties, "additionalProperties": False}
    if required:
        schema["required"] = required
    return schema


def _function(name: str, description: str, parameters: dict[str, Any]) -> dict[str, Any]:
    return {"type": "function", "name": name, "description": description, "parameters": parameters}


WORKFLOW_TOOLS: list[dict[str, Any]] = [
    _function("diagnose_plane_connection", "Check the bot's Plane connection and supported capabilities.", _object("No arguments.", {})),
    _function("get_project_workflow_context", "Read the project modules, labels, profile, and work-item count.", _object("No arguments.", {})),
    _function("get_project_workflow_profile", "Read the active profile and local project workflow settings.", _object("No arguments.", {})),
    _function("get_workflow_options", "Read available states, cycles, assignees, and related planning options.", _object("No arguments.", {})),
    _function("find_work_items", "Find work items by title, UUID, or reference such as EXAMPLE-4.", _object("Search arguments.", {"query": _string("Task title, UUID, or Plane reference."), "max_results": {"type": "integer", "minimum": 1, "maximum": 20}}, ["query"])),
    _function("find_duplicate_candidates", "Find likely duplicate work items for a proposed title.", _object("Search arguments.", {"title": _string("Proposed task title."), "min_score": {"type": "number", "minimum": 0, "maximum": 1}}, ["title"])),
    _function("audit_work_items", "Run a read-only quality and structure audit of the Plane project.", _object("No arguments.", {})),
    _function("create_standardization_plan", "Prepare a saved, reviewable cleanup plan without changing Plane.", _object("Plan options.", {"expires_in_hours": {"type": "integer", "minimum": 1, "maximum": 168}})),
    _function("get_standardization_plan", "Read a saved cleanup plan.", _object("Plan lookup.", {"plan_id": _string("Saved cleanup-plan ID.")}, ["plan_id"])),
    _function("apply_standardization_plan", "Preview a saved cleanup plan. Applying it will always require confirmation.", _object("Plan selection.", {"plan_id": _string("Saved cleanup-plan ID.")}, ["plan_id"])),
    _function("create_standard_work_item", "Draft a structured Plane task. Use a type label, clear outcome, and observable acceptance criteria.", _object("New task details.", {
        "outcome": _string("Clear user-visible outcome."),
        "acceptance_criteria": _string_list("Observable conditions that prove the task is complete."),
        "work_item_type": {"type": "string", "enum": ["bug", "improvement", "task"]},
        "context": _string("Optional product or platform context."),
        "module_name": _string("Existing module unless the user explicitly requests a new one."),
        "surface": _string("Screen, flow, component, or scope."),
        "scope": _string("Affected area and constraints."),
        "priority": {"type": "string", "enum": ["urgent", "high", "medium", "low", "none"]},
        "current_behavior": _string("Required for a bug: what happens now."),
        "expected_behavior": _string("Required for a bug: what should happen."),
        "additional_labels": _string_list("Existing non-type label names to keep."),
        "allow_create_module": {"type": "boolean", "description": "True only when the user explicitly asks to create a new module."},
        "assignee_ids": _string_list("Known assignee IDs from get_workflow_options."),
        "state_id": _string("Known state ID from get_workflow_options."),
        "estimate": {"oneOf": [{"type": "integer", "minimum": 0}, {"type": "string"}]},
        "start_date": _string("YYYY-MM-DD."),
        "target_date": _string("YYYY-MM-DD."),
        "cycle_id": _string("Known cycle ID from get_workflow_options."),
    }, ["outcome", "acceptance_criteria"])),
    _function("update_standard_work_item", "Draft an update for one known Plane work item. Look it up first when only a title or reference is known.", _object("Update details.", {
        "work_item_id": _string("Work-item UUID returned by find_work_items."),
        "outcome": _string("New clear outcome/title."),
        "acceptance_criteria": _string_list("Required when replacing the description."),
        "work_item_type": {"type": "string", "enum": ["bug", "improvement", "task"]},
        "context": _string("Optional title context."),
        "module_name": _string("Existing module name."),
        "surface": _string("Screen, flow, component, or scope."),
        "scope": _string("Affected area and constraints."),
        "priority": {"type": "string", "enum": ["urgent", "high", "medium", "low", "none"]},
        "current_behavior": _string("Required for a bug description replacement."),
        "expected_behavior": _string("Required for a bug description replacement."),
        "additional_labels": _string_list("Existing label names to add."),
        "replace_description": {"type": "boolean"},
        "allow_create_module": {"type": "boolean", "description": "True only when explicitly requested."},
        "assignee_ids": _string_list("Known assignee IDs from get_workflow_options. An empty list clears assignees."),
        "state_id": _string("Known state ID."),
        "estimate": {"oneOf": [{"type": "integer", "minimum": 0}, {"type": "string"}]},
        "start_date": _string("YYYY-MM-DD."),
        "target_date": _string("YYYY-MM-DD."),
        "cycle_id": _string("Known cycle ID."),
    }, ["work_item_id"])),
    _function("ensure_module", "Draft a module creation or work-item assignment.", _object("Module details.", {
        "module_name": _string("Module name."),
        "work_item_ids": _string_list("Work-item UUIDs to assign."),
        "description": _string("Module description when creating a new module."),
        "create_if_missing": {"type": "boolean", "description": "True only when the user explicitly requests module creation."},
    }, ["module_name"])),
    _function("validate_workflow_profile", "Validate a profile override without saving it.", _object("Profile to validate.", {"profile": {"type": "object", "additionalProperties": True}}, ["profile"])),
    _function("save_project_workflow_profile", "Preview a project workflow-profile change. Saving always requires confirmation.", _object("Profile override.", {
        "profile": {"type": "object", "additionalProperties": True},
        "replace_existing": {"type": "boolean"},
    }, ["profile"])),
    _function("add_work_item_evidence_links", "Draft evidence links for a work item. Attachment happens only after confirmation.", _object("Evidence details.", {
        "work_item_id": _string("Work-item UUID."),
        "evidence": {"type": "array", "items": {"type": "object", "properties": {"url": _string("Absolute http or https URL."), "title": _string("Optional descriptive title.")}, "required": ["url"], "additionalProperties": False}},
        "note": _string("Optional evidence note to append to the description."),
    }, ["work_item_id", "evidence"])),
]


PROJECT_BOUND_ACTIONS = {
    "diagnose_plane_connection",
    "get_project_workflow_context",
    "get_project_workflow_profile",
    "get_workflow_options",
    "find_work_items",
    "find_duplicate_candidates",
    "audit_work_items",
    "create_standardization_plan",
    "create_standard_work_item",
    "update_standard_work_item",
    "ensure_module",
    "save_project_workflow_profile",
    "add_work_item_evidence_links",
    "upload_work_item_attachment",
}

WRITE_ACTIONS = {
    "apply_standardization_plan",
    "create_standard_work_item",
    "update_standard_work_item",
    "ensure_module",
    "save_project_workflow_profile",
    "add_work_item_evidence_links",
    "upload_work_item_attachment",
}

INTERNAL_ACTIONS = {"upload_work_item_attachment"}


class WorkflowAdapter:
    def __init__(self, config: BotConfig) -> None:
        self.config = config

    @property
    def tools(self) -> list[dict[str, Any]]:
        return WORKFLOW_TOOLS

    def execute(self, name: str, arguments: dict[str, Any], *, preview: bool = True) -> ToolExecution:
        if name not in {tool["name"] for tool in WORKFLOW_TOOLS} | INTERNAL_ACTIONS:
            raise WorkflowAdapterError("The requested Plane action is not available to this bot.")
        action_arguments = dict(arguments)
        if name in PROJECT_BOUND_ACTIONS:
            action_arguments["project_id"] = self.config.plane_project_id
        if name in WRITE_ACTIONS:
            action_arguments = self._set_preview_mode(name, action_arguments, preview)
        try:
            result = getattr(workflow, name)(**action_arguments)
        except workflow.PlaneWorkflowError as error:
            raise WorkflowAdapterError(str(error)) from error
        if not isinstance(result, dict):
            raise WorkflowAdapterError("The Plane workflow returned an invalid result.")
        original_arguments = {key: value for key, value in action_arguments.items() if key not in {"project_id", "dry_run", "confirm"}}
        return ToolExecution(
            name=name,
            result=result,
            requires_confirmation=name in WRITE_ACTIONS and preview and result.get("status") == "preview",
            arguments=original_arguments,
        )

    def execute_confirmed(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        return self.execute(name, arguments, preview=False).result

    @staticmethod
    def _set_preview_mode(name: str, arguments: dict[str, Any], preview: bool) -> dict[str, Any]:
        adjusted = dict(arguments)
        if name in {"create_standard_work_item", "update_standard_work_item", "ensure_module"}:
            adjusted["dry_run"] = preview
        elif name in {"apply_standardization_plan", "save_project_workflow_profile", "add_work_item_evidence_links", "upload_work_item_attachment"}:
            adjusted["confirm"] = not preview
        return adjusted
