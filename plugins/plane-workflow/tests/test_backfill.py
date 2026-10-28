from __future__ import annotations

import io
import os
import subprocess
import tempfile
import unittest
from contextlib import redirect_stdout
from datetime import date
from pathlib import Path
from unittest.mock import patch

from plane_workflow_mcp import backfill, cli, server
from test_lifecycle import PROJECT_ID, _Api, _profile

COMMITS = [
    ("2026-09-03T10:00:00+00:00", "auth/login.py", "feat(auth): add login form"),
    ("2026-09-04T16:00:00+00:00", "auth/login.py", "fix(auth): handle an empty password"),
    ("2026-09-12T11:00:00+00:00", "billing/export.py", "feat(billing): export invoices as CSV"),
    ("2026-09-14T09:00:00+00:00", "README.md", "docs: describe invoice export"),
]
MONDAY_TO_FRIDAY = {0, 1, 2, 3, 4}


def _git(repo: Path, *arguments: str, when: str | None = None) -> None:
    environment = {**os.environ, "GIT_AUTHOR_NAME": "Ava", "GIT_AUTHOR_EMAIL": "ava@example.test", "GIT_COMMITTER_NAME": "Ava", "GIT_COMMITTER_EMAIL": "ava@example.test"}
    if when:
        environment |= {"GIT_AUTHOR_DATE": when, "GIT_COMMITTER_DATE": when}
    subprocess.run(["git", "-C", str(repo), *arguments], check=True, capture_output=True, env=environment)


def _fixture_repo(directory: str) -> Path:
    repo = Path(directory) / "repo"
    repo.mkdir()
    _git(repo, "init", "-q", "-b", "main")
    for when, path, subject in COMMITS:
        target = repo / path
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("a", encoding="utf-8") as handle:
            handle.write(f"{subject}\n" * 5)
        _git(repo, "add", path)
        _git(repo, "commit", "-q", "-m", subject, when=when)
    return repo


class _BackfillApi(_Api):
    """A project that keeps every created item, so lifecycle calls see real state."""

    def __init__(self) -> None:
        super().__init__()
        self.stored: dict[str, dict[str, object]] = {}
        self.comments: dict[str, list[dict[str, object]]] = {}
        self.modules_data: list[dict[str, object]] = []

    def work_items(self, project_id: str) -> tuple[list[dict[str, object]], int]:
        return list(self.stored.values()), len(self.stored)

    def create_work_item(self, project_id: str, payload: dict[str, object]) -> dict[str, object]:
        self.events.append("create-item")
        item = {"id": f"item-{len(self.stored) + 1}", "sequence_id": len(self.stored) + 1, "project": PROJECT_ID, **payload}
        self.stored[str(item["id"])] = item
        return dict(item)

    def work_item(self, project_id: str, work_item_id: str) -> dict[str, object]:
        return dict(self.stored[work_item_id])

    def update_work_item(self, project_id: str, work_item_id: str, payload: dict[str, object]) -> dict[str, object]:
        self.events.append("update-state" if "state" in payload else "update-item")
        self.stored[work_item_id].update(payload)
        return dict(self.stored[work_item_id])

    def work_item_comments(self, project_id: str, work_item_id: str) -> list[dict[str, object]]:
        return self.comments.setdefault(work_item_id, [])

    def create_work_item_comment(self, project_id: str, work_item_id: str, payload: dict[str, object]) -> dict[str, object]:
        self.events.append("comment")
        comment = {"id": f"comment-{work_item_id}", **payload}
        self.comments.setdefault(work_item_id, []).append(comment)
        return comment

    def modules(self, project_id: str) -> list[dict[str, object]]:
        return self.modules_data

    def create_module(self, project_id: str, payload: dict[str, object]) -> dict[str, object]:
        module = {"id": f"module-{len(self.modules_data) + 1}", **payload}
        self.modules_data.append(module)
        return module

    def attach_to_module(self, project_id: str, module_id: str, work_item_ids: list[str]) -> None:
        self.events.append("module")


class ProposalTests(unittest.TestCase):
    def setUp(self) -> None:
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.repo = _fixture_repo(self.directory.name)
        self.commits = backfill.read_commits(self.repo, since="2026-09-01")

    def test_commits_are_grouped_by_scope_and_dated_on_business_days(self) -> None:
        items = backfill.propose_items(self.commits, weekdays=MONDAY_TO_FRIDAY)

        by_module = {item["module"]: item for item in items}
        self.assertEqual(set(by_module), {"auth", "billing", "General"})
        auth = by_module["auth"]
        self.assertEqual([commit["subject"] for commit in auth["commits"]], [subject for _, _, subject in COMMITS[:2]])
        self.assertEqual((auth["start_date"], auth["target_date"]), ("2026-09-03", "2026-09-04"))
        # Saturday work is planned on the next business day.
        self.assertEqual(by_module["billing"]["start_date"], "2026-09-14")
        self.assertEqual(by_module["billing"]["title"], "Export invoices as CSV")
        self.assertEqual(by_module["billing"]["idempotency_key"], f"git:{self.commits[2].hash}")
        self.assertEqual([item["id"] for item in items], ["1", "2", "3"])

    def test_configured_week_and_module_map_are_respected(self) -> None:
        saturday_to_wednesday = {5, 6, 0, 1, 2}
        items = backfill.propose_items(self.commits[:2], weekdays=saturday_to_wednesday, module_map={"auth/": "Accounts"})

        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["module"], "Accounts")
        # Thursday and Friday are not business days in this week.
        self.assertEqual((items[0]["start_date"], items[0]["target_date"]), ("2026-09-05", "2026-09-05"))

    def test_a_long_pause_splits_one_scope_into_two_items(self) -> None:
        items = backfill.propose_items(self.commits[:2], weekdays=MONDAY_TO_FRIDAY, max_gap_days=0)

        self.assertEqual([len(item["commits"]) for item in items], [1, 1])

    def test_completion_record_cites_commits_and_claims_no_tests(self) -> None:
        item = backfill.propose_items(self.commits[:2], weekdays=MONDAY_TO_FRIDAY)[0]
        record = backfill.completion_record(item)

        self.assertIn("2 commits from 2026-09-03 to 2026-09-04", record["summary"])
        self.assertIn("No tests were run", record["verification"][0])
        self.assertTrue(record["implementation_notes"][0].startswith(self.commits[0].hash[:10]))


class BackfillToolTests(unittest.TestCase):
    def setUp(self) -> None:
        server._WORK_ITEM_CACHE.clear()
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.repo = _fixture_repo(self.directory.name)
        self.api = _BackfillApi()
        patches = patch.multiple(
            server,
            PlaneApi=lambda settings: self.api,
            _find_plane_settings=lambda: server.PlaneSettings("https://plane.example.test", "key", "workspace"),
            _load_profile_config=lambda: _profile("advisory"),
            _today=lambda timezone_name=None: date(2026, 9, 15),
        )
        patches.start()
        self.addCleanup(patches.stop)
        environment = patch.dict(os.environ, {"PLANE_WORKFLOW_PLAN_DIR": str(Path(self.directory.name) / "plans")})
        environment.start()
        self.addCleanup(environment.stop)

    def _plan(self, **overrides: object) -> dict[str, object]:
        return server.plan_git_backfill(repo_path=str(self.repo), since="2026-09-01", project_id=PROJECT_ID, **overrides)

    def test_planning_and_preview_never_write_to_plane(self) -> None:
        plan = self._plan()
        preview = server.apply_git_backfill(plan_id=plan["plan_id"], titles={"1": "Sign-in form"})

        self.assertEqual(plan["commits_read"], 4)
        self.assertEqual(preview["status"], "preview")
        self.assertEqual(preview["items"][0]["title"], "Sign-in form")
        self.assertEqual(preview["items"][0]["actions"], ["create", "start", "complete"])
        self.assertEqual(self.api.events, [])

    def test_apply_creates_starts_and_completes_with_commit_record(self) -> None:
        plan = self._plan()
        result = server.apply_git_backfill(plan_id=plan["plan_id"], allow_create_modules=True, skip=["3"], dry_run=False)

        self.assertEqual(result["status"], "applied")
        self.assertEqual([entry["status"] for entry in result["results"]], ["completed", "completed"])
        auth = self.api.stored["item-1"]
        self.assertEqual((auth["start_date"], auth["target_date"], auth["state"]), ("2026-09-03", "2026-09-04", "done-id"))
        comment = self.api.comments["item-1"][0]["comment_html"]
        commits = backfill.read_commits(self.repo, since="2026-09-01")
        self.assertIn(commits[0].hash[:10], comment)
        self.assertIn("No tests were run", comment)

    def test_rerun_is_reported_as_done_without_duplicates(self) -> None:
        plan = self._plan()
        server.apply_git_backfill(plan_id=plan["plan_id"], allow_create_modules=True, dry_run=False)
        creates = self.api.events.count("create-item")
        server._WORK_ITEM_CACHE.clear()

        again = self._plan()
        rerun = server.apply_git_backfill(plan_id=again["plan_id"], titles={"1": "Renamed after the first run"}, allow_create_modules=True, dry_run=False)

        self.assertTrue(all(item["in_plane"] for item in again["items"]))
        self.assertEqual({entry["status"] for entry in rerun["results"]}, {"already_completed"})
        self.assertEqual(self.api.events.count("create-item"), creates)

    def test_uncommitted_work_is_started_but_not_completed(self) -> None:
        (self.repo / "billing" / "export.py").write_text("work in progress\n", encoding="utf-8")
        plan = self._plan(include_uncommitted=True)
        wip = plan["items"][-1]
        result = server.apply_git_backfill(plan_id=plan["plan_id"], skip=["1", "2", "3"], allow_create_modules=True, dry_run=False)

        self.assertFalse(wip["committed"])
        self.assertEqual(result["results"][0]["status"], "started")
        self.assertEqual(self.api.stored["item-1"]["state"], "started-id")

    def test_failure_stops_and_reports_partial_progress(self) -> None:
        plan = self._plan()
        result = server.apply_git_backfill(plan_id=plan["plan_id"], dry_run=False)

        self.assertEqual(result["status"], "partial")
        self.assertIn("No module named", result["results"][0]["reason"])

    def test_cli_prints_the_plan_without_applying(self) -> None:
        output = io.StringIO()
        with redirect_stdout(output):
            code = cli.main(["backfill", "--repo", str(self.repo), "--since", "2026-09-01", "--project-id", PROJECT_ID])

        self.assertEqual(code, 0)
        self.assertIn("4 commits, 3 items", output.getvalue())
        self.assertIn("Nothing was written to Plane", output.getvalue())
        self.assertEqual(self.api.events, [])


if __name__ == "__main__":
    unittest.main()
