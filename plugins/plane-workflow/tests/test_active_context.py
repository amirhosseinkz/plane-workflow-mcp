from __future__ import annotations

import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch

import configuration
import server


class _Keyring:
    def __init__(self) -> None:
        self.values: dict[tuple[str, str], str] = {}

    def get_password(self, service: str, username: str) -> str | None:
        return self.values.get((service, username))

    def set_password(self, service: str, username: str, password: str) -> None:
        self.values[(service, username)] = password


class _WorkItemApi:
    profile = "workspace"
    workspace = "workspace-slug"

    def __init__(self, item: dict[str, object] | None = None, error: Exception | None = None) -> None:
        self.item = item
        self.error = error

    def work_item(self, _: str, __: str) -> dict[str, object]:
        if self.error:
            raise self.error
        return self.item or {}


class ActiveContextTests(unittest.TestCase):
    def test_active_project_is_used_and_conflicting_project_is_rejected(self) -> None:
        keyring = _Keyring()
        with tempfile.TemporaryDirectory() as directory, patch.dict("os.environ", {"PLANE_WORKFLOW_HOME": directory}, clear=False), patch.object(configuration, "keyring", keyring):
            configuration.save_stored_plane_settings(
                base_url="https://plane.example.test",
                workspace="workspace-slug",
                api_key="secret",
                profile="workspace",
            )
            configuration.set_stored_active_project(
                profile="workspace",
                project_id="active-project",
                identifier="ACTIVE",
                name="Active project",
            )
            api = SimpleNamespace(profile="workspace", workspace="workspace-slug")

            self.assertEqual(server._project_id(api, None), "active-project")
            with self.assertRaisesRegex(server.PlaneWorkflowError, "not the active project"):
                server._project_id(api, "other-project", enforce_active=True)

    def test_wrong_project_work_item_is_reported_before_a_mutation(self) -> None:
        api = _WorkItemApi(item={"id": "work-item", "project": {"id": "other-project"}})

        with self.assertRaisesRegex(server.PlaneWorkflowError, "belongs to project 'other-project'"):
            server._work_item_for_project(api, "active-project", "work-item")

    def test_create_rejects_a_conflicting_project_before_a_plane_request(self) -> None:
        keyring = _Keyring()
        with tempfile.TemporaryDirectory() as directory, patch.dict("os.environ", {"PLANE_WORKFLOW_HOME": directory}, clear=False), patch.object(configuration, "keyring", keyring):
            configuration.save_stored_plane_settings(
                base_url="https://plane.example.test",
                workspace="workspace-slug",
                api_key="secret",
                profile="workspace",
            )
            configuration.set_stored_active_project(
                profile="workspace",
                project_id="active-project",
                identifier="ACTIVE",
                name="Active project",
            )
            settings = server.PlaneSettings(
                base_url="https://plane.example.test",
                workspace="workspace-slug",
                api_key="secret",
                profile="workspace",
            )
            with patch.object(server, "_find_plane_settings", return_value=settings):
                with self.assertRaisesRegex(server.PlaneWorkflowError, "not the active project"):
                    server.create_standard_work_item(
                        project_id="other-project",
                        outcome="Do not create this",
                        acceptance_criteria=["No Plane request is sent."],
                    )

    def test_missing_work_item_explains_the_project_mismatch_risk(self) -> None:
        api = _WorkItemApi(error=server.PlaneWorkflowError("Plane API request failed with HTTP 404."))

        with self.assertRaisesRegex(server.PlaneWorkflowError, "may belong to a different project"):
            server._work_item_for_project(api, "active-project", "work-item")
