"""Run the local direct-message Mattermost bot for Plane Workflow."""

from __future__ import annotations

import argparse
import json
import logging
import time
from typing import Any

import websocket

from agent import PlaneBotAgent
from attachments import AttachmentService
from codex_router import CodexRouterError
from config import BotConfig, ConfigurationError, load_config
from drafts import DraftStore
from mattermost import IncomingPost, MattermostClient, MattermostError, parse_post_event
from workflow_adapter import WorkflowAdapter, WorkflowAdapterError


LOGGER = logging.getLogger("plane_mattermost_bot")
POLL_INTERVAL_SECONDS = 10


class PlaneMattermostBot:
    def __init__(self, config: BotConfig) -> None:
        config.data_dir.mkdir(parents=True, exist_ok=True)
        config.attachment_dir.mkdir(parents=True, exist_ok=True)
        self.config = config
        self.client = MattermostClient(config)
        self.drafts = DraftStore(config.database_path)
        self.workflow = WorkflowAdapter(config)
        self.agent = PlaneBotAgent(config, self.workflow, self.drafts, AttachmentService(config, self.client, self.workflow))
        self.bot_user_id: str | None = None
        self.allowed_user_ids: set[str] = set()
        self.allowed_direct_channel_ids: set[str] = set()
        self._polled_post_ids: dict[str, set[str]] = {}

    def start(self) -> None:
        current_user = self.client.current_user()
        self.bot_user_id = str(current_user.get("id") or "")
        if not self.bot_user_id:
            raise MattermostError("Mattermost did not return a bot user ID.")
        actual_username = str(current_user.get("username") or "").casefold()
        if actual_username != self.config.bot_username.casefold():
            raise MattermostError("MATTERMOST_BOT_USERNAME does not match the account behind MATTERMOST_BOT_TOKEN.")
        for username in self.config.allowed_usernames:
            user = self.client.user_by_username(username)
            user_id = user.get("id")
            if not isinstance(user_id, str) or not user_id:
                raise MattermostError(f"Could not resolve allowed Mattermost user '{username}'.")
            self.allowed_user_ids.add(user_id)
            channel = self.client.direct_channel(self.bot_user_id, user_id)
            channel_id = channel.get("id")
            if not isinstance(channel_id, str) or not channel_id:
                raise MattermostError("Mattermost did not return an approved direct-message channel.")
            self.allowed_direct_channel_ids.add(channel_id)
        self.agent.diagnose_backend()
        self._prime_direct_message_polling()
        LOGGER.info("Codex CLI is signed in and ready for local request routing.")
        LOGGER.info("Plane bot is ready for %s approved direct-message user(s).", len(self.allowed_user_ids))

    def run_forever(self) -> None:
        self.start()
        delay_seconds = 1
        while True:
            connection = None
            try:
                connection = self.client.open_websocket()
                connection.settimeout(POLL_INTERVAL_SECONDS)
                delay_seconds = 1
                LOGGER.info("Connected to Mattermost WebSocket.")
                self._poll_direct_messages()
                while True:
                    try:
                        raw = connection.recv()
                    except websocket.WebSocketTimeoutException:
                        self._poll_direct_messages()
                        continue
                    if not raw:
                        raise MattermostError("Mattermost closed the WebSocket connection.")
                    self._handle_websocket_payload(json.loads(raw))
            except (MattermostError, OSError, json.JSONDecodeError, websocket.WebSocketException) as error:
                LOGGER.warning("Mattermost connection issue: %s. Reconnecting in %s seconds.", error, delay_seconds)
                time.sleep(delay_seconds)
                delay_seconds = min(delay_seconds * 2, 30)
            finally:
                if connection is not None:
                    connection.close()

    def _handle_websocket_payload(self, payload: dict[str, Any]) -> None:
        post = parse_post_event(payload)
        if post is not None:
            self._handle_post(post)

    def _poll_direct_messages(self) -> None:
        for channel_id in self.allowed_direct_channel_ids:
            posts = self.client.channel_posts(channel_id)
            known_post_ids = self._polled_post_ids.get(channel_id, set())
            for post in posts:
                if post.post_id in known_post_ids:
                    continue
                self._handle_post(post)
            self._polled_post_ids[channel_id] = {post.post_id for post in posts}

    def _prime_direct_message_polling(self) -> None:
        for channel_id in self.allowed_direct_channel_ids:
            self._polled_post_ids[channel_id] = {
                post.post_id for post in self.client.channel_posts(channel_id)
            }

    def _handle_post(self, post: IncomingPost) -> None:
        if not self._accept(post):
            return
        if self.drafts.is_post_processed(post.post_id):
            return
        working_post_id: str | None = None
        try:
            working_post = self.client.post_message(
                post.channel_id,
                "I'm checking that and preparing a safe Plane draft. Please wait...",
                root_id=post.root_id,
            )
            candidate = working_post.get("id")
            working_post_id = candidate if isinstance(candidate, str) and candidate else None
        except MattermostError:
            LOGGER.warning("Could not post a working status for a direct-message request.")
        try:
            reply = self.agent.handle(requester_id=post.user_id, message=post.message, file_ids=post.file_ids)
        except Exception:
            LOGGER.exception("Unexpected bot error while handling a direct message.")
            reply = "I could not process that request safely. Please try again, or use `help` for examples."
        if working_post_id:
            try:
                self.client.update_message(working_post_id, reply)
            except MattermostError:
                LOGGER.warning("Could not update the working status with the final direct-message reply.")
                self.client.post_message(post.channel_id, reply, root_id=post.root_id)
        else:
            self.client.post_message(post.channel_id, reply, root_id=post.root_id)
        self.drafts.mark_post_processed(post.post_id)

    def _accept(self, post: IncomingPost) -> bool:
        if post.user_id == self.bot_user_id:
            return False
        if post.user_id not in self.allowed_user_ids:
            return False
        if self.config.dm_only and self.client.channel_type(post.channel_id) != "D":
            return False
        return bool(post.message or post.file_ids)

    def close(self) -> None:
        self.drafts.close()


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the local Mattermost bot for Plane Workflow.")
    parser.add_argument("--check", action="store_true", help="Check Mattermost and Plane access, then exit.")
    arguments = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    try:
        bot = PlaneMattermostBot(load_config())
        if arguments.check:
            bot.start()
            bot.workflow.execute("diagnose_plane_connection", {}, preview=True)
            LOGGER.info("Mattermost and Plane checks passed. The bot is ready to start.")
            return 0
        bot.run_forever()
    except (CodexRouterError, ConfigurationError, MattermostError, WorkflowAdapterError) as error:
        LOGGER.error("Startup check failed: %s", error)
        return 2
    except KeyboardInterrupt:
        LOGGER.info("Plane bot stopped.")
        return 0
    finally:
        if "bot" in locals():
            bot.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
