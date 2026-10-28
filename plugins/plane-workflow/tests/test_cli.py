from __future__ import annotations

import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from plane_workflow_mcp import cli


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

    def test_update_check_reports_a_newer_release_with_its_wheel(self) -> None:
        from types import SimpleNamespace

        release = {
            "tag_name": "v0.7.0",
            "html_url": "https://github.com/example/releases/v0.7.0",
            "assets": [{"name": "plane_workflow_mcp-0.7.0-py3-none-any.whl", "browser_download_url": "https://downloads.example.test/x.whl"}],
        }
        get = lambda *args, **kwargs: SimpleNamespace(ok=True, json=lambda: release)
        with patch.dict("os.environ", {}, clear=False):
            cli.os.environ.pop("PLANE_WORKFLOW_NO_UPDATE_CHECK", None)
            update = cli.check_for_update("0.6.0", get=get)
            self.assertEqual(update["latest_version"], "0.7.0")
            self.assertEqual(update["update_command"], "uv tool install --force plane-workflow-mcp")
            self.assertIsNone(cli.check_for_update("0.7.0", get=get))
            self.assertIsNone(cli.check_for_update("0.10.0", get=get))

    def test_update_check_is_silent_offline_or_when_disabled(self) -> None:
        def offline(*args: object, **kwargs: object) -> object:
            raise cli.server.requests.ConnectionError("offline")

        self.assertIsNone(cli.check_for_update("0.6.0", get=offline))
        with patch.dict("os.environ", {"PLANE_WORKFLOW_NO_UPDATE_CHECK": "1"}):
            self.assertIsNone(cli.check_for_update("0.6.0", get=lambda *a, **k: AssertionError("must not call")))

    def test_setup_without_a_client_only_stores_credentials(self) -> None:
        with patch.object(cli, "_validate_connection"), patch.object(cli.configuration, "save_stored_plane_settings", return_value="profile.json") as save, \
                patch.object(cli, "_install_cli_client", side_effect=AssertionError("must not register")), \
                patch.object(cli, "_install_json_client", side_effect=AssertionError("must not register")), \
                patch.dict("os.environ", {"PLANE_API_KEY": "secret"}):
            result = cli.main(["setup", "--client", "none", "--base-url", "https://plane.example.test", "--workspace", "w", "--non-interactive", "--yes"])
        self.assertEqual(result, 0)
        save.assert_called_once()

