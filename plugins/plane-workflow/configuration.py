"""Credential storage for the standalone Plane Workflow command.

The JSON configuration contains only the Plane URL and workspace.  API keys
live in the operating system keyring so MCP-client configuration files never
need to contain a credential.
"""

from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass
from pathlib import Path

import keyring
from keyring.errors import KeyringError


KEYRING_SERVICE = "plane-workflow-mcp"
SETTINGS_FILENAME = "settings.json"


class ConfigurationError(RuntimeError):
    """Raised when local, non-secret Plane configuration is unusable."""


@dataclass(frozen=True)
class StoredPlaneSettings:
    base_url: str
    api_key: str
    workspace: str
    profile: str


def configuration_directory() -> Path:
    """Return a user-owned configuration directory on every supported OS."""
    override = os.getenv("PLANE_WORKFLOW_HOME")
    if override:
        return Path(override).expanduser()
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "plane-workflow"
    if os.name == "nt":
        return Path(os.getenv("APPDATA", Path.home())) / "plane-workflow"
    return Path(os.getenv("XDG_CONFIG_HOME", Path.home() / ".config")) / "plane-workflow"


def settings_path() -> Path:
    return configuration_directory() / SETTINGS_FILENAME


def _read_settings(path: Path | None = None) -> dict[str, object]:
    target = path or settings_path()
    if not target.exists():
        return {}
    try:
        payload = json.loads(target.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise ConfigurationError(f"Local Plane Workflow settings are invalid: {target}") from error
    if not isinstance(payload, dict):
        raise ConfigurationError(f"Local Plane Workflow settings must be an object: {target}")
    return payload


def _write_settings(payload: dict[str, object], path: Path | None = None) -> Path:
    target = path or settings_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_suffix(".tmp")
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(target)
    try:
        target.chmod(0o600)
    except OSError:
        # Windows does not use POSIX permissions. The secret itself is still in
        # the platform keyring rather than this file.
        pass
    return target


def _profile_record(payload: dict[str, object], profile: str | None) -> tuple[str, dict[str, object]] | None:
    selected = profile or payload.get("active_profile") or "default"
    if not isinstance(selected, str) or not selected.strip():
        raise ConfigurationError("The active Plane Workflow profile is invalid.")
    profiles = payload.get("profiles")
    if profiles is None:
        return None
    if not isinstance(profiles, dict):
        raise ConfigurationError("Plane Workflow settings must contain a profiles object.")
    record = profiles.get(selected)
    if record is None:
        return None
    if not isinstance(record, dict):
        raise ConfigurationError(f"Plane Workflow profile {selected!r} is invalid.")
    return selected, record


def load_stored_plane_settings(profile: str | None = None) -> StoredPlaneSettings | None:
    """Load a configured profile and its secret, or None before first setup."""
    record = _profile_record(_read_settings(), profile)
    if record is None:
        return None
    selected, values = record
    base_url = values.get("base_url")
    workspace = values.get("workspace")
    if not isinstance(base_url, str) or not base_url.strip() or not isinstance(workspace, str) or not workspace.strip():
        raise ConfigurationError(f"Plane Workflow profile {selected!r} is missing its URL or workspace.")
    try:
        api_key = keyring.get_password(KEYRING_SERVICE, selected)
    except KeyringError as error:
        raise ConfigurationError("The operating-system keyring is unavailable. Run plane-workflow setup again.") from error
    if not api_key:
        raise ConfigurationError(f"Plane API key for profile {selected!r} is missing. Run plane-workflow setup.")
    return StoredPlaneSettings(base_url=base_url, api_key=api_key, workspace=workspace, profile=selected)


def save_stored_plane_settings(*, base_url: str, workspace: str, api_key: str, profile: str = "default") -> Path:
    """Store the secret in the keyring and persist only non-secret settings."""
    normalized_url = base_url.rstrip("/").strip()
    normalized_workspace = workspace.strip()
    normalized_key = api_key.strip()
    if not normalized_url or not normalized_workspace or not normalized_key:
        raise ConfigurationError("Plane URL, workspace, and API key are all required.")
    try:
        keyring.set_password(KEYRING_SERVICE, profile, normalized_key)
    except KeyringError as error:
        raise ConfigurationError("Could not store the Plane API key in the operating-system keyring.") from error
    payload = _read_settings()
    profiles = payload.setdefault("profiles", {})
    if not isinstance(profiles, dict):
        raise ConfigurationError("Plane Workflow settings must contain a profiles object.")
    profiles[profile] = {"base_url": normalized_url, "workspace": normalized_workspace}
    payload["version"] = 1
    payload["active_profile"] = profile
    return _write_settings(payload)


def remove_stored_plane_settings(profile: str = "default") -> bool:
    """Remove a profile and its secret; return whether a profile existed."""
    payload = _read_settings()
    profiles = payload.get("profiles")
    existed = isinstance(profiles, dict) and profile in profiles
    if isinstance(profiles, dict):
        profiles.pop(profile, None)
        if payload.get("active_profile") == profile:
            payload["active_profile"] = next(iter(profiles), None)
        _write_settings(payload)
    try:
        keyring.delete_password(KEYRING_SERVICE, profile)
    except keyring.errors.PasswordDeleteError:
        pass
    except KeyringError as error:
        raise ConfigurationError("Could not remove the Plane API key from the operating-system keyring.") from error
    return existed
