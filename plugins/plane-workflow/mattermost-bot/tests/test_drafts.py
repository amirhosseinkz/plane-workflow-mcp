from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from drafts import DraftError, DraftStore


class DraftStoreTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.store = DraftStore(Path(self.temporary_directory.name) / "drafts.sqlite3")

    def tearDown(self) -> None:
        self.store.close()
        self.temporary_directory.cleanup()

    def _create_draft(self):
        return self.store.create(
            requester_id="user-1",
            action="create_standard_work_item",
            arguments={"outcome": "Improve playback"},
            preview={"status": "preview"},
            ttl_minutes=15,
        )

    def test_confirmation_cannot_be_applied_twice(self) -> None:
        draft = self._create_draft()

        started = self.store.begin_execution(draft.draft_id, "user-1")
        self.assertEqual(started.draft_id, draft.draft_id)
        with self.assertRaisesRegex(DraftError, "already being applied"):
            self.store.begin_execution(draft.draft_id, "user-1")

        self.store.mark_completed(draft.draft_id, "user-1")
        with self.assertRaisesRegex(DraftError, "already been applied"):
            self.store.get_pending(draft.draft_id, "user-1")

    def test_failed_confirmation_requires_review(self) -> None:
        draft = self._create_draft()
        self.store.begin_execution(draft.draft_id, "user-1")
        self.store.mark_requires_review(draft.draft_id, "user-1")

        with self.assertRaisesRegex(DraftError, "manual Plane review"):
            self.store.get_pending(draft.draft_id, "user-1")

    def test_processed_post_is_remembered(self) -> None:
        self.assertFalse(self.store.is_post_processed("post-1"))
        self.store.mark_post_processed("post-1")
        self.assertTrue(self.store.is_post_processed("post-1"))
