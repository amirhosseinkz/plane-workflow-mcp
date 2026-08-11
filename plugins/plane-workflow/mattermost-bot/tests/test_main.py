from __future__ import annotations

import json
from types import SimpleNamespace
import tempfile
import unittest
from pathlib import Path

from drafts import DraftStore
from main import PlaneMattermostBot
from mattermost import IncomingPost


class _MattermostClient:
    def __init__(self) -> None:
        self.posts: list[tuple[str, str, str | None]] = []
        self.updates: list[tuple[str, str]] = []

    def channel_type(self, channel_id: str) -> str:
        return "D"

    def channel_posts(self, channel_id: str) -> list[IncomingPost]:
        return []

    def post_message(self, channel_id: str, message: str, *, root_id: str | None = None) -> dict[str, object]:
        self.posts.append((channel_id, message, root_id))
        return {"id": f"bot-post-{len(self.posts)}"}

    def update_message(self, post_id: str, message: str) -> dict[str, object]:
        self.updates.append((post_id, message))
        return {"id": post_id}


class _Agent:
    def __init__(self) -> None:
        self.calls = 0

    def handle(self, **_: object) -> str:
        self.calls += 1
        return "Ready"


class MainLoopTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.store = DraftStore(Path(self.temporary_directory.name) / "drafts.sqlite3")
        self.bot = object.__new__(PlaneMattermostBot)
        self.bot.config = SimpleNamespace(dm_only=True)
        self.bot.client = _MattermostClient()
        self.bot.drafts = self.store
        self.bot.agent = _Agent()
        self.bot.bot_user_id = "bot-user"
        self.bot.allowed_user_ids = {"trusted-user"}
        self.bot.allowed_direct_channel_ids = {"channel-1"}
        self.bot._polled_post_ids = {}

    def tearDown(self) -> None:
        self.store.close()
        self.temporary_directory.cleanup()

    def test_duplicate_websocket_event_is_processed_once(self) -> None:
        payload = {
            "event": "posted",
            "data": {
                "post": json.dumps(
                    {
                        "id": "post-1",
                        "channel_id": "channel-1",
                        "user_id": "trusted-user",
                        "message": "Create a task",
                    }
                )
            },
        }

        self.bot._handle_websocket_payload(payload)
        self.bot._handle_websocket_payload(payload)

        self.assertEqual(self.bot.agent.calls, 1)
        self.assertEqual(len(self.bot.client.posts), 1)
        self.assertIn("Please wait", self.bot.client.posts[0][1])
        self.assertEqual(self.bot.client.updates, [("bot-post-1", "Ready")])

    def test_polling_processes_a_missed_direct_message_once(self) -> None:
        self.bot.client.channel_posts = lambda channel_id: [
            IncomingPost(
                post_id="missed-post-1",
                channel_id=channel_id,
                user_id="trusted-user",
                message="Create a task",
                root_id=None,
                file_ids=(),
            )
        ]

        self.bot._poll_direct_messages()
        self.bot._poll_direct_messages()

        self.assertEqual(self.bot.agent.calls, 1)
        self.assertEqual(self.bot.client.updates, [("bot-post-1", "Ready")])

    def test_polling_ignores_messages_present_at_startup(self) -> None:
        self.bot.client.channel_posts = lambda channel_id: [
            IncomingPost(
                post_id="existing-post-1",
                channel_id=channel_id,
                user_id="trusted-user",
                message="Create a task",
                root_id=None,
                file_ids=(),
            )
        ]

        self.bot._prime_direct_message_polling()
        self.bot._poll_direct_messages()

        self.assertEqual(self.bot.agent.calls, 0)
