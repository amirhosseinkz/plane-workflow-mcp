#!/usr/bin/env python3
"""Readable offline backfill walkthrough: real server code, a synthetic git repo, never connects to Plane."""

from __future__ import annotations

import os
import sys
import tempfile
from datetime import date
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
CORE = ROOT / "plugins" / "plane-workflow"
sys.path.insert(0, str(CORE))
sys.path.insert(0, str(CORE / "tests"))

from plane_workflow_mcp import server
from test_backfill import _BackfillApi, _fixture_repo
from test_lifecycle import PROJECT_ID, _profile


def _day(value: str) -> str:
    return date.fromisoformat(value).strftime("%b %-d")


def walkthrough() -> list[tuple[str, str]]:
    """Return (kind, text) lines: kind is title, user, tool, out, ok, warn, or blank."""
    api = _BackfillApi()
    server._WORK_ITEM_CACHE.clear()
    with tempfile.TemporaryDirectory() as directory, patch.multiple(
        server,
        PlaneApi=lambda settings: api,
        _find_plane_settings=lambda: server.PlaneSettings("https://plane.example.test", "key", "workspace"),
        _load_profile_config=lambda: _profile("advisory"),
        load_stored_plane_settings=lambda *args, **kwargs: None,
        _today=lambda timezone_name=None: date(2026, 9, 15),
    ), patch.dict(os.environ, {"PLANE_WORKFLOW_PLAN_DIR": str(Path(directory) / "plans")}):
        repo = _fixture_repo(directory)
        plan = server.plan_git_backfill(repo_path=str(repo), since="2026-09-01", project_id=PROJECT_ID)
        renamed = {"1": "Sign-in form"}
        applied = server.apply_git_backfill(plan_id=plan["plan_id"], titles=renamed, allow_create_modules=True, dry_run=False)
        server._WORK_ITEM_CACHE.clear()
        again = server.plan_git_backfill(repo_path=str(repo), since="2026-09-01", project_id=PROJECT_ID)
        rerun = server.apply_git_backfill(plan_id=again["plan_id"], titles=renamed, allow_create_modules=True, dry_run=False)
        comment = api.comments["item-1"][0]["comment_html"]

    if applied["status"] != "applied" or {entry["status"] for entry in rerun["results"]} != {"already_completed"}:
        raise RuntimeError("Demo flow did not produce the expected results")
    if "No tests were run" not in comment:
        raise RuntimeError("Completion record must state that no tests ran")
    titles = {entry["id"]: entry["title"] for entry in applied["results"]}
    lines: list[tuple[str, str]] = [
        ("title", "Offline demo · real plane-workflow code · synthetic git repo"),
        ("blank", ""),
        ("user", "Put my git history since Sep 1 into Plane. Plan it first."),
        ("blank", ""),
        ("tool", "plan_git_backfill(since=\"2026-09-01\")"),
        ("out", f"{plan['commits_read']} commits → {len(plan['items'])} work items, dated on business days"),
    ]
    for item in plan["items"]:
        dates = f"{_day(item['start_date'])} → {_day(item['target_date'])}"
        lines.append(("out", f"{item['id']}  {dates:<16}{item['module']:<9} {item['title'][:30]:<31} {item['commits']} commit{'s' if item['commits'] != 1 else ''}"))
    lines += [
        ("ok", "Plan only. Nothing written to Plane."),
        ("blank", ""),
        ("user", "Call #1 \"Sign-in form\". Apply it."),
        ("blank", ""),
        ("tool", "apply_git_backfill(dry_run=false)"),
    ]
    for entry in applied["results"]:
        lines.append(("ok", f"TEST-{entry['work_item']['sequence_id']}  {titles[entry['id']][:30]:<31} created → started → done"))
    lines += [
        ("out", "Each completion comment lists its commits."),
        ("blank", ""),
        ("tool", "apply_git_backfill   (run again)"),
        ("ok", f"already_completed ×{len(rerun['results'])}. Nothing duplicated."),
    ]
    return lines


def main() -> None:
    for kind, text in walkthrough():
        prefix = {"user": "> ", "tool": "● ", "out": "  ", "ok": "  ✓ ", "warn": "  ! "}.get(kind, "")
        print(prefix + text)


if __name__ == "__main__":
    main()
