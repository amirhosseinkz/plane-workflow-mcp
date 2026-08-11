"""Configurable workflow tools layered on top of a Plane workspace."""

from __future__ import annotations

import argparse
import hashlib
import html
import importlib.resources
import json
import mimetypes
import os
import re
import sys
import tomllib
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any, Literal
from urllib.parse import urlparse
from uuid import uuid4

import requests
from fastmcp import FastMCP

from configuration import ConfigurationError, load_stored_plane_settings


PLUGIN_ROOT = Path(__file__).resolve().parent
PACKAGED_PROFILES = Path(importlib.resources.files("plane_workflow_mcp").joinpath("profiles.json"))
USER_PROFILES = Path.home() / ".codex" / "plane-workflow" / "profiles.json"
DEFAULT_PLAN_DIR = Path.home() / ".codex" / "plane-workflow" / "plans"
VALID_PRIORITIES = {"urgent", "high", "medium", "low", "none"}
VALID_TYPES = {"bug", "improvement", "task"}


class PlaneWorkflowError(RuntimeError):
    """A safe error suitable for returning through MCP."""


@dataclass(frozen=True)
class PlaneSettings:
    base_url: str
    api_key: str
    workspace: str


def _read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text())
    except json.JSONDecodeError as error:
        raise PlaneWorkflowError(f"Invalid workflow profile file: {path}") from error
    if not isinstance(payload, dict):
        raise PlaneWorkflowError(f"Workflow profile file must contain an object: {path}")
    return payload


def _merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    merged = dict(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def _load_profile_config() -> dict[str, Any]:
    packaged = _read_json(PACKAGED_PROFILES)
    override_path = Path(os.environ.get("PLANE_WORKFLOW_CONFIG", USER_PROFILES))
    user = _read_json(override_path)
    merged = _merge(
        packaged,
        {key: value for key, value in user.items() if key != "profiles"},
    )
    merged["profiles"] = [
        *packaged.get("profiles", []),
        *user.get("profiles", []),
    ]
    return merged


def _profile_override_path() -> Path:
    return Path(os.environ.get("PLANE_WORKFLOW_CONFIG", USER_PROFILES))


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(f"{path.suffix}.tmp")
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    temporary.replace(path)


def _plan_dir() -> Path:
    return Path(os.environ.get("PLANE_WORKFLOW_PLAN_DIR", DEFAULT_PLAN_DIR))


def _plan_path(plan_id: str) -> Path:
    if not re.fullmatch(r"[a-f0-9-]{36}", plan_id):
        raise PlaneWorkflowError("plan_id is invalid.")
    return _plan_dir() / f"{plan_id}.json"


def _read_plan(plan_id: str) -> dict[str, Any]:
    path = _plan_path(plan_id)
    if not path.exists():
        raise PlaneWorkflowError("No saved standardization plan has that id.")
    return _read_json(path)


def _write_plan(plan: dict[str, Any]) -> None:
    _write_json(_plan_path(str(plan["id"])), plan)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _plan_expired(plan: dict[str, Any]) -> bool:
    expires_at = plan.get("expires_at")
    if not isinstance(expires_at, str):
        return True
    try:
        expires = datetime.fromisoformat(expires_at.replace("Z", "+00:00"))
    except ValueError:
        return True
    return expires <= _utc_now()


def _validate_profile(profile: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    match = profile.get("match")
    if match is not None and (
        not isinstance(match, dict)
        or any(not isinstance(value, str) or not _text(value) for value in match.values())
    ):
        errors.append("match must map nonempty strings to nonempty strings.")
    title_template = profile.get("title_template")
    if title_template is not None:
        if not isinstance(title_template, list) or not title_template or not all(isinstance(part, str) and _text(part) for part in title_template):
            errors.append("title_template must be a nonempty list of strings.")
        else:
            allowed_fields = {"context", "module", "surface", "outcome"}
            for part in title_template:
                fields = set(re.findall(r"{([^{}]+)}", part))
                unknown = fields - allowed_fields
                if unknown:
                    errors.append(f"title_template uses unsupported placeholders: {', '.join(sorted(unknown))}.")
    default_priority = profile.get("default_priority")
    if default_priority is not None and default_priority not in VALID_PRIORITIES:
        errors.append("default_priority must be urgent, high, medium, low, or none.")
    language = profile.get("language")
    if language is not None and (not isinstance(language, str) or not _text(language)):
        errors.append("language must be a nonempty string.")
    for key in ("type_labels", "type_label_colors"):
        value = profile.get(key)
        if value is not None and (not isinstance(value, dict) or not all(isinstance(name, str) and isinstance(label, str) for name, label in value.items())):
            errors.append(f"{key} must map strings to strings.")
    stale_after_days = profile.get("stale_after_days")
    if stale_after_days is not None and (
        not isinstance(stale_after_days, int) or isinstance(stale_after_days, bool) or stale_after_days < 1
    ):
        errors.append("stale_after_days must be a positive whole number.")
    return errors


def _user_profile_config() -> dict[str, Any]:
    path = _profile_override_path()
    payload = _read_json(path)
    if "profiles" not in payload:
        payload["profiles"] = []
    if not isinstance(payload["profiles"], list):
        raise PlaneWorkflowError("User workflow profiles must contain a profiles list.")
    return payload


def _find_plane_settings() -> PlaneSettings:
    direct = {
        "base_url": os.getenv("PLANE_BASE_URL"),
        "api_key": os.getenv("PLANE_API_KEY"),
        "workspace": os.getenv("PLANE_WORKSPACE_SLUG"),
    }
    if all(direct.values()):
        return PlaneSettings(**direct)  # type: ignore[arg-type]

    stored_error: ConfigurationError | None = None
    try:
        stored = load_stored_plane_settings()
    except ConfigurationError as error:
        stored = None
        stored_error = error
    if stored:
        return PlaneSettings(base_url=stored.base_url, api_key=stored.api_key, workspace=stored.workspace)

    config_path = Path.home() / ".codex" / "config.toml"
    if not config_path.exists():
        setup_hint = f" Run plane-workflow setup. ({stored_error})" if stored_error else " Run plane-workflow setup."
        raise PlaneWorkflowError(
            "Plane credentials are not configured. Set PLANE_BASE_URL, PLANE_API_KEY, and "
            f"PLANE_WORKSPACE_SLUG, configure a legacy Codex MCP server, or use the standalone setup.{setup_hint}"
        )

    config = tomllib.loads(config_path.read_text())
    servers = config.get("mcp_servers", {})
    preferred = os.getenv("PLANE_WORKFLOW_SOURCE")
    candidates: list[tuple[str, dict[str, Any]]] = []
    for name, server in servers.items():
        environment = server.get("env", {}) if isinstance(server, dict) else {}
        if all(environment.get(key) for key in ("PLANE_BASE_URL", "PLANE_API_KEY", "PLANE_WORKSPACE_SLUG")):
            candidates.append((name, environment))

    if preferred:
        candidates = [candidate for candidate in candidates if candidate[0] == preferred]
    if len(candidates) != 1:
        names = ", ".join(name for name, _ in candidates) or "none"
        raise PlaneWorkflowError(
            "Could not select one Plane MCP configuration. Set PLANE_WORKFLOW_SOURCE to one "
            f"configured server name. Available candidates: {names}. Or run plane-workflow setup."
        )

    _, environment = candidates[0]
    return PlaneSettings(
        base_url=environment["PLANE_BASE_URL"],
        api_key=environment["PLANE_API_KEY"],
        workspace=environment["PLANE_WORKSPACE_SLUG"],
    )


class PlaneApi:
    def __init__(self, settings: PlaneSettings) -> None:
        self.base_url = settings.base_url.rstrip("/")
        self.workspace = settings.workspace
        self.session = requests.Session()
        self.session.headers.update({"X-API-Key": settings.api_key, "Accept": "application/json"})

    def request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        payload: dict[str, Any] | None = None,
    ) -> Any:
        normalized_path = path.strip("/")
        url = f"{self.base_url}/api/v1/workspaces/{self.workspace}/{normalized_path}/"
        response = self.session.request(method, url, params=params, json=payload, timeout=30)
        if not response.ok:
            raise PlaneWorkflowError(f"Plane API request failed with HTTP {response.status_code}.")
        if not response.content:
            return None
        return response.json()

    def project(self, project_id: str) -> dict[str, Any]:
        return self.request("GET", f"projects/{project_id}")

    def modules(self, project_id: str) -> list[dict[str, Any]]:
        return _results(self.request("GET", f"projects/{project_id}/modules", params={"per_page": 1000}))

    def states(self, project_id: str) -> list[dict[str, Any]]:
        return _results(self.request("GET", f"projects/{project_id}/states", params={"per_page": 1000}))

    def cycles(self, project_id: str) -> list[dict[str, Any]]:
        return _results(self.request("GET", f"projects/{project_id}/cycles", params={"per_page": 1000}))

    def members(self, project_id: str) -> list[dict[str, Any]]:
        return _results(self.request("GET", f"projects/{project_id}/members", params={"per_page": 1000}))

    def releases(self) -> list[dict[str, Any]]:
        return _results(self.request("GET", "releases/", params={"per_page": 1000}))

    def labels(self, project_id: str) -> list[dict[str, Any]]:
        return _results(self.request("GET", f"projects/{project_id}/labels", params={"per_page": 1000}))

    def work_items(self, project_id: str) -> tuple[list[dict[str, Any]], int | None]:
        """Return every work item, including projects with more than one API page."""
        items: list[dict[str, Any]] = []
        total_count: int | None = None
        page = 1
        while True:
            payload = self.request("GET", f"projects/{project_id}/work-items", params={"per_page": 100, "page": page})
            page_items = _results(payload)
            items.extend(page_items)
            if isinstance(payload, dict) and isinstance(payload.get("total_count"), int):
                total_count = payload["total_count"]
            if not page_items or (total_count is not None and len(items) >= total_count):
                break
            page += 1
            if page > 10_000:
                raise PlaneWorkflowError("Plane returned too many work-item pages to export safely.")
        return items, total_count

    def work_item(self, project_id: str, work_item_id: str) -> dict[str, Any]:
        return self.request("GET", f"projects/{project_id}/work-items/{work_item_id}")

    def work_item_links(self, project_id: str, work_item_id: str) -> list[dict[str, Any]]:
        return _results(
            self.request(
                "GET",
                f"projects/{project_id}/work-items/{work_item_id}/links",
                params={"per_page": 1000},
            )
        )

    def create_work_item_link(self, project_id: str, work_item_id: str, *, url: str, title: str | None) -> dict[str, Any]:
        payload: dict[str, Any] = {"url": url}
        if title:
            payload["title"] = title
        return self.request(
            "POST",
            f"projects/{project_id}/work-items/{work_item_id}/links",
            payload=payload,
        )

    def upload_work_item_attachment(
        self,
        project_id: str,
        work_item_id: str,
        *,
        name: str,
        content_type: str,
        file_bytes: bytes,
    ) -> dict[str, Any]:
        """Use Plane's three-step presigned-upload flow without exposing presigned data to MCP clients."""
        raw = self.request(
            "POST",
            f"projects/{project_id}/work-items/{work_item_id}/attachments",
            payload={"name": name, "type": content_type, "size": len(file_bytes)},
        )
        if not isinstance(raw, dict):
            raise PlaneWorkflowError("Plane returned an invalid attachment upload response.")
        upload_data = raw.get("upload_data")
        asset_id = raw.get("asset_id")
        attachment = raw.get("attachment")
        if not isinstance(upload_data, dict) or not isinstance(asset_id, str) or not isinstance(attachment, dict):
            raise PlaneWorkflowError("Plane did not provide a complete attachment upload request.")
        upload_url = upload_data.get("url")
        fields = upload_data.get("fields", {})
        if not isinstance(upload_url, str) or not isinstance(fields, dict):
            raise PlaneWorkflowError("Plane did not provide a valid attachment storage request.")
        try:
            response = requests.post(
                upload_url,
                data=fields,
                files={"file": (name, file_bytes, content_type)},
                timeout=120,
            )
            response.raise_for_status()
        except requests.RequestException as error:
            raise PlaneWorkflowError("Attachment storage upload failed. The attachment record may be incomplete.") from error
        self.request(
            "PATCH",
            f"projects/{project_id}/work-items/{work_item_id}/attachments/{asset_id}",
            payload={"is_uploaded": True},
        )
        return attachment

    def create_work_item(self, project_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        return self.request("POST", f"projects/{project_id}/work-items", payload=payload)

    def update_work_item(self, project_id: str, work_item_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        return self.request("PATCH", f"projects/{project_id}/work-items/{work_item_id}", payload=payload)

    def create_label(self, project_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        return self.request("POST", f"projects/{project_id}/labels", payload=payload)

    def create_module(self, project_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        return self.request("POST", f"projects/{project_id}/modules", payload=payload)

    def attach_to_module(self, project_id: str, module_id: str, work_item_ids: list[str]) -> None:
        self.request(
            "POST",
            f"projects/{project_id}/modules/{module_id}/module-issues",
            payload={"issues": work_item_ids},
        )

    def attach_to_cycle(self, project_id: str, cycle_id: str, work_item_ids: list[str]) -> None:
        self.request(
            "POST",
            f"projects/{project_id}/cycles/{cycle_id}/cycle-issues",
            payload={"issues": work_item_ids},
        )

    def module_work_items(self, project_id: str, module_id: str) -> list[dict[str, Any]]:
        return _results(
            self.request(
                "GET",
                f"projects/{project_id}/modules/{module_id}/module-issues",
                params={"per_page": 1000},
            )
        )


def _results(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if isinstance(payload, dict):
        results = payload.get("results", [])
        return [item for item in results if isinstance(item, dict)]
    return []


def _text(value: str | None) -> str:
    return re.sub(r"\s+", " ", (value or "").strip())


def _normalize(value: str | None) -> str:
    return re.sub(r"[\W_]+", "", _text(value).casefold(), flags=re.UNICODE)


def _resolve_profile(api: PlaneApi, project_id: str) -> tuple[dict[str, Any], dict[str, Any]]:
    project = api.project(project_id)
    config = _load_profile_config()
    profile = dict(config.get("default", {}))
    for candidate in config.get("profiles", []):
        if not isinstance(candidate, dict):
            continue
        match = candidate.get("match", {})
        workspace_matches = not match.get("workspace") or match["workspace"] == api.workspace
        identifier_matches = not match.get("project_identifier") or match["project_identifier"] == project.get("identifier")
        if workspace_matches and identifier_matches:
            profile = _merge(profile, candidate)
    return profile, project


def _build_title(
    profile: dict[str, Any],
    *,
    context: str | None,
    module: str | None,
    surface: str | None,
    outcome: str,
    title_parts: list[str] | None,
) -> str:
    if title_parts:
        parts = [_text(part).strip("|") for part in title_parts if _text(part)]
    else:
        values = {"context": _text(context), "module": _text(module), "surface": _text(surface), "outcome": _text(outcome)}
        parts = []
        for template_part in profile.get("title_template", ["{context}", "{module}", "{surface}", "{outcome}"]):
            try:
                rendered = str(template_part).format_map(values)
            except KeyError:
                continue
            rendered = _text(rendered).strip("|")
            if rendered and "{" not in rendered:
                parts.append(rendered)
    if not parts:
        raise PlaneWorkflowError("Provide title_parts or at least an outcome.")
    return " | ".join(parts)


def _render_description(
    work_item_type: str,
    *,
    outcome: str,
    current_behavior: str | None,
    expected_behavior: str | None,
    scope: str | None,
    acceptance_criteria: list[str],
) -> str:
    if not acceptance_criteria:
        raise PlaneWorkflowError("Provide at least one observable acceptance criterion.")
    if work_item_type == "bug" and (not _text(current_behavior) or not _text(expected_behavior)):
        raise PlaneWorkflowError("Bug work items require current_behavior and expected_behavior.")

    sections: list[tuple[str, str]] = []
    if work_item_type == "bug":
        sections.extend([("Current behavior", _text(current_behavior)), ("Expected behavior", _text(expected_behavior))])
    else:
        sections.append(("Requested outcome", _text(outcome)))
    if _text(scope):
        sections.append(("Scope", _text(scope)))
    body = "".join(f"<p><strong>{html.escape(title)}</strong></p><p>{html.escape(value)}</p>" for title, value in sections)
    criteria = "".join(f"<li>{html.escape(_text(item))}</li>" for item in acceptance_criteria if _text(item))
    return f"{body}<p><strong>Acceptance criteria</strong></p><ul>{criteria}</ul>"


def _find_by_name(items: list[dict[str, Any]], name: str) -> dict[str, Any] | None:
    wanted = _text(name).casefold()
    return next((item for item in items if _text(str(item.get("name", ""))).casefold() == wanted), None)


def _ensure_label(
    api: PlaneApi,
    project_id: str,
    labels: list[dict[str, Any]],
    name: str,
    *,
    description: str,
    color: str | None = None,
) -> dict[str, Any]:
    existing = _find_by_name(labels, name)
    if existing:
        return existing
    created = api.create_label(project_id, {"name": name, "color": color, "description": description})
    labels.append(created)
    return created


def _ensure_type_label(api: PlaneApi, project_id: str, labels: list[dict[str, Any]], profile: dict[str, Any], work_item_type: str) -> dict[str, Any] | None:
    if work_item_type == "task":
        return None
    label_name = profile.get("type_labels", {}).get(work_item_type, work_item_type.title())
    color_value = profile.get("type_label_colors", {}).get(work_item_type)
    color = _text(color_value) if isinstance(color_value, str) else None
    return _ensure_label(
        api,
        project_id,
        labels,
        _text(str(label_name)),
        description=f"{work_item_type.title()} work item.",
        color=color or None,
    )


def _module(api: PlaneApi, project_id: str, module_name: str | None, *, allow_create: bool, description: str | None) -> dict[str, Any] | None:
    if not _text(module_name):
        return None
    existing = _find_by_name(api.modules(project_id), module_name)
    if existing:
        return existing
    if not allow_create:
        raise PlaneWorkflowError(f"No module named '{module_name}' exists. Set allow_create_module to create it explicitly.")
    payload: dict[str, Any] = {"name": _text(module_name), "status": "backlog"}
    if _text(description):
        payload["description"] = _text(description)
    return api.create_module(project_id, payload)


def _module_preview(
    api: PlaneApi,
    project_id: str,
    module_name: str | None,
    *,
    allow_create: bool,
    description: str | None,
) -> dict[str, Any] | None:
    if not _text(module_name):
        return None
    existing = _find_by_name(api.modules(project_id), module_name)
    if existing:
        return {"id": existing.get("id"), "name": existing.get("name"), "will_create": False}
    if not allow_create:
        raise PlaneWorkflowError(f"No module named '{module_name}' exists. Set allow_create_module to create it explicitly.")
    return {"id": None, "name": _text(module_name), "description": _text(description) or None, "will_create": True}


def _duplicate(items: list[dict[str, Any]], title: str) -> dict[str, Any] | None:
    wanted = _normalize(title)
    return next((item for item in items if _normalize(str(item.get("name", ""))) == wanted), None)


def _title_tokens(value: str | None) -> set[str]:
    return {token for token in re.findall(r"\w+", _text(value).casefold(), flags=re.UNICODE) if len(token) > 1}


def _title_similarity(left: str | None, right: str | None) -> float:
    normalized_left = _normalize(left)
    normalized_right = _normalize(right)
    if not normalized_left or not normalized_right:
        return 0.0
    if normalized_left == normalized_right:
        return 1.0
    left_tokens = _title_tokens(left)
    right_tokens = _title_tokens(right)
    token_overlap = len(left_tokens & right_tokens) / len(left_tokens | right_tokens) if left_tokens and right_tokens else 0.0
    sequence_similarity = SequenceMatcher(None, normalized_left, normalized_right).ratio()
    return round(max(token_overlap, (sequence_similarity * 0.6) + (token_overlap * 0.4)), 3)


def _duplicate_candidates(items: list[dict[str, Any]], title: str, *, min_score: float) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    for item in items:
        score = _title_similarity(title, str(item.get("name", "")))
        if score >= min_score:
            candidates.append({"score": score, "work_item": _work_item_summary(item)})
    return sorted(candidates, key=lambda candidate: (-float(candidate["score"]), str(candidate["work_item"].get("name", ""))))


def _work_item_search_results(
    items: list[dict[str, Any]],
    query: str,
    *,
    project_identifier: str | None,
) -> list[dict[str, Any]]:
    normalized_query = _normalize(query)
    query_lower = _text(query).casefold()
    sequence_match = re.fullmatch(
        rf"{re.escape(_text(project_identifier or ''))}-(\d+)",
        _text(query),
        flags=re.IGNORECASE,
    ) if _text(project_identifier) else None
    results: list[dict[str, Any]] = []
    for item in items:
        item_id = _text(str(item.get("id", "")))
        sequence_id = str(item.get("sequence_id", ""))
        title = _text(str(item.get("name", "")))
        reference = f"{project_identifier}-{sequence_id}" if project_identifier and sequence_id else None
        score = 0.0
        if query_lower == item_id.casefold() or (reference and query_lower == reference.casefold()):
            score = 1.0
        elif sequence_match and sequence_id == sequence_match.group(1):
            score = 1.0
        elif query_lower in title.casefold() or (normalized_query and normalized_query in _normalize(title)):
            score = max(0.9, _title_similarity(query, title))
        else:
            score = _title_similarity(query, title)
        if score >= 0.45:
            results.append(
                {
                    "score": round(score, 3),
                    "work_item": {**_work_item_summary(item), "identifier": reference},
                }
            )
    return sorted(results, key=lambda result: (-float(result["score"]), str(result["work_item"].get("name", ""))))


def _label_ids(item: dict[str, Any]) -> list[str]:
    identifiers: list[str] = []
    for label in item.get("labels", []):
        if isinstance(label, str):
            identifiers.append(label)
        elif isinstance(label, dict) and label.get("id"):
            identifiers.append(str(label["id"]))
    return identifiers


def _item_fingerprint(item: dict[str, Any]) -> str:
    snapshot = {
        "id": item.get("id"),
        "name": item.get("name"),
        "priority": item.get("priority"),
        "labels": sorted(_label_ids(item)),
        "updated_at": item.get("updated_at"),
    }
    return hashlib.sha256(json.dumps(snapshot, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def _type_labels(profile: dict[str, Any]) -> dict[str, str]:
    configured = profile.get("type_labels", {})
    if not isinstance(configured, dict):
        return {}
    return {
        _text(str(name)).casefold(): _text(str(label))
        for name, label in configured.items()
        if _text(str(name)) in VALID_TYPES and _text(str(label))
    }


def _build_standardization_actions(
    items: list[dict[str, Any]],
    labels: list[dict[str, Any]],
    profile: dict[str, Any],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Propose only deterministic structural changes; all other gaps remain advisories."""
    label_ids_by_name = {
        _text(str(label.get("name", ""))).casefold(): str(label.get("id"))
        for label in labels
        if label.get("id") and _text(str(label.get("name", "")))
    }
    type_labels = _type_labels(profile)
    type_by_label = {label.casefold(): work_item_type for work_item_type, label in type_labels.items()}
    default_priority = profile.get("default_priority", "medium")
    actions: list[dict[str, Any]] = []
    advisories: list[dict[str, Any]] = []

    for item in items:
        name = _text(str(item.get("name", "")))
        parts = [_text(part) for part in name.split("|")]
        first_part = parts[0].casefold() if parts else ""
        changes: dict[str, Any] = {}
        advisory_findings: list[str] = []
        if item.get("priority") in {None, "", "none"} and default_priority in VALID_PRIORITIES:
            changes["priority"] = default_priority
        work_item_type = type_by_label.get(first_part)
        if work_item_type:
            remaining_title = " | ".join(part for part in parts[1:] if part)
            if remaining_title:
                changes["name"] = remaining_title
            else:
                advisory_findings.append("type_prefix_cannot_be_removed_without_an_empty_title")
            label_name = type_labels[work_item_type]
            label_id = label_ids_by_name.get(label_name.casefold())
            if not label_id or label_id not in _label_ids(item):
                changes["ensure_type_label"] = {"type": work_item_type, "name": label_name}
        if changes:
            actions.append(
                {
                    "work_item": _work_item_summary(item),
                    "work_item_id": item.get("id"),
                    "fingerprint": _item_fingerprint(item),
                    "changes": changes,
                }
            )
        if not any(_text(str(item.get(key, ""))) for key in ("description", "description_html", "description_stripped")):
            advisory_findings.append("missing_description")
        if advisory_findings:
            advisories.append({"work_item": _work_item_summary(item), "findings": advisory_findings})
    return actions, advisories


def _work_item_summary(item: dict[str, Any]) -> dict[str, Any]:
    return {"id": item.get("id"), "sequence_id": item.get("sequence_id"), "name": item.get("name"), "priority": item.get("priority")}


def _profile_view(profile: dict[str, Any]) -> dict[str, Any]:
    """Return configuration only; profiles never contain Plane credentials."""
    return {
        key: value
        for key, value in profile.items()
        if key in {"match", "title_template", "default_priority", "type_labels", "type_label_colors", "language", "stale_after_days"}
    }


def _project_profile_match(api: PlaneApi, project: dict[str, Any]) -> dict[str, str]:
    identifier = _text(str(project.get("identifier", "")))
    if not identifier:
        raise PlaneWorkflowError("The Plane project does not have an identifier, so a profile cannot be bound safely.")
    return {"workspace": api.workspace, "project_identifier": identifier}


def _option_id(item: dict[str, Any], *, member: bool = False) -> str | None:
    if member:
        nested = item.get("member")
        if isinstance(nested, dict) and nested.get("id"):
            return str(nested["id"])
        if isinstance(nested, str) and _text(nested):
            return nested
        if item.get("member_id"):
            return str(item["member_id"])
    if item.get("id"):
        return str(item["id"])
    return None


def _workflow_option_view(item: dict[str, Any], *, member: bool = False) -> dict[str, Any]:
    nested = item.get("member") if member else None
    nested_data = nested if isinstance(nested, dict) else {}
    return {
        "id": _option_id(item, member=member),
        "name": item.get("name")
        or item.get("display_name")
        or nested_data.get("display_name")
        or nested_data.get("name")
        or nested_data.get("email")
        or item.get("email"),
        "type": item.get("type") or item.get("group"),
    }


def _optional_options(loader: Any, *, member: bool = False) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    try:
        items = loader()
    except PlaneWorkflowError:
        return [], {"available": False}
    return [_workflow_option_view(item, member=member) for item in items], {"available": True}


def _validate_date(value: str | None, field_name: str) -> str | None:
    if value is None:
        return None
    candidate = _text(value)
    try:
        date.fromisoformat(candidate)
    except ValueError as error:
        raise PlaneWorkflowError(f"{field_name} must use YYYY-MM-DD.") from error
    return candidate


def _validate_estimate(value: int | str | None) -> int | str | None:
    if value is None:
        return None
    if isinstance(value, bool):
        raise PlaneWorkflowError("estimate must be a non-negative number or a configured estimate value.")
    if isinstance(value, int):
        if value < 0:
            raise PlaneWorkflowError("estimate must be non-negative.")
        return value
    if isinstance(value, str) and _text(value):
        return _text(value)
    raise PlaneWorkflowError("estimate must be a non-negative number or a configured estimate value.")


def _validate_id_list(values: list[str] | None, field_name: str) -> list[str] | None:
    if values is None:
        return None
    if not all(isinstance(value, str) and _text(value) for value in values):
        raise PlaneWorkflowError(f"{field_name} must contain nonempty IDs.")
    return list(dict.fromkeys(_text(value) for value in values))


def _validate_workflow_selection(
    api: PlaneApi,
    project_id: str,
    *,
    assignee_ids: list[str] | None,
    state_id: str | None,
    cycle_id: str | None,
    release_id: str | None,
) -> None:
    if state_id:
        state_ids = {_option_id(item) for item in api.states(project_id)}
        if state_id not in state_ids:
            raise PlaneWorkflowError("state_id is not available in this project. Use get_workflow_options first.")
    if cycle_id:
        cycle_ids = {_option_id(item) for item in api.cycles(project_id)}
        if cycle_id not in cycle_ids:
            raise PlaneWorkflowError("cycle_id is not available in this project. Use get_workflow_options first.")
    if assignee_ids:
        member_ids = {_option_id(item, member=True) for item in api.members(project_id)}
        unknown = [member_id for member_id in assignee_ids if member_id not in member_ids]
        if unknown:
            raise PlaneWorkflowError("One or more assignee_ids are not project members. Use get_workflow_options first.")
    if release_id:
        try:
            api.releases()
        except PlaneWorkflowError as error:
            raise PlaneWorkflowError("Release assignment is unavailable on this Plane server. No work item was changed.") from error
        raise PlaneWorkflowError("This Plane API exposes releases but not work-item release assignments. No work item was changed.")


def _workflow_field_payload(
    *,
    assignee_ids: list[str] | None,
    state_id: str | None,
    estimate: int | str | None,
    start_date: str | None,
    target_date: str | None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {}
    if assignee_ids is not None:
        payload["assignees"] = assignee_ids
    if state_id:
        payload["state"] = state_id
    if estimate is not None:
        payload["estimate_point"] = estimate
    if start_date is not None:
        payload["start_date"] = start_date
    if target_date is not None:
        payload["target_date"] = target_date
    return payload


def _normalize_evidence_links(evidence: list[dict[str, str]]) -> list[dict[str, str | None]]:
    if not evidence:
        raise PlaneWorkflowError("Provide at least one evidence link.")
    normalized: list[dict[str, str | None]] = []
    seen_urls: set[str] = set()
    for item in evidence:
        if not isinstance(item, dict):
            raise PlaneWorkflowError("Each evidence link must be an object with a url and optional title.")
        url = _text(item.get("url"))
        parsed = urlparse(url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise PlaneWorkflowError("Evidence links must use an absolute http or https URL.")
        if url in seen_urls:
            continue
        title_value = item.get("title")
        if title_value is not None and not isinstance(title_value, str):
            raise PlaneWorkflowError("Evidence-link titles must be strings.")
        title = _text(title_value) if isinstance(title_value, str) else None
        if title and len(title) > 240:
            raise PlaneWorkflowError("Evidence-link titles must be 240 characters or fewer.")
        seen_urls.add(url)
        normalized.append({"url": url, "title": title or None})
    if not normalized:
        raise PlaneWorkflowError("Provide at least one unique evidence link.")
    return normalized


def _attachment_metadata(file_path: str, max_size_mb: int) -> dict[str, Any]:
    if isinstance(max_size_mb, bool) or not isinstance(max_size_mb, int) or not 1 <= max_size_mb <= 100:
        raise PlaneWorkflowError("max_size_mb must be a whole number from 1 to 100.")
    try:
        path = Path(file_path).expanduser().resolve(strict=True)
    except OSError as error:
        raise PlaneWorkflowError("The attachment file could not be found.") from error
    if not path.is_file():
        raise PlaneWorkflowError("The attachment path must point to a regular file.")
    size = path.stat().st_size
    limit = max_size_mb * 1024 * 1024
    if size > limit:
        raise PlaneWorkflowError(f"The attachment is larger than the {max_size_mb} MB limit.")
    content_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    return {"path": path, "name": path.name, "size": size, "type": content_type}


def _append_evidence_note(description_html: str | None, note: str) -> str:
    existing = description_html or ""
    return f"{existing}<p><strong>Evidence note</strong></p><p>{html.escape(note)}</p>"


def _plain_text(value: Any) -> str:
    return _text(re.sub(r"<[^>]+>", " ", html.unescape(str(value or ""))))


def _item_description_text(item: dict[str, Any]) -> str:
    for field in ("description_stripped", "description_html", "description"):
        text = _plain_text(item.get(field))
        if text:
            return text
    return ""


def _item_state_id(item: dict[str, Any]) -> str | None:
    state = item.get("state")
    if isinstance(state, dict) and state.get("id"):
        return str(state["id"])
    if isinstance(state, str) and _text(state):
        return state
    return None


def _updated_at(value: Any) -> datetime | None:
    if not isinstance(value, str) or not _text(value):
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def _audit_finding(code: str, severity: Literal["error", "warning", "advisory"], message: str) -> dict[str, str]:
    return {"code": code, "severity": severity, "message": message}


def _quality_findings_for_item(
    item: dict[str, Any],
    *,
    type_labels: dict[str, str],
    type_label_ids: dict[str, str],
    assigned_ids: set[str],
    state_types: dict[str, str],
    stale_after_days: int,
) -> list[dict[str, str]]:
    findings: list[dict[str, str]] = []
    name = _text(str(item.get("name", "")))
    parts = [_text(part) for part in name.split("|")]
    first_part = parts[0].casefold() if parts else ""
    type_by_label = {label.casefold(): work_item_type for work_item_type, label in type_labels.items()}
    item_label_ids = set(_label_ids(item))
    matching_types = [work_item_type for work_item_type, label_id in type_label_ids.items() if label_id in item_label_ids]
    description = _item_description_text(item)

    if item.get("priority") in {None, "", "none"}:
        findings.append(_audit_finding("missing_priority", "warning", "No priority is set."))
    if first_part in type_by_label:
        findings.append(_audit_finding("type_encoded_in_title", "advisory", "The work-item type is encoded in the title instead of represented only by a label."))
        inferred_type = type_by_label[first_part]
        if type_label_ids.get(inferred_type) not in item_label_ids:
            findings.append(_audit_finding("missing_type_label", "warning", "The type inferred from the title is not present as a label."))
    if len(matching_types) > 1:
        findings.append(_audit_finding("conflicting_type_labels", "error", "More than one configured work-item type label is assigned."))
    if not description:
        findings.append(_audit_finding("missing_description", "warning", "The work item has no structured description."))
    else:
        lower_description = description.casefold()
        criterion_marker = re.search(r"acceptance criteria|معیار(?:های)? پذیرش", lower_description)
        if not criterion_marker:
            findings.append(_audit_finding("missing_acceptance_criteria", "warning", "The description does not contain acceptance criteria."))
        else:
            criteria_text = lower_description[criterion_marker.end() :]
            generic_phrases = (
                "works correctly",
                "works as expected",
                "should work",
                "works fine",
                "is fixed",
                "به درستی کار کند",
                "درست کار کند",
            )
            if criteria_text and any(phrase in criteria_text for phrase in generic_phrases):
                findings.append(_audit_finding("non_testable_acceptance_criteria", "advisory", "Acceptance criteria contain a generic outcome rather than an observable condition."))
        if "scope" not in lower_description and "دامنه" not in lower_description:
            findings.append(_audit_finding("scope_not_explicit", "advisory", "The description does not explicitly state scope or exclusions."))
    if str(item.get("id")) not in assigned_ids:
        findings.append(_audit_finding("unassigned_module", "warning", "The work item is not assigned to a module."))
    normalized_name = _normalize(name)
    if len(_title_tokens(name)) < 3 or normalized_name in {"bug", "task", "improvement", "fixbug", "fixissue", "update"}:
        findings.append(_audit_finding("vague_title", "advisory", "The title is too short or generic to communicate a clear outcome."))
    state_type = state_types.get(_item_state_id(item) or "")
    last_updated = _updated_at(item.get("updated_at"))
    if state_type not in {"completed", "cancelled"} and last_updated and _utc_now() - last_updated > timedelta(days=stale_after_days):
        findings.append(_audit_finding("stale_work_item", "advisory", f"No update has been recorded for more than {stale_after_days} days."))
    return findings


def _connection_probe(loader: Any) -> dict[str, Any]:
    try:
        result = loader()
    except (PlaneWorkflowError, requests.RequestException):
        return {"available": False}
    if isinstance(result, tuple) and result and isinstance(result[0], list):
        return {"available": True, "count": len(result[0])}
    if isinstance(result, list):
        return {"available": True, "count": len(result)}
    return {"available": True}


mcp = FastMCP(
    "Plane Workflow",
    instructions=(
        "Use these tools to create and maintain Plane work items through configurable workflow rules. "
        "For a new installation, call get_plane_workflow_setup_status first and run plane-workflow setup "
        "when it reports needs_setup. Use get_project_workflow_context before writes and audit_work_items before bulk changes."
    ),
)


@mcp.tool()
def get_plane_workflow_setup_status() -> dict[str, Any]:
    """Check whether Plane Workflow is configured, without contacting Plane or revealing credentials."""
    direct = all(os.getenv(name) for name in ("PLANE_BASE_URL", "PLANE_API_KEY", "PLANE_WORKSPACE_SLUG"))
    if direct:
        return {"status": "configured", "configured": True, "source": "environment", "next_command": None}
    try:
        stored = load_stored_plane_settings()
    except ConfigurationError as error:
        return {
            "status": "needs_setup",
            "configured": False,
            "next_command": "plane-workflow setup",
            "recommendation": str(error),
        }
    if stored:
        return {"status": "configured", "configured": True, "source": "operating-system keyring", "next_command": None}
    try:
        _find_plane_settings()
    except PlaneWorkflowError:
        pass
    else:
        return {"status": "configured", "configured": True, "source": "legacy Codex configuration", "next_command": None}
    return {
        "status": "needs_setup",
        "configured": False,
        "next_command": "plane-workflow setup",
        "recommendation": "Run plane-workflow setup to choose a client and securely enter your Plane API key.",
    }


@mcp.tool()
def get_project_workflow_context(project_id: str) -> dict[str, Any]:
    """Read a project's identifiers, active profile, modules, labels, and work-item count without changing Plane."""
    api = PlaneApi(_find_plane_settings())
    profile, project = _resolve_profile(api, project_id)
    work_items, total_count = api.work_items(project_id)
    return {
        "project": {"id": project.get("id"), "identifier": project.get("identifier"), "name": project.get("name")},
        "workspace": api.workspace,
        "profile": {"title_template": profile.get("title_template"), "default_priority": profile.get("default_priority"), "language": profile.get("language")},
        "modules": [{"id": item.get("id"), "name": item.get("name"), "description": item.get("description")} for item in api.modules(project_id)],
        "labels": [{"id": item.get("id"), "name": item.get("name")} for item in api.labels(project_id)],
        "work_item_count": total_count if total_count is not None else len(work_items),
    }


@mcp.tool()
def get_project_workflow_profile(project_id: str) -> dict[str, Any]:
    """Read the merged workflow profile for a Plane project without changing Plane or local profile files."""
    api = PlaneApi(_find_plane_settings())
    profile, project = _resolve_profile(api, project_id)
    return {
        "status": "profile",
        "project": {"id": project.get("id"), "identifier": project.get("identifier"), "name": project.get("name")},
        "binding": _project_profile_match(api, project),
        "profile": _profile_view(profile),
        "user_profile_path": str(_profile_override_path()),
        "note": "This is configuration only. It does not change Plane.",
    }


@mcp.tool()
def get_workflow_options(project_id: str) -> dict[str, Any]:
    """List the available state, cycle, and assignee choices for a project without changing Plane."""
    api = PlaneApi(_find_plane_settings())
    project = api.project(project_id)
    states, state_capability = _optional_options(lambda: api.states(project_id))
    cycles, cycle_capability = _optional_options(lambda: api.cycles(project_id))
    members, member_capability = _optional_options(lambda: api.members(project_id), member=True)
    releases, release_capability = _optional_options(api.releases)
    return {
        "status": "options",
        "project": {"id": project.get("id"), "identifier": project.get("identifier"), "name": project.get("name")},
        "states": states,
        "cycles": cycles,
        "assignees": members,
        "releases": releases,
        "capabilities": {
            "state": state_capability,
            "cycle_assignment": cycle_capability,
            "assignee": member_capability,
            "estimate": {"available": True},
            "dates": {"available": True},
            "release_assignment": {"available": False, "reason": "This Plane API does not expose a work-item release relationship."},
            "release_catalog": release_capability,
        },
        "note": "Use these IDs when creating or updating a work item. Release assignment is reported separately because it is not available through this Plane API.",
    }


@mcp.tool()
def diagnose_plane_connection(project_id: str | None = None) -> dict[str, Any]:
    """Check local Plane configuration and, when given a project, read the available API capabilities without changing Plane."""
    try:
        settings = _find_plane_settings()
    except PlaneWorkflowError as error:
        return {
            "status": "unhealthy",
            "connection": {"configured": False},
            "checks": {},
            "recommendations": [str(error)],
        }
    connection = {"configured": True, "base_url": settings.base_url, "workspace": settings.workspace}
    if not project_id:
        return {
            "status": "configured",
            "connection": connection,
            "checks": {},
            "recommendations": ["Provide project_id to run read-only API capability checks."],
        }

    api = PlaneApi(settings)
    checks: dict[str, dict[str, Any]] = {"project": _connection_probe(lambda: api.project(project_id))}
    if not checks["project"]["available"]:
        return {
            "status": "unhealthy",
            "connection": connection,
            "project_id": project_id,
            "checks": checks,
            "recommendations": ["Check the Plane URL, API key permissions, workspace, and project ID."],
        }
    checks.update(
        {
            "modules": _connection_probe(lambda: api.modules(project_id)),
            "labels": _connection_probe(lambda: api.labels(project_id)),
            "work_items": _connection_probe(lambda: api.work_items(project_id)),
            "states": _connection_probe(lambda: api.states(project_id)),
            "cycles": _connection_probe(lambda: api.cycles(project_id)),
            "members": _connection_probe(lambda: api.members(project_id)),
            "releases": _connection_probe(api.releases),
        }
    )
    core_checks = ("modules", "labels", "work_items", "states", "cycles", "members")
    status = "healthy" if all(checks[name]["available"] for name in core_checks) else "degraded"
    recommendations: list[str] = []
    if not checks["releases"]["available"]:
        recommendations.append("Release catalog and release assignment are unavailable on this Plane server; the workflow will leave releases untouched.")
    if status == "degraded":
        unavailable = ", ".join(name for name in core_checks if not checks[name]["available"])
        recommendations.append(f"Unavailable project capabilities: {unavailable}. Use only the available fields until the Plane server is updated or permissions are fixed.")
    if not recommendations:
        recommendations.append("Core Plane workflow capabilities are available.")
    return {
        "status": status,
        "connection": connection,
        "project_id": project_id,
        "checks": checks,
        "recommendations": recommendations,
        "note": "This diagnostic is read-only and never returns your API key.",
    }


@mcp.tool()
def validate_workflow_profile(profile: dict[str, Any]) -> dict[str, Any]:
    """Validate a reusable workflow-profile override and return a representative title preview without saving it."""
    if not isinstance(profile, dict):
        raise PlaneWorkflowError("profile must be an object.")
    errors = _validate_profile(profile)
    merged = _merge(dict(_load_profile_config().get("default", {})), profile)
    preview: str | None = None
    if not errors:
        preview = _build_title(
            merged,
            context="Context",
            module="Module",
            surface="Surface",
            outcome="Clear outcome",
            title_parts=None,
        )
    return {
        "status": "valid" if not errors else "invalid",
        "valid": not errors,
        "errors": errors,
        "title_preview": preview,
        "profile": _profile_view(profile),
        "note": "No profile was saved.",
    }


@mcp.tool()
def save_project_workflow_profile(
    project_id: str,
    profile: dict[str, Any],
    replace_existing: bool = False,
    confirm: bool = False,
) -> dict[str, Any]:
    """Preview or save a project-bound workflow-profile override locally. Set confirm=true to write the profile file."""
    if not isinstance(profile, dict):
        raise PlaneWorkflowError("profile must be an object.")
    if "match" in profile:
        raise PlaneWorkflowError("Do not provide match. The profile is bound automatically to the selected Plane project.")
    errors = _validate_profile(profile)
    if errors:
        return {"status": "invalid", "valid": False, "errors": errors, "note": "No profile was saved."}

    api = PlaneApi(_find_plane_settings())
    project = api.project(project_id)
    binding = _project_profile_match(api, project)
    user_config = _user_profile_config()
    profiles = user_config["profiles"]
    existing_index = next(
        (
            index
            for index, candidate in enumerate(profiles)
            if isinstance(candidate, dict) and candidate.get("match") == binding
        ),
        None,
    )
    saved_profile = {"match": binding, **profile}
    if existing_index is not None:
        saved_profile = _merge(dict(profiles[existing_index]), saved_profile)
        if not replace_existing:
            return {
                "status": "profile_exists",
                "project": {"id": project.get("id"), "identifier": project.get("identifier"), "name": project.get("name")},
                "profile": _profile_view(saved_profile),
                "requires_replace_existing": True,
                "note": "An override already exists for this project. Set replace_existing=true to update it.",
            }

    result = {
        "project": {"id": project.get("id"), "identifier": project.get("identifier"), "name": project.get("name")},
        "profile": _profile_view(saved_profile),
        "user_profile_path": str(_profile_override_path()),
    }
    if not confirm:
        return {
            "status": "preview",
            **result,
            "note": "No profile was saved. Set confirm=true after reviewing this preview.",
        }

    if existing_index is None:
        profiles.append(saved_profile)
    else:
        profiles[existing_index] = saved_profile
    _write_json(_profile_override_path(), user_config)
    return {"status": "saved", **result, "note": "The local workflow profile was saved. Plane data was not changed."}


@mcp.tool()
def create_standardization_plan(project_id: str, expires_in_hours: int = 24) -> dict[str, Any]:
    """Create and save a read-only cleanup proposal. The plan does not change Plane until apply_standardization_plan is confirmed."""
    if isinstance(expires_in_hours, bool) or not isinstance(expires_in_hours, int) or not 1 <= expires_in_hours <= 168:
        raise PlaneWorkflowError("expires_in_hours must be a whole number from 1 to 168.")
    api = PlaneApi(_find_plane_settings())
    profile, project = _resolve_profile(api, project_id)
    items, total_count = api.work_items(project_id)
    actions, advisories = _build_standardization_actions(items, api.labels(project_id), profile)
    now = _utc_now()
    plan = {
        "version": 1,
        "id": str(uuid4()),
        "created_at": now.isoformat(),
        "expires_at": (now + timedelta(hours=expires_in_hours)).isoformat(),
        "workspace": api.workspace,
        "project": {"id": project.get("id"), "identifier": project.get("identifier"), "name": project.get("name")},
        "profile": _profile_view(profile),
        "work_items_checked": total_count if total_count is not None else len(items),
        "actions": actions,
        "advisories": advisories,
    }
    _write_plan(plan)
    return {
        "status": "planned",
        "plan_id": plan["id"],
        "expires_at": plan["expires_at"],
        "project": plan["project"],
        "work_items_checked": plan["work_items_checked"],
        "actions": actions,
        "advisories": advisories,
        "note": "This plan is saved locally and has not changed Plane. Review it, then call apply_standardization_plan with confirm=true.",
    }


@mcp.tool()
def get_standardization_plan(plan_id: str) -> dict[str, Any]:
    """Read a saved standardization plan without changing Plane."""
    plan = _read_plan(plan_id)
    return {
        "status": "expired" if _plan_expired(plan) else "planned",
        "plan": plan,
        "note": "This is a saved proposal. It has not changed Plane.",
    }


@mcp.tool()
def apply_standardization_plan(plan_id: str, confirm: bool = False) -> dict[str, Any]:
    """Preview or apply a saved standardization plan. Set confirm=true only after reviewing its proposed actions."""
    plan = _read_plan(plan_id)
    if _plan_expired(plan):
        return {
            "status": "expired",
            "plan_id": plan_id,
            "expires_at": plan.get("expires_at"),
            "note": "The plan has expired. Create a fresh plan so its checks reflect the current backlog.",
        }
    if not confirm:
        return {
            "status": "preview",
            "plan_id": plan_id,
            "expires_at": plan.get("expires_at"),
            "actions": plan.get("actions", []),
            "advisories": plan.get("advisories", []),
            "note": "No Plane data was changed. Set confirm=true to apply the saved actions.",
        }

    project_data = plan.get("project")
    if not isinstance(project_data, dict) or not _text(str(project_data.get("id", ""))):
        raise PlaneWorkflowError("The saved plan is missing its Plane project.")
    project_id = str(project_data["id"])
    api = PlaneApi(_find_plane_settings())
    profile, project = _resolve_profile(api, project_id)
    if plan.get("workspace") != api.workspace or project.get("identifier") != project_data.get("identifier"):
        raise PlaneWorkflowError("This plan was created for a different Plane workspace or project and cannot be applied here.")

    labels = api.labels(project_id)
    applied: list[dict[str, Any]] = []
    skipped_stale: list[dict[str, Any]] = []
    failed: list[dict[str, Any]] = []
    for action in plan.get("actions", []):
        if not isinstance(action, dict):
            continue
        work_item_id = _text(str(action.get("work_item_id", "")))
        changes = action.get("changes")
        if not work_item_id or not isinstance(changes, dict):
            failed.append({"work_item_id": work_item_id or None, "reason": "invalid_saved_action"})
            continue
        try:
            current = api.work_item(project_id, work_item_id)
            if action.get("fingerprint") != _item_fingerprint(current):
                skipped_stale.append({"work_item": _work_item_summary(current), "reason": "changed_since_plan"})
                continue
            payload: dict[str, Any] = {}
            for field in ("name", "priority"):
                if field in changes:
                    payload[field] = changes[field]
            ensure_type_label = changes.get("ensure_type_label")
            if isinstance(ensure_type_label, dict):
                label_name = _text(str(ensure_type_label.get("name", "")))
                work_item_type = _text(str(ensure_type_label.get("type", ""))).casefold()
                if not label_name or work_item_type not in VALID_TYPES:
                    failed.append({"work_item_id": work_item_id, "reason": "invalid_type_label_action"})
                    continue
                color_value = profile.get("type_label_colors", {}).get(work_item_type)
                label = _ensure_label(
                    api,
                    project_id,
                    labels,
                    label_name,
                    description=f"{work_item_type.title()} work item.",
                    color=_text(color_value) if isinstance(color_value, str) else None,
                )
                label_ids = _label_ids(current)
                if str(label.get("id")) not in label_ids:
                    payload["labels"] = [*label_ids, label["id"]]
            updated = api.update_work_item(project_id, work_item_id, payload) if payload else current
            applied.append({"work_item": _work_item_summary(updated), "changes": changes})
        except PlaneWorkflowError as error:
            failed.append({"work_item_id": work_item_id, "reason": str(error)})
    return {
        "status": "applied" if not failed else "partially_applied",
        "plan_id": plan_id,
        "applied": applied,
        "skipped_stale": skipped_stale,
        "failed": failed,
        "note": "Items changed after the plan was created were skipped and left untouched.",
    }


@mcp.tool()
def find_duplicate_candidates(
    project_id: str,
    title: str,
    min_score: float = 0.55,
    max_results: int = 5,
) -> dict[str, Any]:
    """Find potentially duplicate Plane work items by title similarity without changing Plane."""
    if not 0.0 <= min_score <= 1.0:
        raise PlaneWorkflowError("min_score must be between 0 and 1.")
    if isinstance(max_results, bool) or not isinstance(max_results, int) or not 1 <= max_results <= 20:
        raise PlaneWorkflowError("max_results must be a whole number from 1 to 20.")
    candidate_title = _text(title)
    if not candidate_title:
        raise PlaneWorkflowError("title is required.")
    api = PlaneApi(_find_plane_settings())
    items, _ = api.work_items(project_id)
    candidates = _duplicate_candidates(items, candidate_title, min_score=min_score)[:max_results]
    return {
        "status": "candidates",
        "title": candidate_title,
        "min_score": min_score,
        "candidates": candidates,
        "note": "Similarity is a review signal, not proof that two work items are duplicates.",
    }


@mcp.tool()
def find_work_items(project_id: str, query: str, max_results: int = 10) -> dict[str, Any]:
    """Find Plane work items by their title, UUID, or project reference such as PROJECT-12 without changing Plane."""
    if isinstance(max_results, bool) or not isinstance(max_results, int) or not 1 <= max_results <= 20:
        raise PlaneWorkflowError("max_results must be a whole number from 1 to 20.")
    search_query = _text(query)
    if not search_query:
        raise PlaneWorkflowError("query is required.")
    api = PlaneApi(_find_plane_settings())
    project = api.project(project_id)
    items, _ = api.work_items(project_id)
    results = _work_item_search_results(items, search_query, project_identifier=_text(str(project.get("identifier", ""))) or None)
    return {
        "status": "results",
        "query": search_query,
        "work_items": results[:max_results],
        "note": "This is a read-only lookup. Use the returned work-item id for a targeted update.",
    }


@mcp.tool()
def add_work_item_evidence_links(
    project_id: str,
    work_item_id: str,
    evidence: list[dict[str, str]],
    note: str | None = None,
    confirm: bool = False,
) -> dict[str, Any]:
    """Preview or attach validated evidence links to one work item. Set confirm=true to create the links."""
    normalized_links = _normalize_evidence_links(evidence)
    note_text = _text(note)
    if len(note_text) > 2000:
        raise PlaneWorkflowError("Evidence notes must be 2,000 characters or fewer.")
    if not confirm:
        return {
            "status": "preview",
            "work_item_id": work_item_id,
            "evidence": normalized_links,
            "note": note_text or None,
            "message": "No Plane data was changed. Set confirm=true to attach these links.",
        }

    api = PlaneApi(_find_plane_settings())
    existing_urls = {
        _text(str(link.get("url", "")))
        for link in api.work_item_links(project_id, work_item_id)
        if _text(str(link.get("url", "")))
    }
    created: list[dict[str, Any]] = []
    skipped: list[str] = []
    for link in normalized_links:
        url = str(link["url"])
        if url in existing_urls:
            skipped.append(url)
            continue
        created_link = api.create_work_item_link(project_id, work_item_id, url=url, title=link.get("title"))
        created.append({"id": created_link.get("id"), "url": url, "title": link.get("title")})
    note_updated = False
    if note_text:
        existing = api.work_item(project_id, work_item_id)
        api.update_work_item(
            project_id,
            work_item_id,
            {"description_html": _append_evidence_note(existing.get("description_html"), note_text)},
        )
        note_updated = True
    return {
        "status": "attached",
        "work_item_id": work_item_id,
        "created": created,
        "already_present": skipped,
        "note_updated": note_updated,
    }


@mcp.tool()
def upload_work_item_attachment(
    project_id: str,
    work_item_id: str,
    file_path: str,
    max_size_mb: int = 25,
    confirm: bool = False,
) -> dict[str, Any]:
    """Preview or upload one local file as a Plane attachment. Set confirm=true to upload the file."""
    metadata = _attachment_metadata(file_path, max_size_mb)
    preview = {
        "work_item_id": work_item_id,
        "attachment": {"name": metadata["name"], "size": metadata["size"], "type": metadata["type"]},
    }
    if not confirm:
        return {
            "status": "preview",
            **preview,
            "message": "No file was uploaded. Set confirm=true to attach this file to Plane.",
        }
    try:
        file_bytes = metadata["path"].read_bytes()
    except OSError as error:
        raise PlaneWorkflowError("The attachment file could not be read.") from error
    api = PlaneApi(_find_plane_settings())
    attachment = api.upload_work_item_attachment(
        project_id,
        work_item_id,
        name=metadata["name"],
        content_type=metadata["type"],
        file_bytes=file_bytes,
    )
    return {
        "status": "uploaded",
        **preview,
        "attachment_id": attachment.get("id"),
        "message": "The file was uploaded to the work item.",
    }


@mcp.tool()
def create_standard_work_item(
    project_id: str,
    outcome: str,
    acceptance_criteria: list[str],
    work_item_type: Literal["bug", "improvement", "task"] = "task",
    context: str | None = None,
    module_name: str | None = None,
    surface: str | None = None,
    scope: str | None = None,
    priority: Literal["urgent", "high", "medium", "low", "none"] | None = None,
    current_behavior: str | None = None,
    expected_behavior: str | None = None,
    additional_labels: list[str] | None = None,
    title_parts: list[str] | None = None,
    allow_create_module: bool = False,
    module_description: str | None = None,
    allow_duplicate: bool = False,
    assignee_ids: list[str] | None = None,
    state_id: str | None = None,
    estimate: int | str | None = None,
    start_date: str | None = None,
    target_date: str | None = None,
    cycle_id: str | None = None,
    release_id: str | None = None,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Create a structured Plane work item with labels, duplicate review, optional module/cycle assignment, and planning fields."""
    if work_item_type not in VALID_TYPES:
        raise PlaneWorkflowError("work_item_type must be bug, improvement, or task.")
    selected_assignees = _validate_id_list(assignee_ids, "assignee_ids")
    selected_state = _text(state_id) or None
    selected_cycle = _text(cycle_id) or None
    selected_release = _text(release_id) or None
    selected_estimate = _validate_estimate(estimate)
    selected_start_date = _validate_date(start_date, "start_date")
    selected_target_date = _validate_date(target_date, "target_date")
    api = PlaneApi(_find_plane_settings())
    profile, _ = _resolve_profile(api, project_id)
    _validate_workflow_selection(
        api,
        project_id,
        assignee_ids=selected_assignees,
        state_id=selected_state,
        cycle_id=selected_cycle,
        release_id=selected_release,
    )
    title = _build_title(profile, context=context, module=module_name, surface=surface, outcome=outcome, title_parts=title_parts)
    work_items, _ = api.work_items(project_id)
    duplicate = _duplicate(work_items, title)
    if duplicate and not allow_duplicate:
        return {"status": "duplicate_detected", "title": title, "duplicate": _work_item_summary(duplicate)}
    similar = _duplicate_candidates(work_items, title, min_score=0.78)
    if similar and not allow_duplicate:
        return {
            "status": "similarity_review_required",
            "title": title,
            "candidates": similar[:5],
            "note": "Review these similar work items, or set allow_duplicate=true when a separate item is intentional.",
        }

    selected_priority = priority or profile.get("default_priority", "medium")
    if selected_priority not in VALID_PRIORITIES:
        raise PlaneWorkflowError("priority must be urgent, high, medium, low, or none.")
    labels = api.labels(project_id)
    by_name = {_text(str(label.get("name", ""))).casefold(): label for label in labels}
    requested_labels = [_text(name) for name in additional_labels or [] if _text(name)]
    missing_labels = [name for name in requested_labels if name.casefold() not in by_name]
    if missing_labels:
        raise PlaneWorkflowError(f"Requested labels do not exist: {', '.join(missing_labels)}.")
    description_html = _render_description(
        work_item_type,
        outcome=outcome,
        current_behavior=current_behavior,
        expected_behavior=expected_behavior,
        scope=scope,
        acceptance_criteria=acceptance_criteria,
    )
    workflow_payload = _workflow_field_payload(
        assignee_ids=selected_assignees,
        state_id=selected_state,
        estimate=selected_estimate,
        start_date=selected_start_date,
        target_date=selected_target_date,
    )
    workflow_summary = {
        "assignee_ids": selected_assignees or [],
        "state_id": selected_state,
        "estimate": selected_estimate,
        "start_date": selected_start_date,
        "target_date": selected_target_date,
        "cycle_id": selected_cycle,
    }
    if dry_run:
        preview = {
            "title": title,
            "priority": selected_priority,
            "module": module_name,
            "type": work_item_type,
            "labels": requested_labels + ([profile.get("type_labels", {}).get(work_item_type, work_item_type.title())] if work_item_type != "task" else []),
            "description_html": description_html,
            "workflow": workflow_summary,
        }
        return {"status": "preview", "work_item": preview, "note": "No Plane data was changed."}

    module = _module(api, project_id, module_name, allow_create=allow_create_module, description=module_description)
    type_label = _ensure_type_label(api, project_id, labels, profile, work_item_type)
    label_ids = [by_name[name.casefold()]["id"] for name in requested_labels]
    if type_label:
        label_ids.append(type_label["id"])

    item = api.create_work_item(
        project_id,
        {"name": title, "description_html": description_html, "priority": selected_priority, "labels": label_ids or None, **workflow_payload},
    )
    if module:
        api.attach_to_module(project_id, module["id"], [item["id"]])
    if selected_cycle:
        api.attach_to_cycle(project_id, selected_cycle, [item["id"]])
    return {
        "status": "created",
        "work_item": _work_item_summary(item),
        "module": {"id": module.get("id"), "name": module.get("name")} if module else None,
        "labels": requested_labels + ([type_label.get("name")] if type_label else []),
        "workflow": workflow_summary,
    }


@mcp.tool()
def update_standard_work_item(
    project_id: str,
    work_item_id: str,
    outcome: str | None = None,
    acceptance_criteria: list[str] | None = None,
    work_item_type: Literal["bug", "improvement", "task"] | None = None,
    context: str | None = None,
    module_name: str | None = None,
    surface: str | None = None,
    scope: str | None = None,
    priority: Literal["urgent", "high", "medium", "low", "none"] | None = None,
    current_behavior: str | None = None,
    expected_behavior: str | None = None,
    additional_labels: list[str] | None = None,
    title_parts: list[str] | None = None,
    replace_description: bool = False,
    allow_create_module: bool = False,
    module_description: str | None = None,
    assignee_ids: list[str] | None = None,
    state_id: str | None = None,
    estimate: int | str | None = None,
    start_date: str | None = None,
    target_date: str | None = None,
    cycle_id: str | None = None,
    release_id: str | None = None,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Preview or update a specific Plane work item while preserving labels and description unless a structured replacement is requested."""
    if work_item_type is not None and work_item_type not in VALID_TYPES:
        raise PlaneWorkflowError("work_item_type must be bug, improvement, or task.")
    selected_assignees = _validate_id_list(assignee_ids, "assignee_ids")
    selected_state = _text(state_id) or None
    selected_cycle = _text(cycle_id) or None
    selected_release = _text(release_id) or None
    selected_estimate = _validate_estimate(estimate)
    selected_start_date = _validate_date(start_date, "start_date")
    selected_target_date = _validate_date(target_date, "target_date")
    api = PlaneApi(_find_plane_settings())
    profile, _ = _resolve_profile(api, project_id)
    _validate_workflow_selection(
        api,
        project_id,
        assignee_ids=selected_assignees,
        state_id=selected_state,
        cycle_id=selected_cycle,
        release_id=selected_release,
    )
    existing = api.work_item(project_id, work_item_id)
    payload: dict[str, Any] = {}
    if priority:
        if priority not in VALID_PRIORITIES:
            raise PlaneWorkflowError("priority must be urgent, high, medium, low, or none.")
        payload["priority"] = priority
    if outcome:
        payload["name"] = _build_title(profile, context=context, module=module_name, surface=surface, outcome=outcome, title_parts=title_parts)
    if replace_description:
        if not outcome or not acceptance_criteria:
            raise PlaneWorkflowError("Replacing a description requires outcome and acceptance_criteria.")
        selected_type = work_item_type or "task"
        payload["description_html"] = _render_description(selected_type, outcome=outcome, current_behavior=current_behavior, expected_behavior=expected_behavior, scope=scope, acceptance_criteria=acceptance_criteria)

    labels = api.labels(project_id)
    by_name = {_text(str(label.get("name", ""))).casefold(): label for label in labels}
    preserved_ids = _label_ids(existing)
    requested_labels = [_text(name) for name in additional_labels or [] if _text(name)]
    missing_labels = [name for name in requested_labels if name.casefold() not in by_name]
    if missing_labels:
        raise PlaneWorkflowError(f"Requested labels do not exist: {', '.join(missing_labels)}.")
    for name in requested_labels:
        preserved_ids.append(by_name[name.casefold()]["id"])
    type_label_preview: dict[str, Any] | None = None
    if work_item_type:
        type_label_name = _text(str(profile.get("type_labels", {}).get(work_item_type, work_item_type.title())))
        type_label = _find_by_name(labels, type_label_name)
        if not type_label and dry_run:
            type_label_preview = {"name": type_label_name, "will_create": True}
        elif not type_label:
            type_label = _ensure_type_label(api, project_id, labels, profile, work_item_type)
        if type_label:
            preserved_ids.append(type_label["id"])
    if requested_labels or work_item_type:
        payload["labels"] = list(dict.fromkeys(preserved_ids))
    payload.update(
        _workflow_field_payload(
            assignee_ids=selected_assignees,
            state_id=selected_state,
            estimate=selected_estimate,
            start_date=selected_start_date,
            target_date=selected_target_date,
        )
    )
    if not payload and not module_name and not selected_cycle:
        raise PlaneWorkflowError("Provide at least one field to update.")

    module_preview = _module_preview(
        api,
        project_id,
        module_name,
        allow_create=allow_create_module,
        description=module_description,
    )
    workflow_summary = {
        "assignee_ids": selected_assignees,
        "state_id": selected_state,
        "estimate": selected_estimate,
        "start_date": selected_start_date,
        "target_date": selected_target_date,
        "cycle_id": selected_cycle,
    }
    if dry_run:
        return {
            "status": "preview",
            "work_item": _work_item_summary(existing),
            "changes": payload,
            "module": module_preview,
            "type_label": type_label_preview,
            "workflow": workflow_summary,
            "note": "No Plane data was changed. Set dry_run=false to apply these updates.",
        }

    updated = api.update_work_item(project_id, work_item_id, payload) if payload else existing
    module = _module(api, project_id, module_name, allow_create=allow_create_module, description=module_description)
    if module:
        api.attach_to_module(project_id, module["id"], [work_item_id])
    if selected_cycle:
        api.attach_to_cycle(project_id, selected_cycle, [work_item_id])
    return {
        "status": "updated",
        "work_item": _work_item_summary(updated),
        "module": {"id": module.get("id"), "name": module.get("name")} if module else None,
        "workflow": workflow_summary,
    }


@mcp.tool()
def ensure_module(
    project_id: str,
    module_name: str,
    work_item_ids: list[str] | None = None,
    description: str | None = None,
    create_if_missing: bool = False,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Preview or find an existing module, then explicitly create or assign it when requested."""
    api = PlaneApi(_find_plane_settings())
    if dry_run:
        module_preview = _module_preview(
            api,
            project_id,
            module_name,
            allow_create=create_if_missing,
            description=description,
        )
        return {
            "status": "preview",
            "module": module_preview,
            "assigned_work_item_ids": work_item_ids or [],
            "note": "No Plane data was changed. Set dry_run=false to create or assign this module.",
        }
    module = _module(api, project_id, module_name, allow_create=create_if_missing, description=description)
    if work_item_ids:
        api.attach_to_module(project_id, module["id"], work_item_ids)
    return {"module": {"id": module.get("id"), "name": module.get("name")}, "assigned_work_item_ids": work_item_ids or []}


@mcp.tool()
def audit_work_items(project_id: str) -> dict[str, Any]:
    """Audit Plane work items without changing them. Reports structural and quality gaps for a human-approved cleanup."""
    api = PlaneApi(_find_plane_settings())
    profile, _ = _resolve_profile(api, project_id)
    labels = api.labels(project_id)
    type_labels = _type_labels(profile)
    labels_by_name = {_text(str(label.get("name", ""))).casefold(): label for label in labels}
    type_label_ids = {
        work_item_type: str(labels_by_name[label_name.casefold()]["id"])
        for work_item_type, label_name in type_labels.items()
        if label_name.casefold() in labels_by_name and labels_by_name[label_name.casefold()].get("id")
    }
    modules = api.modules(project_id)
    assigned_ids: set[str] = set()
    module_findings: list[dict[str, Any]] = []
    for module in modules:
        module_items = api.module_work_items(project_id, module["id"])
        module_ids = {str(item.get("id")) for item in module_items if item.get("id")}
        assigned_ids.update(module_ids)
        if not module_ids:
            module_findings.append(
                {
                    "module": {"id": module.get("id"), "name": module.get("name")},
                    "findings": [_audit_finding("orphaned_module", "advisory", "The module has no assigned work items.")],
                }
            )
    states, _ = _optional_options(lambda: api.states(project_id))
    state_types = {str(state["id"]): str(state.get("type", "")) for state in states if state.get("id")}
    stale_after_days = profile.get("stale_after_days", 90)
    if not isinstance(stale_after_days, int) or isinstance(stale_after_days, bool) or stale_after_days < 1:
        stale_after_days = 90
    items, total_count = api.work_items(project_id)
    findings: list[dict[str, Any]] = []
    severity_counts = {"error": 0, "warning": 0, "advisory": 0}
    for item in items:
        item_findings = _quality_findings_for_item(
            item,
            type_labels=type_labels,
            type_label_ids=type_label_ids,
            assigned_ids=assigned_ids,
            state_types=state_types,
            stale_after_days=stale_after_days,
        )
        for finding in item_findings:
            severity_counts[finding["severity"]] += 1
        if item_findings:
            findings.append({"work_item": _work_item_summary(item), "findings": item_findings})
    for module_finding in module_findings:
        for finding in module_finding["findings"]:
            severity_counts[finding["severity"]] += 1
    return {
        "status": "audit",
        "work_items_checked": total_count if total_count is not None else len(items),
        "summary": {
            "work_items_with_findings": len(findings),
            "modules_with_findings": len(module_findings),
            "by_severity": severity_counts,
        },
        "findings": findings,
        "module_findings": module_findings,
        "note": "No Plane data was changed. Review findings before applying updates.",
    }


@mcp.tool()
def export_work_items_report(
    project_id: str,
    format: Literal["docx", "pdf"],
    filters: dict[str, Any] | None = None,
    layout: dict[str, Any] | None = None,
    title: str | None = None,
    output_directory: str | None = None,
) -> dict[str, Any]:
    """Export filtered Plane work items as a dynamic Word or PDF report without changing Plane.

    Example filters: {"state_names": ["Backlog", "In Progress"]}. Example layout:
    {"group_by": "state", "columns": ["identifier", "title", "state", "priority"]}.
    """
    from reports import ReportError, export_work_items_report as export_report

    try:
        return export_report(
            PlaneApi(_find_plane_settings()),
            project_id=project_id,
            report_format=format,
            title=title,
            filters=filters,
            layout=layout,
            output_directory=output_directory,
        )
    except ReportError as error:
        raise PlaneWorkflowError(str(error)) from error


def _self_test() -> None:
    generic = {"title_template": ["{context}", "{module}", "{surface}", "{outcome}"]}
    prefixed = {"title_template": ["EXAMPLE", "{module}", "{surface}", "{outcome}"]}
    assert _build_title(generic, context="Web", module="Search", surface="Results", outcome="Preserve filters", title_parts=None) == "Web | Search | Results | Preserve filters"
    assert _build_title(prefixed, context=None, module="Media", surface="Player", outcome="Enable captions", title_parts=None) == "EXAMPLE | Media | Player | Enable captions"
    description = _render_description("bug", outcome="", current_behavior="It fails", expected_behavior="It succeeds", scope=None, acceptance_criteria=["The retry completes"])
    assert "Current behavior" in description and "Acceptance criteria" in description
    assert _duplicate([{"name": "Web | Search | Preserve filters"}], "web|search|preserve filters") is not None
    assert _duplicate([{"name": "نمونه | بررسی"}], "نمونه|بررسی") is not None
    assert _title_similarity("EXAMPLE | Media | Player | Choose quality", "EXAMPLE | Media | Player | Let viewers choose quality") >= 0.78
    search_results = _work_item_search_results(
        [{"id": "work-1", "sequence_id": 12, "name": "EXAMPLE | Media | Player | Choose quality", "priority": "high"}],
        "EXAMPLE-12",
        project_identifier="EXAMPLE",
    )
    assert search_results[0]["work_item"]["id"] == "work-1"
    assert _validate_date("2026-07-28", "target_date") == "2026-07-28"
    assert _workflow_field_payload(assignee_ids=["member-1"], state_id="state-1", estimate=3, start_date="2026-07-28", target_date=None) == {
        "assignees": ["member-1"],
        "state": "state-1",
        "estimate_point": 3,
        "start_date": "2026-07-28",
    }
    assert _option_id({"member": {"id": "member-1"}}, member=True) == "member-1"
    assert _normalize_evidence_links([{"url": "https://example.com/proof", "title": "Proof"}])[0]["url"] == "https://example.com/proof"
    assert _attachment_metadata(str(PACKAGED_PROFILES), 1)["name"] == "profiles.json"
    assert "Evidence note" in _append_evidence_note("<p>Existing</p>", "Checked on device")
    quality_codes = {
        finding["code"]
        for finding in _quality_findings_for_item(
            {
                "id": "1",
                "name": "Bug | Fix",
                "priority": "none",
                "labels": [],
                "description_html": "<p>Details</p>",
                "state": "todo",
                "updated_at": "2000-01-01T00:00:00Z",
            },
            type_labels={"bug": "Bug"},
            type_label_ids={"bug": "label-bug"},
            assigned_ids=set(),
            state_types={"todo": "started"},
            stale_after_days=30,
        )
    }
    assert {"missing_priority", "missing_type_label", "missing_acceptance_criteria", "stale_work_item"}.issubset(quality_codes)
    assert _connection_probe(lambda: [{"id": "one"}]) == {"available": True, "count": 1}
    assert _validate_profile({"title_template": ["{module}", "{outcome}"], "stale_after_days": 90}) == []
    actions, advisories = _build_standardization_actions(
        [{"id": "1", "name": "Bug | Retry", "priority": "none", "labels": [], "updated_at": "2026-01-01T00:00:00Z"}],
        [],
        {"default_priority": "medium", "type_labels": {"bug": "Bug"}},
    )
    assert actions[0]["changes"]["name"] == "Retry" and actions[0]["changes"]["ensure_type_label"]["name"] == "Bug"
    assert "missing_description" in advisories[0]["findings"]
    assert _plan_expired({"expires_at": "2000-01-01T00:00:00+00:00"})
    print("Plane Workflow self-test passed.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--self-test", action="store_true")
    arguments = parser.parse_args()
    if arguments.self_test:
        _self_test()
    else:
        mcp.run()
