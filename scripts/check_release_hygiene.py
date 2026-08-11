#!/usr/bin/env python3
"""Reject generated artifacts and deployment-specific values in tracked source."""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path
from urllib.parse import urlparse


ROOT = Path(__file__).resolve().parents[1]
URL = re.compile(r"(?:https?|wss?)://[^\s\"'<>`]+")
SSH_URL = re.compile(r"(?<![\w@])git@([A-Za-z0-9.-]+):")
CONFIG_URL = re.compile(
    r"^[ \t]*(?:export[ \t]+)?(?:PLANE_BASE_URL|MATTERMOST_URL)[ \t]*=[ \t]*[\"']?((?:https?|wss?)://[^\s\"']+)",
    re.MULTILINE,
)
CONFIG_IDENTIFIER = re.compile(
    r"^[ \t]*(?:export[ \t]+)?(?:PLANE_WORKSPACE_SLUG|PLANE_PROJECT_ID|PLANE_PROJECT_IDENTIFIER|MATTERMOST_BOT_USERNAME)[ \t]*=[ \t]*[\"']?([^\s\"'#]+)",
    re.MULTILINE,
)
SECRET_VALUE = re.compile(
    r"^[ \t]*(?:export[ \t]+)?[A-Z][A-Z0-9_]*(?:TOKEN|API_KEY|SECRET|PASSWORD)[ \t]*=[ \t]*[\"']?([^\s\"'#]+)",
    re.MULTILINE,
)
ABSOLUTE_LOCAL_PATH = re.compile(
    r"(?:/" + r"(?:Users|home)/|/" + r"opt/homebrew|/" + r"usr/local|[A-Za-z]:\\\\Users\\\\)"
)
ALLOWED_HOSTS = {
    "example.com",
    "github.com",
    "json-schema.org",
    "opencode.ai",
    "plane.so",
    "docs.astral.sh",
    "semver.org",
}


def tracked_files() -> list[Path]:
    result = subprocess.run(
        ["git", "ls-files", "-z"],
        cwd=ROOT,
        check=True,
        capture_output=True,
    )
    return [Path(item.decode("utf-8")) for item in result.stdout.split(b"\0") if item]


def is_disallowed_artifact(path: Path) -> bool:
    return (
        path.parts[:1] in (("output",), (".codebase-memory",), ("graphify-out",))
        or "build" in path.parts
        or any(part.endswith(".egg-info") for part in path.parts)
    )


def is_allowed_url(url: str) -> bool:
    if "{" in url:
        return True
    host = urlparse(url.rstrip(".,;:)")).hostname or ""
    return not host or host.endswith(".example.test") or host in ALLOWED_HOSTS


def is_example_value(value: str) -> bool:
    normalized = value.lower()
    return normalized.startswith(("example", "test", "replace-", "${"))


def main() -> int:
    errors: list[str] = []
    for relative in tracked_files():
        if is_disallowed_artifact(relative):
            errors.append(f"generated or private artifact is tracked: {relative}")
            continue
        if relative.suffix in {".lock", ".pdf", ".docx", ".png", ".jpg", ".jpeg"}:
            continue
        path = ROOT / relative
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        for url in URL.findall(text):
            if not is_allowed_url(url):
                errors.append(f"unapproved fixed URL in {relative}: {url}")
        for host in SSH_URL.findall(text):
            if host != "github.com":
                errors.append(f"unapproved SSH host in {relative}: {host}")
        for value in CONFIG_URL.findall(text):
            host = urlparse(value).hostname or ""
            if not host.endswith(".example.test"):
                errors.append(f"deployment configuration must use an example.test value in {relative}")
        for value in CONFIG_IDENTIFIER.findall(text):
            if not is_example_value(value):
                errors.append(f"deployment identifier must use an example value in {relative}")
        for value in SECRET_VALUE.findall(text):
            if not is_example_value(value):
                errors.append(f"secret-like value must not be committed in {relative}")
        if ABSOLUTE_LOCAL_PATH.search(text):
            errors.append(f"absolute local path in {relative}")
    if errors:
        print("Public-release hygiene check failed:", file=sys.stderr)
        print("\n".join(f"- {error}" for error in errors), file=sys.stderr)
        return 1
    print("Public-release hygiene check passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
