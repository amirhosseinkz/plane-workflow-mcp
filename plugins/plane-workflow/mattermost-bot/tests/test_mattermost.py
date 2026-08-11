from __future__ import annotations

import json
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from mattermost import MattermostClient, MattermostError, parse_post_event


class _WebSocketConnection:
    def __init__(self, responses: list[dict[str, object]]) -> None:
        self.responses = [json.dumps(response) for response in responses]
        self.sent: list[str] = []
        self.timeouts: list[int] = []
        self.closed = False

    def settimeout(self, timeout: int) -> None:
        self.timeouts.append(timeout)

    def send(self, payload: str) -> None:
        self.sent.append(payload)

    def recv(self) -> str:
        return self.responses.pop(0)

    def close(self) -> None:
        self.closed = True


class MattermostEventTests(unittest.TestCase):
    def test_parses_direct_message_post(self) -> None:
        payload = {
            "event": "posted",
            "data": {
                "post": json.dumps(
                    {
                        "id": "post-1",
                        "channel_id": "channel-1",
                        "user_id": "user-1",
                        "message": " Create a task ",
                        "root_id": "thread-1",
                        "file_ids": ["file-1", 42, ""],
                    }
                )
            },
        }

        post = parse_post_event(payload)

        self.assertIsNotNone(post)
        assert post is not None
        self.assertEqual(post.message, "Create a task")
        self.assertEqual(post.root_id, "thread-1")
        self.assertEqual(post.file_ids, ("file-1",))

    def test_ignores_non_post_events(self) -> None:
        self.assertIsNone(parse_post_event({"event": "hello", "data": {}}))

    def test_reads_channel_posts_in_chronological_order(self) -> None:
        client = MattermostClient(SimpleNamespace(mattermost_url="https://chat.example.test", bot_token="test-token"))
        payload = {
            "order": ["new", "old"],
            "posts": {
                "old": {"id": "old", "channel_id": "channel-1", "user_id": "user-1", "message": "First"},
                "new": {"id": "new", "channel_id": "channel-1", "user_id": "user-1", "message": "Second"},
            },
        }

        with patch.object(client, "_request", return_value=payload):
            posts = client.channel_posts("channel-1")

        self.assertEqual([post.post_id for post in posts], ["old", "new"])


class MattermostWebSocketTests(unittest.TestCase):
    def setUp(self) -> None:
        self.config = SimpleNamespace(
            mattermost_url="https://chat.example.test",
            websocket_url="wss://chat.example.test/api/v4/websocket",
            bot_token="test-token",
        )

    def test_ignores_non_response_events_until_authentication_succeeds(self) -> None:
        connection = _WebSocketConnection(
            [
                {"event": "hello", "data": {"server_version": "test"}},
                {"status": "OK", "seq_reply": 1},
            ]
        )
        client = MattermostClient(self.config)

        with patch("mattermost.websocket.create_connection", return_value=connection):
            result = client.open_websocket()

        self.assertIs(result, connection)
        self.assertEqual(connection.timeouts, [15, None])
        self.assertFalse(connection.closed)

    def test_returns_safe_error_when_mattermost_explicitly_rejects_authentication(self) -> None:
        connection = _WebSocketConnection(
            [{"status": "FAIL", "seq_reply": 1, "error": {"id": "websocket.auth.invalid"}}]
        )
        client = MattermostClient(self.config)

        with patch("mattermost.websocket.create_connection", return_value=connection):
            with self.assertRaisesRegex(MattermostError, "websocket.auth.invalid"):
                client.open_websocket()

        self.assertTrue(connection.closed)
