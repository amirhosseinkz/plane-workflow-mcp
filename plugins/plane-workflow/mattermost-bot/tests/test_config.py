from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from config import ConfigurationError, load_config


class ConfigurationTests(unittest.TestCase):
    def test_loads_expected_local_configuration(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            env_path = Path(temporary_directory) / ".env"
            env_path.write_text(
                "\n".join(
                    [
                        "MATTERMOST_URL=https://chat.example.test",
                        "MATTERMOST_BOT_USERNAME=plane-workflow-bot",
                        "MATTERMOST_BOT_TOKEN=test-token",
                        "MATTERMOST_ALLOWED_USERNAMES=Alice, bob",
                        "PLANE_BASE_URL=https://plane.example.test",
                        "PLANE_WORKSPACE_SLUG=example-workspace",
                        "PLANE_API_KEY=test-plane-key",
                        "PLANE_PROJECT_ID=project-id",
                        "PLANE_PROJECT_IDENTIFIER=EXAMPLE",
                        "BOT_DATA_DIR=./test-data",
                    ]
                ),
                encoding="utf-8",
            )
            with patch.dict(os.environ, {}, clear=True):
                config = load_config(env_path)

        self.assertEqual(config.allowed_usernames, ("alice", "bob"))
        self.assertEqual(config.websocket_url, "wss://chat.example.test/api/v4/websocket")
        self.assertEqual(config.plane_project_identifier, "EXAMPLE")
        self.assertTrue(config.dm_only)

    def test_rejects_missing_trusted_user(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaisesRegex(ConfigurationError, "PLANE_BASE_URL"):
                load_config(Path("/does/not/exist"))
