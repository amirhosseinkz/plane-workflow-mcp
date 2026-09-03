from __future__ import annotations

import asyncio
from datetime import date
import unittest
from unittest.mock import patch

import requests
import server


PROJECT_ID = "project-id"


def _profile(mode: str = "strict") -> dict[str, object]:
    return {
        "default": {
            "title_template": ["{context}", "{surface}", "{outcome}"],
            "default_priority": "medium",
            "type_labels": {"task": "Task", "bug": "Bug", "improvement": "Improvement"},
            "type_label_colors": {"task": "#6B7280"},
            "planning": {
                "mode": mode,
                "default_assignee_id": "member-id",
                "default_labels": ["Engineering"],
                "default_unstarted_state_id": "backlog-id",
                "default_started_state_id": "started-id",
                "default_completed_state_id": "done-id",
                "business_days": ["monday", "tuesday", "wednesday", "thursday", "friday"],
                "complexity": {
                    "small": {"estimate": "point-id", "lead_business_days": 2},
                },
            },
        },
        "profiles": [],
    }


class _Api:
    profile = None
    workspace = "workspace"

    def __init__(self) -> None:
        self.item: dict[str, object] = {
            "id": "item-id",
            "name": "Web | Player | Improve quality",
            "priority": "medium",
            "project": PROJECT_ID,
            "state": "started-id",
            "estimate_point": "point-id",
        }
        self.items: list[dict[str, object]] = []
        self.labels_data: list[dict[str, object]] = [
            {"id": "engineering-id", "name": "Engineering"},
            {"id": "task-label-id", "name": "Task"},
        ]
        self.comments_data: list[dict[str, object]] = []
        self.worklogs_data: list[dict[str, object]] = []
        self.events: list[str] = []

    @staticmethod
    def project(project_id: str) -> dict[str, object]:
        return {"id": project_id, "identifier": "TEST", "name": "Test"}

    @staticmethod
    def states(project_id: str) -> list[dict[str, object]]:
        return [
            {"id": "backlog-id", "name": "Backlog", "type": "backlog"},
            {"id": "started-id", "name": "In Progress", "type": "started"},
            {"id": "done-id", "name": "Done", "type": "completed"},
        ]

    @staticmethod
    def members(project_id: str) -> list[dict[str, object]]:
        return [{"member": {"id": "member-id", "display_name": "Ava"}}]

    @staticmethod
    def cycles(project_id: str) -> list[dict[str, object]]:
        return []

    @staticmethod
    def estimate(project_id: str) -> dict[str, object]:
        return {"id": "estimate-id", "name": "Points"}

    @staticmethod
    def estimate_points(project_id: str, estimate_id: str) -> list[dict[str, object]]:
        return [{"id": "point-id", "key": 2, "value": "2", "description": "Small"}]

    def work_items(self, project_id: str) -> tuple[list[dict[str, object]], int]:
        return self.items, len(self.items)

    def labels(self, project_id: str) -> list[dict[str, object]]:
        return self.labels_data

    def modules(self, project_id: str) -> list[dict[str, object]]:
        return []

    def work_item(self, project_id: str, work_item_id: str) -> dict[str, object]:
        return dict(self.item)

    def create_label(self, project_id: str, payload: dict[str, object]) -> dict[str, object]:
        label = {"id": f"label-{len(self.labels_data)}", **payload}
        self.labels_data.append(label)
        return label

    def create_work_item(self, project_id: str, payload: dict[str, object]) -> dict[str, object]:
        self.events.append("create-item")
        return {"id": "new-item", "sequence_id": 1, **payload}

    def update_work_item(self, project_id: str, work_item_id: str, payload: dict[str, object]) -> dict[str, object]:
        self.events.append("update-state" if "state" in payload else "update-item")
        self.item.update(payload)
        return dict(self.item)

    def work_item_comments(self, project_id: str, work_item_id: str) -> list[dict[str, object]]:
        return self.comments_data

    def create_work_item_comment(self, project_id: str, work_item_id: str, payload: dict[str, object]) -> dict[str, object]:
        self.events.append("comment")
        comment = {"id": "comment-id", **payload}
        self.comments_data.append(comment)
        return comment

    def worklogs(self, project_id: str, work_item_id: str) -> list[dict[str, object]]:
        return self.worklogs_data

    def create_worklog(self, project_id: str, work_item_id: str, payload: dict[str, object]) -> dict[str, object]:
        self.events.append("worklog")
        worklog = {"id": "worklog-id", **payload}
        self.worklogs_data.append(worklog)
        return worklog


class LifecycleTests(unittest.TestCase):
    def _patch_api(self, api: _Api, profile: dict[str, object] | None = None):
        return patch.multiple(
            server,
            PlaneApi=lambda settings: api,
            _find_plane_settings=lambda: server.PlaneSettings("https://plane.example.test", "key", "workspace"),
            _load_profile_config=lambda: profile or _profile(),
        )

    def test_strict_planning_applies_assignment_labels_estimate_and_business_dates(self) -> None:
        api = _Api()
        with self._patch_api(api), patch.object(server, "_today", return_value=date(2026, 9, 4)):
            result = server.create_standard_work_item(
                project_id=PROJECT_ID,
                outcome="Improve quality",
                acceptance_criteria=["Viewer can select a quality"],
                context="Web",
                surface="Player",
                scope="Quality selector only",
                complexity="small",
                dry_run=True,
            )

        workflow = result["work_item"]["workflow"]
        self.assertEqual(workflow["assignee_ids"], ["member-id"])
        self.assertEqual(workflow["estimate"], "point-id")
        self.assertEqual(workflow["start_date"], "2026-09-04")
        self.assertEqual(workflow["target_date"], "2026-09-07")
        self.assertEqual(result["work_item"]["labels"], ["Engineering", "Task"])

    def test_strict_planning_rejects_an_incomplete_profile(self) -> None:
        api = _Api()
        profile = _profile()
        profile["default"]["planning"] = {"mode": "strict"}
        with self._patch_api(api, profile):
            with self.assertRaisesRegex(server.PlaneWorkflowError, "Strict planning requires"):
                server.create_standard_work_item(
                    project_id=PROJECT_ID,
                    outcome="Improve quality",
                    acceptance_criteria=["Viewer can select a quality"],
                    scope="Quality selector only",
                    complexity="small",
                    dry_run=True,
                )

    def test_start_previews_actual_date_and_started_state(self) -> None:
        api = _Api()
        api.item["state"] = "backlog-id"
        with self._patch_api(api), patch.object(server, "_today", return_value=date(2026, 9, 3)):
            result = server.start_standard_work_item(project_id=PROJECT_ID, work_item_id="item-id", dry_run=True)

        self.assertEqual(result["changes"], {"state": "started-id", "start_date": "2026-09-03"})
        self.assertEqual(api.events, [])

    def test_start_retry_preserves_existing_start_date(self) -> None:
        api = _Api()
        api.item["start_date"] = "2026-09-01"
        with self._patch_api(api), patch.object(server, "_today", return_value=date(2026, 9, 3)):
            result = server.start_standard_work_item(project_id=PROJECT_ID, work_item_id="item-id")

        self.assertEqual(result["status"], "already_started")
        self.assertEqual(result["workflow"]["start_date"], "2026-09-01")
        self.assertEqual(api.events, [])

    def test_explicit_start_date_still_derives_target_date(self) -> None:
        api = _Api()
        with self._patch_api(api):
            result = server.create_standard_work_item(
                project_id=PROJECT_ID,
                outcome="Improve quality",
                acceptance_criteria=["Viewer can select a quality"],
                scope="Quality selector only",
                complexity="small",
                start_date="2026-09-04",
                dry_run=True,
            )

        self.assertEqual(result["work_item"]["workflow"]["target_date"], "2026-09-07")

    def test_generic_update_cannot_complete_work(self) -> None:
        api = _Api()
        with self._patch_api(api):
            with self.assertRaisesRegex(server.PlaneWorkflowError, "complete_standard_work_item"):
                server.update_standard_work_item(project_id=PROJECT_ID, work_item_id="item-id", state_id="done-id")

    def test_completion_records_comment_and_worklog_before_done(self) -> None:
        api = _Api()
        with self._patch_api(api):
            result = server.complete_standard_work_item(
                project_id=PROJECT_ID,
                work_item_id="item-id",
                summary="Improved <quality> selection.",
                verification=["Unit tests pass"],
                implementation_notes=["Updated player state"],
                follow_ups=["Monitor rollout"],
                actual_minutes=95,
            )

        self.assertEqual(result["status"], "completed")
        self.assertEqual(api.events, ["comment", "worklog", "update-state"])
        self.assertIn("&lt;quality&gt;", result["completion"]["comment_html"])
        self.assertIn("Actual active time: 1h 35m", result["completion"]["comment_html"])
        self.assertEqual(api.item["state"], "done-id")

    def test_completion_retry_reuses_its_comment_and_worklog(self) -> None:
        api = _Api()
        summary = "Improved quality selection."
        verification = ["Unit tests pass"]
        external_id = server._completion_external_id("item-id", summary, verification, [], [], 30, "done-id")
        api.comments_data.append({"id": "existing-comment", "external_id": external_id})
        api.worklogs_data.append({"id": "existing-worklog", "description": f"[plane-workflow:{external_id}] Existing"})
        with self._patch_api(api):
            result = server.complete_standard_work_item(
                project_id=PROJECT_ID,
                work_item_id="item-id",
                summary=summary,
                verification=verification,
                actual_minutes=30,
            )

        self.assertEqual(result["status"], "completed")
        self.assertEqual(api.events, ["update-state"])
        self.assertEqual(result["comment_id"], "existing-comment")
        self.assertEqual(result["worklog_id"], "existing-worklog")

    def test_completion_requires_started_work(self) -> None:
        api = _Api()
        api.item["state"] = "backlog-id"
        with self._patch_api(api):
            with self.assertRaisesRegex(server.PlaneWorkflowError, "Start the work item"):
                server.complete_standard_work_item(
                    project_id=PROJECT_ID,
                    work_item_id="item-id",
                    summary="Improved quality selection.",
                    verification=["Unit tests pass"],
                )

    def test_worklog_read_failure_returns_a_retryable_partial_result(self) -> None:
        api = _Api()

        def fail_worklogs(project_id: str, work_item_id: str) -> list[dict[str, object]]:
            raise server.PlaneWorkflowError("worklogs unavailable")

        api.worklogs = fail_worklogs  # type: ignore[method-assign]
        with self._patch_api(api):
            result = server.complete_standard_work_item(
                project_id=PROJECT_ID,
                work_item_id="item-id",
                summary="Improved quality selection.",
                verification=["Unit tests pass"],
                actual_minutes=30,
            )

        self.assertEqual(result["status"], "completion_pending")
        self.assertEqual(result["stage"], "worklog")
        self.assertEqual(api.events, ["comment"])
        self.assertEqual(api.item["state"], "started-id")

    def test_profile_validation_catches_invalid_planning_values(self) -> None:
        errors = server._validate_profile(
            {
                "planning": {
                    "mode": "automatic",
                    "business_days": ["someday"],
                    "complexity": {"huge": {"lead_business_days": 0}},
                }
            }
        )

        self.assertTrue(any("planning.mode" in error for error in errors))
        self.assertTrue(any("business_days" in error for error in errors))
        self.assertTrue(any("unsupported levels" in error for error in errors))

    def test_displayed_estimate_value_resolves_to_plane_point_id(self) -> None:
        api = _Api()

        self.assertEqual(server._resolve_estimate_selection(api, PROJECT_ID, 2, required=True), "point-id")

    def test_numeric_estimate_falls_back_when_catalog_is_unavailable(self) -> None:
        api = _Api()

        def unavailable(project_id: str) -> dict[str, object]:
            raise server.PlaneWorkflowError("not supported")

        api.estimate = unavailable  # type: ignore[method-assign]

        self.assertEqual(server._resolve_estimate_selection(api, PROJECT_ID, 3, required=True), 3)

    def test_completion_fingerprint_covers_every_persisted_input(self) -> None:
        first = server._completion_external_id("item-id", "Done", ["Tests"], ["Changed code"], [], 30, "done-id")
        second = server._completion_external_id("item-id", "Done", ["Tests"], ["Changed code"], [], 45, "done-id")

        self.assertNotEqual(first, second)

    def test_plane_estimate_contract_accepts_singleton_object(self) -> None:
        api = server.PlaneApi(server.PlaneSettings("https://plane.example.test", "key", "workspace"))
        with patch.object(api, "request", return_value={"id": "estimate-id", "name": "Points"}):
            estimate = api.estimate(PROJECT_ID)

        self.assertEqual(estimate, {"id": "estimate-id", "name": "Points"})

    def test_comment_listing_follows_plane_cursors(self) -> None:
        api = server.PlaneApi(server.PlaneSettings("https://plane.example.test", "key", "workspace"))
        pages = [
            {"results": [{"id": "one"}], "next_page_results": True, "next_cursor": "100:1:0"},
            {"results": [{"id": "two"}], "next_page_results": False, "next_cursor": None},
        ]
        with patch.object(api, "request", side_effect=pages) as request:
            comments = api.work_item_comments(PROJECT_ID, "item-id")

        self.assertEqual([comment["id"] for comment in comments], ["one", "two"])
        self.assertEqual(request.call_args_list[1].kwargs["params"]["cursor"], "100:1:0")

    def test_plane_request_wraps_network_failures(self) -> None:
        api = server.PlaneApi(server.PlaneSettings("https://plane.example.test", "key", "workspace"))
        api.session.request = lambda *args, **kwargs: (_ for _ in ()).throw(requests.Timeout("timed out"))  # type: ignore[method-assign]

        with self.assertRaisesRegex(server.PlaneWorkflowError, "before a response"):
            api.project(PROJECT_ID)

    def test_timeout_after_comment_commit_is_safe_to_retry(self) -> None:
        api = _Api()
        original_create = api.create_work_item_comment

        def commit_then_timeout(project_id: str, work_item_id: str, payload: dict[str, object]) -> dict[str, object]:
            original_create(project_id, work_item_id, payload)
            raise server.PlaneWorkflowError("response timed out")

        api.create_work_item_comment = commit_then_timeout  # type: ignore[method-assign]
        arguments = {
            "project_id": PROJECT_ID,
            "work_item_id": "item-id",
            "summary": "Improved quality selection.",
            "verification": ["Unit tests pass"],
        }
        with self._patch_api(api):
            pending = server.complete_standard_work_item(**arguments)
            api.create_work_item_comment = original_create  # type: ignore[method-assign]
            completed = server.complete_standard_work_item(**arguments)

        self.assertEqual(pending["status"], "completion_pending")
        self.assertEqual(completed["status"], "completed")
        self.assertEqual(len(api.comments_data), 1)

    def test_fastmcp_schema_requires_completion_facts_and_positive_minutes(self) -> None:
        tools = {tool.name: tool for tool in asyncio.run(server.mcp.list_tools())}
        schema = tools["complete_standard_work_item"].parameters

        self.assertEqual(set(schema["required"]), {"work_item_id", "summary", "verification"})
        integer_schema = next(option for option in schema["properties"]["actual_minutes"]["anyOf"] if option.get("type") == "integer")
        self.assertEqual(integer_schema["minimum"], 1)


if __name__ == "__main__":
    unittest.main()
