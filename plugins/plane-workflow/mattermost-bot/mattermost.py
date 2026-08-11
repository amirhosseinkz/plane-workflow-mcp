"""Minimal Mattermost REST and WebSocket client for a direct-message bot."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

import requests
import websocket

from config import BotConfig


class MattermostError(RuntimeError):
    """Raised for safe, user-facing Mattermost failures."""


@dataclass(frozen=True)
class IncomingPost:
    post_id: str
    channel_id: str
    user_id: str
    message: str
    root_id: str | None
    file_ids: tuple[str, ...]


class MattermostClient:
    def __init__(self, config: BotConfig) -> None:
        self.config = config
        self.session = requests.Session()
        self.session.headers.update(
            {
                "Authorization": f"Bearer {config.bot_token}",
                "Accept": "application/json",
                "Content-Type": "application/json",
            }
        )
        self._channel_types: dict[str, str] = {}

    def _url(self, path: str) -> str:
        return f"{self.config.mattermost_url}/api/v4/{path.lstrip('/')}"

    def _request(self, method: str, path: str, *, payload: dict[str, Any] | None = None) -> Any:
        try:
            response = self.session.request(method, self._url(path), json=payload, timeout=30)
        except requests.RequestException as error:
            raise MattermostError("Could not reach Mattermost.") from error
        if not response.ok:
            raise MattermostError(f"Mattermost API request failed with HTTP {response.status_code}.")
        if not response.content:
            return None
        return response.json()

    def current_user(self) -> dict[str, Any]:
        response = self._request("GET", "users/me")
        if not isinstance(response, dict):
            raise MattermostError("Mattermost returned an invalid bot profile.")
        return response

    def user_by_username(self, username: str) -> dict[str, Any]:
        response = self._request("GET", f"users/username/{username}")
        if not isinstance(response, dict):
            raise MattermostError(f"Could not resolve Mattermost user '{username}'.")
        return response

    def channel_type(self, channel_id: str) -> str:
        if channel_id not in self._channel_types:
            channel = self._request("GET", f"channels/{channel_id}")
            if not isinstance(channel, dict) or not isinstance(channel.get("type"), str):
                raise MattermostError("Mattermost returned an invalid channel.")
            self._channel_types[channel_id] = channel["type"]
        return self._channel_types[channel_id]

    def direct_channel(self, first_user_id: str, second_user_id: str) -> dict[str, Any]:
        try:
            response = self.session.post(
                self._url("channels/direct"),
                json=[first_user_id, second_user_id],
                timeout=30,
            )
        except requests.RequestException as error:
            raise MattermostError("Could not reach Mattermost.") from error
        if not response.ok:
            raise MattermostError(f"Mattermost API request failed with HTTP {response.status_code}.")
        try:
            channel = response.json()
        except ValueError as error:
            raise MattermostError("Mattermost returned an invalid direct-message channel.") from error
        channel_id = channel.get("id") if isinstance(channel, dict) else None
        if not isinstance(channel_id, str) or not channel_id:
            raise MattermostError("Mattermost returned an invalid direct-message channel.")
        self._channel_types[channel_id] = "D"
        return channel

    def channel_posts(self, channel_id: str, *, per_page: int = 30) -> list[IncomingPost]:
        response = self._request("GET", f"channels/{channel_id}/posts?per_page={per_page}")
        if not isinstance(response, dict):
            raise MattermostError("Mattermost returned invalid channel posts.")
        posts = response.get("posts")
        order = response.get("order")
        if not isinstance(posts, dict) or not isinstance(order, list):
            raise MattermostError("Mattermost returned invalid channel posts.")
        parsed: list[IncomingPost] = []
        for post_id in reversed(order):
            if not isinstance(post_id, str):
                continue
            post = _parse_post(posts.get(post_id))
            if post is not None:
                parsed.append(post)
        return parsed

    def post_message(self, channel_id: str, message: str, *, root_id: str | None = None) -> dict[str, Any]:
        payload: dict[str, Any] = {"channel_id": channel_id, "message": message[:16000]}
        if root_id:
            payload["root_id"] = root_id
        response = self._request("POST", "posts", payload=payload)
        return response if isinstance(response, dict) else {}

    def update_message(self, post_id: str, message: str) -> dict[str, Any]:
        response = self._request("PUT", f"posts/{post_id}", payload={"id": post_id, "message": message[:16000]})
        return response if isinstance(response, dict) else {}

    def file_info(self, file_id: str) -> dict[str, Any]:
        response = self._request("GET", f"files/{file_id}/info")
        if not isinstance(response, dict):
            raise MattermostError("Mattermost returned invalid file metadata.")
        return response

    def download_file(self, file_id: str) -> bytes:
        try:
            response = self.session.get(self._url(f"files/{file_id}"), timeout=120)
        except requests.RequestException as error:
            raise MattermostError("Could not download the Mattermost attachment.") from error
        if not response.ok:
            raise MattermostError(f"Mattermost attachment download failed with HTTP {response.status_code}.")
        return response.content

    def open_websocket(self) -> websocket.WebSocket:
        connection: websocket.WebSocket | None = None
        try:
            connection = websocket.create_connection(self.config.websocket_url, timeout=60)
            connection.settimeout(15)
            connection.send(
                json.dumps(
                    {
                        "seq": 1,
                        "action": "authentication_challenge",
                        "data": {"token": self.config.bot_token},
                    }
                )
            )
            for _ in range(10):
                response = json.loads(connection.recv())
                if response.get("seq_reply") != 1:
                    continue
                if response.get("status") == "OK":
                    connection.settimeout(None)
                    return connection
                error = response.get("error")
                error_id = error.get("id") if isinstance(error, dict) else None
                detail = f" ({error_id})" if isinstance(error_id, str) and error_id else ""
                raise MattermostError(f"Mattermost rejected the bot's WebSocket authentication{detail}.")
            raise MattermostError("Mattermost did not complete the bot's WebSocket authentication.")
        except Exception as error:
            if connection is not None:
                connection.close()
            if isinstance(error, MattermostError):
                raise
            raise MattermostError("Could not establish an authenticated Mattermost WebSocket connection.") from error


def parse_post_event(payload: dict[str, Any]) -> IncomingPost | None:
    if payload.get("event") != "posted":
        return None
    data = payload.get("data")
    if not isinstance(data, dict) or not isinstance(data.get("post"), str):
        return None
    try:
        post = json.loads(data["post"])
    except json.JSONDecodeError:
        return None
    return _parse_post(post)


def _parse_post(post: Any) -> IncomingPost | None:
    if not isinstance(post, dict):
        return None
    post_id = post.get("id")
    channel_id = post.get("channel_id")
    user_id = post.get("user_id")
    if not all(isinstance(value, str) and value for value in (post_id, channel_id, user_id)):
        return None
    file_ids = post.get("file_ids") or []
    if not isinstance(file_ids, list):
        file_ids = []
    return IncomingPost(
        post_id=post_id,
        channel_id=channel_id,
        user_id=user_id,
        message=str(post.get("message") or "").strip(),
        root_id=post.get("root_id") or None,
        file_ids=tuple(file_id for file_id in file_ids if isinstance(file_id, str) and file_id),
    )
