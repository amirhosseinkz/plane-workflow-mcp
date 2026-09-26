#!/usr/bin/env python3
"""Run a real preview against the test fixture; never connect to Plane."""

from __future__ import annotations

import json
import sys
from datetime import date
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
CORE = ROOT / "plugins" / "plane-workflow"
sys.path.insert(0, str(CORE))
sys.path.insert(0, str(CORE / "tests"))

import server
from test_lifecycle import PROJECT_ID, _Api, _profile


def main() -> None:
    api = _Api()
    # Reuse the offline lifecycle fixture, not stored credentials or a live project.
    with (
        patch.object(server, "PlaneApi", return_value=api),
        patch.object(server, "_find_plane_settings", return_value=None),
        patch.object(server, "_load_profile_config", return_value=_profile()),
        patch.object(server, "load_stored_plane_settings", return_value=None),
        patch.object(server, "_today", return_value=date(2026, 9, 4)),
        patch.object(server.requests.sessions.Session, "request", side_effect=RuntimeError("Network disabled in demo")),
    ):
        result = server.create_standard_work_item(
            project_id=PROJECT_ID,
            outcome="Prevent duplicate orders when checkout is retried",
            work_item_type="bug",
            context="Web",
            surface="Checkout",
            current_behavior="Retrying checkout after a timeout can create two orders.",
            expected_behavior="Retrying the same request creates only one order.",
            scope="Checkout retry handling and regression tests",
            complexity="small",
            acceptance_criteria=[
                "Repeating the same request creates one order",
                "A failed first attempt can be retried",
                "The existing successful checkout flow still works",
            ],
            dry_run=True,
        )
    if result["status"] != "preview" or api.events:
        raise RuntimeError("Demo must produce a preview without writes")
    print(json.dumps({
        "demo": "Offline fixture; fixed date and synthetic IDs. No live Plane connection.",
        "result": result,
    }, indent=2))


if __name__ == "__main__":
    main()
