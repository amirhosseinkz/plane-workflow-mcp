from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import patch

from codex_router import CodexRouter, CodexRouterError


class _Completed:
    def __init__(self, returncode: int = 0, stdout: str = "", stderr: str = "") -> None:
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


class CodexRouterTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.config = SimpleNamespace(
            codex_command="codex",
            codex_timeout_seconds=30,
            data_dir=Path(self.temporary_directory.name),
            plane_project_identifier="EXAMPLE",
        )
        self.tools = [
            {
                "name": "create_standard_work_item",
                "description": "Draft a task.",
                "parameters": {"type": "object"},
            }
        ]

    def tearDown(self) -> None:
        self.temporary_directory.cleanup()

    @patch("codex_router.shutil.which", return_value="codex")
    @patch("codex_router.subprocess.run")
    def test_routes_with_restricted_codex_command(self, run, _which) -> None:
        def write_decision(command: list[str], **_: object) -> _Completed:
            output_path = Path(command[command.index("--output-last-message") + 1])
            output_path.write_text(
                '{"action":"create_standard_work_item","arguments_json":"{\\"outcome\\":\\"Improve quality\\",\\"acceptance_criteria\\":[\\"Viewer can choose a quality\\"]}","message":""}',
                encoding="utf-8",
            )
            return _Completed()

        run.side_effect = write_decision

        decision = CodexRouter(self.config, self.tools).route(
            message="Create a task for quality selection",
            file_ids=(),
        )

        command = run.call_args.args[0]
        self.assertEqual(decision.action, "create_standard_work_item")
        self.assertIn("--sandbox", command)
        self.assertIn("read-only", command)
        self.assertIn("--ignore-rules", command)
        self.assertIn("--ephemeral", command)

    @patch("codex_router.shutil.which", return_value="codex")
    @patch("codex_router.subprocess.run")
    def test_rejects_action_outside_the_allowlist(self, run, _which) -> None:
        def write_decision(command: list[str], **_: object) -> _Completed:
            output_path = Path(command[command.index("--output-last-message") + 1])
            output_path.write_text('{"action":"delete_everything","arguments_json":"{}","message":""}', encoding="utf-8")
            return _Completed()

        run.side_effect = write_decision

        with self.assertRaisesRegex(CodexRouterError, "unavailable"):
            CodexRouter(self.config, self.tools).route(message="Do a thing", file_ids=())

    @patch("codex_router.shutil.which", return_value="codex")
    @patch("codex_router.subprocess.run", return_value=_Completed(stderr="Logged in using ChatGPT"))
    def test_diagnose_accepts_chatgpt_sign_in(self, _run, _which) -> None:
        CodexRouter(self.config, self.tools).diagnose()
