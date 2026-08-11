from __future__ import annotations

import unittest

from configure import build_environment


class ConfigureTests(unittest.TestCase):
    def test_builds_configuration_from_the_supplied_deployment_values(self) -> None:
        rendered = build_environment(
            mattermost_url="https://chat.example.test",
            bot_username="plane-workflow-bot",
            bot_token="mattermost-token",
            allowed_usernames="alice, bob",
            plane_base_url="https://plane.example.test",
            plane_workspace_slug="example-workspace",
            plane_api_key="plane-token",
            plane_project_id="example-project-id",
            plane_project_identifier="EXAMPLE",
        )

        self.assertIn("MATTERMOST_URL=https://chat.example.test", rendered)
        self.assertIn("MATTERMOST_ALLOWED_USERNAMES=alice, bob", rendered)
        self.assertIn("PLANE_PROJECT_IDENTIFIER=EXAMPLE", rendered)
        self.assertIn("CODEX_COMMAND=codex", rendered)
