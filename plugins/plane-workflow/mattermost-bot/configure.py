"""Create the local credential file for the Mattermost Plane bot."""

from __future__ import annotations

import argparse
from getpass import getpass
from pathlib import Path


ROOT = Path(__file__).resolve().parent
ENV_PATH = ROOT / ".env"


def _value(prompt: str, *, secret: bool = False, default: str | None = None) -> str:
    suffix = f" [{default}]" if default else ""
    raw = getpass(f"{prompt}{suffix}: ") if secret else input(f"{prompt}{suffix}: ")
    value = raw.strip() or (default or "")
    if not value:
        raise ValueError(f"{prompt} is required.")
    if "\n" in value or "\r" in value:
        raise ValueError(f"{prompt} must be a single line.")
    return value


def build_environment(
    *,
    mattermost_url: str,
    bot_username: str,
    bot_token: str,
    allowed_usernames: str,
    plane_base_url: str,
    plane_workspace_slug: str,
    plane_api_key: str,
    plane_project_id: str,
    plane_project_identifier: str,
) -> str:
    return "\n".join(
        [
            "# Generated locally by configure.py. Keep this file private.",
            f"MATTERMOST_URL={mattermost_url}",
            f"MATTERMOST_BOT_USERNAME={bot_username}",
            f"MATTERMOST_BOT_TOKEN={bot_token}",
            f"MATTERMOST_ALLOWED_USERNAMES={allowed_usernames}",
            "MATTERMOST_DM_ONLY=true",
            "",
            f"PLANE_BASE_URL={plane_base_url}",
            f"PLANE_WORKSPACE_SLUG={plane_workspace_slug}",
            f"PLANE_API_KEY={plane_api_key}",
            f"PLANE_PROJECT_ID={plane_project_id}",
            f"PLANE_PROJECT_IDENTIFIER={plane_project_identifier}",
            "",
            "CODEX_COMMAND=codex",
            "CODEX_TIMEOUT_SECONDS=120",
            "",
            "BOT_DATA_DIR=./data",
            "DRAFT_TTL_MINUTES=15",
            "",
        ]
    )


def configure(*, overwrite: bool) -> None:
    if ENV_PATH.exists() and not overwrite:
        raise ValueError(f"{ENV_PATH} already exists. Run again with --overwrite to replace it.")
    print("Enter the connection details for your own deployment. Tokens are not displayed after you type them.")
    mattermost_url = _value("Mattermost URL")
    bot_username = _value("Mattermost bot username")
    bot_token = _value("Mattermost bot token", secret=True)
    allowed_usernames = _value("Allowed Mattermost username(s), comma-separated")
    plane_base_url = _value("Plane URL")
    plane_workspace_slug = _value("Plane workspace slug")
    plane_api_key = _value("Plane API key", secret=True)
    plane_project_id = _value("Plane project ID")
    plane_project_identifier = _value("Plane project identifier")
    ENV_PATH.write_text(
        build_environment(
            mattermost_url=mattermost_url,
            bot_username=bot_username,
            bot_token=bot_token,
            allowed_usernames=allowed_usernames,
            plane_base_url=plane_base_url,
            plane_workspace_slug=plane_workspace_slug,
            plane_api_key=plane_api_key,
            plane_project_id=plane_project_id,
            plane_project_identifier=plane_project_identifier,
        ),
        encoding="utf-8",
    )
    ENV_PATH.chmod(0o600)
    print("Saved the private bot configuration. Next run: uv run python main.py --check")


def main() -> int:
    parser = argparse.ArgumentParser(description="Create the private local configuration for Plane Bot.")
    parser.add_argument("--overwrite", action="store_true", help="Replace an existing local .env file.")
    arguments = parser.parse_args()
    try:
        configure(overwrite=arguments.overwrite)
    except ValueError as error:
        print(f"Configuration was not changed: {error}")
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
