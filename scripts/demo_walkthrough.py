#!/usr/bin/env python3
"""Readable offline walkthrough: real server code, test fixture, never connects to Plane."""

from __future__ import annotations

import sys
from datetime import date
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
CORE = ROOT / "plugins" / "plane-workflow"
sys.path.insert(0, str(CORE))
sys.path.insert(0, str(CORE / "tests"))

from plane_workflow_mcp import server
from test_lifecycle import PROJECT_ID, _Api, _profile

BUG = {
    "project_id": PROJECT_ID,
    "outcome": "Prevent duplicate orders when checkout is retried",
    "work_item_type": "bug",
    "context": "Web",
    "surface": "Checkout",
    "current_behavior": "Retrying checkout after a timeout can create two orders.",
    "expected_behavior": "Retrying the same request creates only one order.",
    "scope": "Checkout retry handling and regression tests",
    "complexity": "small",
    "acceptance_criteria": [
        "Repeating the same request creates one order",
        "A failed first attempt can be retried",
        "The existing checkout flow still works",
    ],
}


def _day(value: str) -> str:
    return date.fromisoformat(value).strftime("%a %b %-d")


def walkthrough() -> list[tuple[str, str]]:
    """Return (kind, text) lines: kind is title, user, tool, out, ok, warn, or blank."""
    api = _Api()
    server._WORK_ITEM_CACHE.clear()

    def commit_then_time_out(project_id: str, payload: dict[str, object]) -> dict[str, object]:
        api.items.append({"id": "made-item", "sequence_id": 42, **payload})
        raise server.PlaneApiError("Plane did not respond to a write request.", outcome_unknown=True)

    with (
        patch.object(server, "PlaneApi", return_value=api),
        patch.object(server, "_find_plane_settings", return_value=None),
        patch.object(server, "_load_profile_config", return_value=_profile()),
        patch.object(server, "load_stored_plane_settings", return_value=None),
        patch.object(server, "_today", return_value=date(2026, 9, 4)),
        patch.object(server.requests.sessions.Session, "request", side_effect=RuntimeError("Network disabled in demo")),
    ):
        preview = server.create_standard_work_item(**BUG, dry_run=True)
        api.create_work_item = commit_then_time_out  # type: ignore[method-assign]
        created = server.create_standard_work_item(**BUG)
        retried = server.create_standard_work_item(**BUG)

    item = preview["work_item"]
    plan = item["workflow"]
    if preview["status"] != "preview" or created["status"] != "already_created" or retried["status"] != "duplicate_detected":
        raise RuntimeError("Demo flow did not produce the expected results")
    reference = f"TEST-{created['work_item']['sequence_id']}"
    lines = [
        ("title", "Offline demo · real plane-workflow code · synthetic data"),
        ("blank", ""),
        ("user", "Checkout retries can create two orders. Draft a bug, preview first."),
        ("blank", ""),
        ("tool", "create_standard_work_item(dry_run=true)"),
        ("out", f"Title     {item['title']}"),
        ("out", f"Type      {item['type'].title()} · {item['priority']} · {', '.join(item['labels'])}"),
        ("out", f"Plan      {plan['planning_mode']} · {plan['complexity']} · {_day(plan['start_date'])} → {_day(plan['target_date'])}"),
        *[("out", f"{'Accept' if index == 0 else '':<10}✓ {text}") for index, text in enumerate(BUG["acceptance_criteria"])],
        ("ok", "Preview only. No Plane data changed."),
        ("blank", ""),
        ("user", "Looks right. Create it."),
        ("blank", ""),
        ("tool", "create_standard_work_item"),
        ("warn", "Plane timed out after the write."),
        ("ok", f"Found it by external_id → {reference}, status already_created"),
        ("blank", ""),
        ("tool", "create_standard_work_item   (agent retries anyway)"),
        ("ok", f"duplicate_detected → {reference}. Nothing created twice."),
    ]
    return lines


def main() -> None:
    for kind, text in walkthrough():
        prefix = {"user": "> ", "tool": "● ", "out": "  ", "ok": "  ✓ ", "warn": "  ! "}.get(kind, "")
        print(prefix + text)


if __name__ == "__main__":
    main()
