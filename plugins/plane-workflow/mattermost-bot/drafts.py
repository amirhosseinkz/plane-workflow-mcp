"""Local, expiring confirmation records for Plane-changing bot actions."""

from __future__ import annotations

import json
import secrets
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


class DraftError(RuntimeError):
    """Raised when a pending action cannot be confirmed safely."""


@dataclass(frozen=True)
class Draft:
    draft_id: str
    requester_id: str
    action: str
    arguments: dict[str, Any]
    preview: dict[str, Any]
    created_at: datetime
    expires_at: datetime


class DraftStore:
    def __init__(self, database_path: Path) -> None:
        database_path.parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(database_path)
        self.connection.row_factory = sqlite3.Row
        self.connection.execute(
            """
            CREATE TABLE IF NOT EXISTS drafts (
                draft_id TEXT PRIMARY KEY,
                requester_id TEXT NOT NULL,
                action TEXT NOT NULL,
                arguments_json TEXT NOT NULL,
                preview_json TEXT NOT NULL,
                created_at TEXT NOT NULL,
                expires_at TEXT NOT NULL,
                status TEXT NOT NULL
            )
            """
        )
        self.connection.execute(
            """
            CREATE TABLE IF NOT EXISTS processed_posts (
                post_id TEXT PRIMARY KEY,
                processed_at TEXT NOT NULL
            )
            """
        )
        self.connection.commit()

    def close(self) -> None:
        self.connection.close()

    def create(
        self,
        *,
        requester_id: str,
        action: str,
        arguments: dict[str, Any],
        preview: dict[str, Any],
        ttl_minutes: int,
    ) -> Draft:
        now = datetime.now(timezone.utc)
        draft = Draft(
            draft_id=secrets.token_urlsafe(6).lower(),
            requester_id=requester_id,
            action=action,
            arguments=arguments,
            preview=preview,
            created_at=now,
            expires_at=now + timedelta(minutes=ttl_minutes),
        )
        self.connection.execute(
            """
            INSERT INTO drafts (draft_id, requester_id, action, arguments_json, preview_json, created_at, expires_at, status)
            VALUES (?, ?, ?, ?, ?, ?, ?, 'pending')
            """,
            (
                draft.draft_id,
                draft.requester_id,
                draft.action,
                json.dumps(draft.arguments, ensure_ascii=False),
                json.dumps(draft.preview, ensure_ascii=False),
                draft.created_at.isoformat(),
                draft.expires_at.isoformat(),
            ),
        )
        self.connection.commit()
        return draft

    def get_pending(self, draft_id: str, requester_id: str) -> Draft:
        row = self.connection.execute(
            "SELECT * FROM drafts WHERE draft_id = ? AND requester_id = ?",
            (draft_id, requester_id),
        ).fetchone()
        if row is None:
            raise DraftError("No draft with that ID belongs to you.")
        status = str(row["status"])
        if status != "pending":
            messages = {
                "applying": "This draft is already being applied and cannot be retried automatically.",
                "confirmed": "This draft has already been applied.",
                "cancelled": "This draft was cancelled.",
                "expired": "That draft has expired. Please ask the bot to prepare a fresh preview.",
                "requires_review": "This draft needs a manual Plane review before another change is attempted.",
            }
            raise DraftError(messages.get(status, "This draft is no longer available for confirmation."))
        draft = self._from_row(row)
        if draft.expires_at <= datetime.now(timezone.utc):
            self._transition(draft_id, requester_id, "pending", "expired")
            raise DraftError("That draft has expired. Please ask the bot to prepare a fresh preview.")
        return draft

    def begin_execution(self, draft_id: str, requester_id: str) -> Draft:
        draft = self.get_pending(draft_id, requester_id)
        self._transition(draft_id, requester_id, "pending", "applying")
        return draft

    def mark_completed(self, draft_id: str, requester_id: str) -> None:
        self._transition(draft_id, requester_id, "applying", "confirmed")

    def mark_requires_review(self, draft_id: str, requester_id: str) -> None:
        self._transition(draft_id, requester_id, "applying", "requires_review")

    def cancel(self, draft_id: str, requester_id: str) -> Draft:
        draft = self.get_pending(draft_id, requester_id)
        self._transition(draft_id, requester_id, "pending", "cancelled")
        return draft

    def is_post_processed(self, post_id: str) -> bool:
        row = self.connection.execute("SELECT 1 FROM processed_posts WHERE post_id = ?", (post_id,)).fetchone()
        return row is not None

    def mark_post_processed(self, post_id: str) -> None:
        now = datetime.now(timezone.utc)
        cutoff = (now - timedelta(days=30)).isoformat()
        self.connection.execute("DELETE FROM processed_posts WHERE processed_at < ?", (cutoff,))
        self.connection.execute(
            "INSERT OR IGNORE INTO processed_posts (post_id, processed_at) VALUES (?, ?)",
            (post_id, now.isoformat()),
        )
        self.connection.commit()

    def _transition(self, draft_id: str, requester_id: str, expected_status: str, next_status: str) -> None:
        cursor = self.connection.execute(
            """
            UPDATE drafts
            SET status = ?
            WHERE draft_id = ? AND requester_id = ? AND status = ?
            """,
            (next_status, draft_id, requester_id, expected_status),
        )
        self.connection.commit()
        if cursor.rowcount != 1:
            raise DraftError("This draft changed state before it could be processed. Please prepare a new preview.")

    @staticmethod
    def _from_row(row: sqlite3.Row) -> Draft:
        return Draft(
            draft_id=str(row["draft_id"]),
            requester_id=str(row["requester_id"]),
            action=str(row["action"]),
            arguments=json.loads(str(row["arguments_json"])),
            preview=json.loads(str(row["preview_json"])),
            created_at=datetime.fromisoformat(str(row["created_at"])),
            expires_at=datetime.fromisoformat(str(row["expires_at"])),
        )
