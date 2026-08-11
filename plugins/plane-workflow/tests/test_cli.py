from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import cli


class CliTests(unittest.TestCase):
    def test_opencode_setup_writes_secret_free_local_mcp_entry(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "opencode.json"
            path.write_text('{\n  // existing comment\n  "model": "test",\n}\n', encoding="utf-8")
            cli._install_json_client("opencode", path)
            payload = json.loads(path.read_text(encoding="utf-8"))

            self.assertEqual(payload["mcp"]["plane-workflow"], {"type": "local", "command": ["plane-workflow", "mcp"], "enabled": True})
            self.assertNotIn("PLANE_API_KEY", path.read_text(encoding="utf-8"))
            self.assertTrue(path.with_suffix(".json.plane-workflow-backup").exists())

    def test_zed_setup_writes_context_server(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "settings.json"
            cli._install_json_client("zed", path)
            payload = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(payload["context_servers"]["plane-workflow"], {"command": "plane-workflow", "args": ["mcp"], "env": {}})

    def test_setup_dry_run_does_not_prompt_for_or_store_credentials(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "opencode.json"
            with patch.object(cli.configuration, "save_stored_plane_settings", side_effect=AssertionError("must not save")):
                result = cli.main(["setup", "--client", "opencode", "--config-file", str(path), "--dry-run", "--yes"])

            self.assertEqual(result, 0)
            self.assertFalse(path.exists())

    def test_no_command_suggests_setup(self) -> None:
        with patch("sys.stdout") as output:
            self.assertEqual(cli.main([]), 2)
        rendered = "".join(str(call.args[0]) for call in output.write.call_args_list if call.args)
        self.assertIn("plane-workflow setup", rendered)
