from __future__ import annotations

import json
import subprocess
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
            self.assertEqual(payload["model"], "test")
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

    def test_codex_setup_registers_without_credentials(self) -> None:
        from unittest.mock import Mock

        for exists in (False, True):
            with self.subTest(exists=exists):
                runner = Mock(side_effect=[
                    subprocess.CompletedProcess([], 0 if exists else 1, "", ""),
                    *([subprocess.CompletedProcess([], 0, "", "")] if exists else []),
                    subprocess.CompletedProcess([], 0, "", ""),
                ])
                cli._install_codex(runner=runner)
                commands = [call.args[0] for call in runner.call_args_list]
                expected = [["codex", "mcp", "get", "plane-workflow"]]
                if exists:
                    expected.append(["codex", "mcp", "remove", "plane-workflow"])
                expected.append(["codex", "mcp", "add", "plane-workflow", "--", "plane-workflow", "mcp"])
                self.assertEqual(commands, expected)

    def test_claude_code_setup_registers_user_scope_with_absolute_launcher(self) -> None:
        from unittest.mock import Mock

        runner = Mock(side_effect=[
            subprocess.CompletedProcess([], 1, "", "No MCP server found"),
            subprocess.CompletedProcess([], 0, "", ""),
        ])
        with patch.object(cli.shutil, "which", return_value="/opt/bin/plane-workflow"):
            cli._install_cli_client("claude-code", runner=runner)
        commands = [call.args[0] for call in runner.call_args_list]
        self.assertEqual(commands, [
            ["claude", "mcp", "get", "plane-workflow"],
            ["claude", "mcp", "add", "--scope", "user", "plane-workflow", "--", "/opt/bin/plane-workflow", "mcp"],
        ])

    def test_claude_code_dry_run_does_not_call_the_cli(self) -> None:
        with patch.object(cli.subprocess, "run", side_effect=AssertionError("must not run")), patch.object(cli.configuration, "save_stored_plane_settings", side_effect=AssertionError("must not save")):
            self.assertEqual(cli.main(["setup", "--client", "claude-code", "--dry-run", "--yes"]), 0)

    def test_cursor_and_claude_desktop_write_mcp_servers_entry(self) -> None:
        for client in ("cursor", "claude-desktop"):
            with self.subTest(client=client), tempfile.TemporaryDirectory() as directory:
                path = Path(directory) / "mcp.json"
                path.write_text('{"mcpServers": {"other": {"command": "x"}}}', encoding="utf-8")
                with patch.object(cli.shutil, "which", return_value=None):
                    cli._install_json_client(client, path)
                payload = json.loads(path.read_text(encoding="utf-8"))
                self.assertEqual(payload["mcpServers"]["plane-workflow"], {"command": "plane-workflow", "args": ["mcp"]})
                self.assertIn("other", payload["mcpServers"])
                self.assertTrue(cli._remove_json_client(client, path))
                self.assertNotIn("plane-workflow", json.loads(path.read_text(encoding="utf-8"))["mcpServers"])
