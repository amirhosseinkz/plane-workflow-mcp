"""Configuration for the local Mattermost Plane bot."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


BOT_ROOT = Path(__file__).resolve().parent


class ConfigurationError(RuntimeError):
    """Raised when the bot cannot start safely."""


def load_env_file(path: Path) -> None:
    """Load a small local .env file without overriding explicitly supplied environment values."""
    if not path.exists():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


def _required(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise ConfigurationError(f"{name} must be set in the bot's local .env file.")
    return value


def _bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().casefold() in {"1", "true", "yes", "on"}


def _positive_int(name: str, default: int) -> int:
    raw = os.getenv(name, str(default)).strip()
    try:
        value = int(raw)
    except ValueError as error:
        raise ConfigurationError(f"{name} must be a whole number.") from error
    if value < 1:
        raise ConfigurationError(f"{name} must be greater than zero.")
    return value


@dataclass(frozen=True)
class BotConfig:
    mattermost_url: str
    bot_username: str
    bot_token: str
    allowed_usernames: tuple[str, ...]
    dm_only: bool
    plane_project_id: str
    plane_project_identifier: str
    codex_command: str
    codex_timeout_seconds: int
    data_dir: Path
    draft_ttl_minutes: int

    @property
    def database_path(self) -> Path:
        return self.data_dir / "plane-bot.sqlite3"

    @property
    def attachment_dir(self) -> Path:
        return self.data_dir / "attachments"

    @property
    def websocket_url(self) -> str:
        base = self.mattermost_url.rstrip("/")
        if base.startswith("https://"):
            return f"wss://{base.removeprefix('https://')}/api/v4/websocket"
        if base.startswith("http://"):
            return f"ws://{base.removeprefix('http://')}/api/v4/websocket"
        raise ConfigurationError("MATTERMOST_URL must start with http:// or https://.")


def load_config(env_path: Path | None = None) -> BotConfig:
    load_env_file(env_path or BOT_ROOT / ".env")
    _required("PLANE_BASE_URL")
    _required("PLANE_WORKSPACE_SLUG")
    _required("PLANE_API_KEY")
    usernames = tuple(
        username.strip().casefold()
        for username in os.getenv("MATTERMOST_ALLOWED_USERNAMES", "").split(",")
        if username.strip()
    )
    if not usernames:
        raise ConfigurationError("MATTERMOST_ALLOWED_USERNAMES must list at least one trusted user.")
    data_dir = Path(os.getenv("BOT_DATA_DIR", BOT_ROOT / "data")).expanduser()
    if not data_dir.is_absolute():
        data_dir = (BOT_ROOT / data_dir).resolve()
    return BotConfig(
        mattermost_url=_required("MATTERMOST_URL").rstrip("/"),
        bot_username=_required("MATTERMOST_BOT_USERNAME"),
        bot_token=_required("MATTERMOST_BOT_TOKEN"),
        allowed_usernames=usernames,
        dm_only=_bool("MATTERMOST_DM_ONLY", True),
        plane_project_id=_required("PLANE_PROJECT_ID"),
        plane_project_identifier=_required("PLANE_PROJECT_IDENTIFIER"),
        codex_command=os.getenv("CODEX_COMMAND", "codex").strip() or "codex",
        codex_timeout_seconds=_positive_int("CODEX_TIMEOUT_SECONDS", 120),
        data_dir=data_dir,
        draft_ttl_minutes=_positive_int("DRAFT_TTL_MINUTES", 15),
    )
