from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import launch_agent


class LaunchAgentTests(unittest.TestCase):
    def test_service_uses_the_discovered_uv_executable(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            with (
                patch.dict(os.environ, {}, clear=True),
                patch("launch_agent.ROOT", root),
                patch("launch_agent.shutil.which", return_value="uv"),
            ):
                specification = launch_agent._service_specification()

        self.assertEqual(specification["Label"], "com.planeworkflow.mattermost-bot")
        self.assertEqual(
            specification["ProgramArguments"],
            ["uv", "run", "python", str(root / "main.py")],
        )

    def test_uv_command_environment_override_is_used(self) -> None:
        with patch.dict(os.environ, {"UV_COMMAND": "custom-uv"}, clear=True):
            self.assertEqual(launch_agent._uv_executable(), "custom-uv")

    def test_launch_agent_helper_rejects_non_macos_hosts(self) -> None:
        with patch("launch_agent.sys.platform", "linux"):
            with self.assertRaisesRegex(RuntimeError, "only on macOS"):
                launch_agent._require_macos()
