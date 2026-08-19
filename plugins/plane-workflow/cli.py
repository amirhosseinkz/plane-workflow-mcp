"""Install and operate Plane Workflow as a portable MCP command."""

from __future__ import annotations

import argparse
import getpass
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any, Callable

import configuration
import server


CLIENTS = ("codex", "opencode", "zed")


class SetupError(RuntimeError):
    """A setup issue that the user can safely correct."""


def _jsonc_to_json(text: str) -> str:
    """Remove JSONC comments and trailing commas without touching strings."""
    output: list[str] = []
    index = 0
    in_string = False
    escaped = False
    while index < len(text):
        character = text[index]
        following = text[index + 1] if index + 1 < len(text) else ""
        if in_string:
            output.append(character)
            if escaped:
                escaped = False
            elif character == "\\":
                escaped = True
            elif character == '"':
                in_string = False
            index += 1
            continue
        if character == '"':
            in_string = True
            output.append(character)
        elif character == "/" and following == "/":
            index = text.find("\n", index)
            if index == -1:
                break
            output.append("\n")
        elif character == "/" and following == "*":
            closing = text.find("*/", index + 2)
            if closing == -1:
                raise SetupError("The client configuration has an unterminated block comment.")
            index = closing + 1
        else:
            output.append(character)
        index += 1
    result = "".join(output)
    compact: list[str] = []
    index = 0
    in_string = False
    escaped = False
    while index < len(result):
        character = result[index]
        if in_string:
            compact.append(character)
            if escaped:
                escaped = False
            elif character == "\\":
                escaped = True
            elif character == '"':
                in_string = False
            index += 1
            continue
        if character == '"':
            in_string = True
            compact.append(character)
        elif character == ",":
            look_ahead = index + 1
            while look_ahead < len(result) and result[look_ahead].isspace():
                look_ahead += 1
            if look_ahead < len(result) and result[look_ahead] in "}]":
                index += 1
                continue
            compact.append(character)
        else:
            compact.append(character)
        index += 1
    return "".join(compact)


def _read_jsonc(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        payload = json.loads(_jsonc_to_json(path.read_text(encoding="utf-8")))
    except json.JSONDecodeError as error:
        raise SetupError(f"Could not parse client configuration: {path}") from error
    if not isinstance(payload, dict):
        raise SetupError(f"Client configuration must be a JSON object: {path}")
    return payload


def _write_json_config(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        backup = path.with_suffix(path.suffix + ".plane-workflow-backup")
        if not backup.exists():
            backup.write_text(path.read_text(encoding="utf-8"), encoding="utf-8")
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    temporary.replace(path)


def _opencode_config_path(override: str | None = None) -> Path:
    if override:
        return Path(override).expanduser()
    configured = os.getenv("OPENCODE_CONFIG")
    if configured:
        return Path(configured).expanduser()
    directory = Path(os.getenv("XDG_CONFIG_HOME", Path.home() / ".config")) / "opencode"
    jsonc_path = directory / "opencode.jsonc"
    return jsonc_path if jsonc_path.exists() else directory / "opencode.json"


def _zed_settings_path(override: str | None = None) -> Path:
    if override:
        return Path(override).expanduser()
    configured = os.getenv("ZED_SETTINGS_PATH")
    if configured:
        return Path(configured).expanduser()
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "Zed" / "settings.json"
    if os.name == "nt":
        return Path(os.getenv("APPDATA", Path.home())) / "Zed" / "settings.json"
    return Path(os.getenv("XDG_CONFIG_HOME", Path.home() / ".config")) / "zed" / "settings.json"


def _install_json_client(client: str, path: Path, *, dry_run: bool = False) -> Path:
    payload = _read_jsonc(path)
    if client == "opencode":
        payload.setdefault("$schema", "https://opencode.ai/config.json")
        mcp_servers = payload.setdefault("mcp", {})
        if not isinstance(mcp_servers, dict):
            raise SetupError("OpenCode config has a non-object mcp field.")
        mcp_servers["plane-workflow"] = {"type": "local", "command": ["plane-workflow", "mcp"], "enabled": True}
    elif client == "zed":
        servers = payload.setdefault("context_servers", {})
        if not isinstance(servers, dict):
            raise SetupError("Zed settings have a non-object context_servers field.")
        servers["plane-workflow"] = {"command": "plane-workflow", "args": ["mcp"], "env": {}}
    else:
        raise SetupError(f"Unsupported JSON-configured client: {client}")
    if not dry_run:
        _write_json_config(path, payload)
    return path


def _remove_json_client(client: str, path: Path, *, dry_run: bool = False) -> bool:
    payload = _read_jsonc(path)
    key = "mcp" if client == "opencode" else "context_servers"
    servers = payload.get(key)
    if not isinstance(servers, dict) or "plane-workflow" not in servers:
        return False
    servers.pop("plane-workflow")
    if not dry_run:
        _write_json_config(path, payload)
    return True


def _run_codex(arguments: list[str], runner: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run) -> subprocess.CompletedProcess[str]:
    try:
        return runner(["codex", "mcp", *arguments], text=True, capture_output=True, check=False)
    except OSError as error:
        raise SetupError("Codex CLI is not available on PATH.") from error


def _install_codex(*, dry_run: bool = False, runner: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run) -> str:
    if dry_run:
        return "codex mcp add plane-workflow -- plane-workflow mcp"
    current = _run_codex(["get", "plane-workflow"], runner)
    if current.returncode == 0:
        removed = _run_codex(["remove", "plane-workflow"], runner)
        if removed.returncode != 0:
            raise SetupError(f"Could not replace the existing Codex MCP server: {removed.stderr.strip()}")
    added = _run_codex(["add", "plane-workflow", "--", "plane-workflow", "mcp"], runner)
    if added.returncode != 0:
        raise SetupError(f"Could not configure Codex: {added.stderr.strip()}")
    return "Codex MCP configuration"


def _remove_codex(*, dry_run: bool = False, runner: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run) -> bool:
    if dry_run:
        return True
    result = _run_codex(["remove", "plane-workflow"], runner)
    if result.returncode != 0:
        if "not found" in result.stderr.casefold():
            return False
        raise SetupError(f"Could not remove the Codex MCP server: {result.stderr.strip()}")
    return True


def detected_clients() -> list[str]:
    binaries = {"codex": "codex", "opencode": "opencode", "zed": "zed"}
    return [client for client, binary in binaries.items() if shutil.which(binary)]


def _choose_client(requested: str | None, input_fn: Callable[[str], str] = input) -> str:
    if requested:
        return requested
    available = detected_clients()
    if len(available) == 1:
        return available[0]
    if not available:
        raise SetupError("No supported client was found. Re-run with --client codex, opencode, or zed.")
    options = ", ".join(f"{index + 1}) {client}" for index, client in enumerate(available))
    answer = input_fn(f"Choose a client ({options}): ").strip()
    if answer.isdigit() and 1 <= int(answer) <= len(available):
        return available[int(answer) - 1]
    if answer in available:
        return answer
    raise SetupError("Choose one of the detected clients.")


def _confirm(message: str, *, yes: bool, input_fn: Callable[[str], str] = input) -> bool:
    return yes or input_fn(f"{message} [y/N]: ").strip().casefold() in {"y", "yes"}


def _prompt(value: str | None, label: str, input_fn: Callable[[str], str] = input) -> str:
    answer = value or input_fn(f"{label}: ")
    if not answer.strip():
        raise SetupError(f"{label} is required.")
    return answer.strip()


def _validate_connection(base_url: str, workspace: str, api_key: str) -> None:
    try:
        api = server.PlaneApi(server.PlaneSettings(base_url=base_url, workspace=workspace, api_key=api_key))
        api.request("GET", "projects", params={"per_page": 1})
    except (server.PlaneWorkflowError, server.requests.RequestException, OSError) as error:
        raise SetupError("Plane could not validate this URL, workspace, and API key. Nothing was saved.") from error


def command_setup(arguments: argparse.Namespace) -> int:
    client = _choose_client(arguments.client)
    destination = (
        "your Codex MCP configuration" if client == "codex" else str(_opencode_config_path(arguments.config_file) if client == "opencode" else _zed_settings_path(arguments.config_file))
    )
    if not _confirm(f"Configure Plane Workflow for {client} and update {destination}?", yes=arguments.yes):
        print("Setup cancelled; no settings were changed.")
        return 0
    if arguments.dry_run:
        if client == "codex":
            preview = _install_codex(dry_run=True)
        else:
            path = _opencode_config_path(arguments.config_file) if client == "opencode" else _zed_settings_path(arguments.config_file)
            _install_json_client(client, path, dry_run=True)
            preview = f"would update {path} with plane-workflow -> plane-workflow mcp"
        print(f"Setup preview for {client}: {preview}. No credentials or client settings were changed.")
        return 0
    base_url = _prompt(arguments.base_url, "Plane base URL")
    workspace = _prompt(arguments.workspace, "Plane workspace slug")
    api_key = os.getenv("PLANE_API_KEY") if arguments.non_interactive else getpass.getpass("Plane API key (stored in your OS keyring): ")
    if not api_key:
        raise SetupError("Plane API key is required.")
    _validate_connection(base_url, workspace, api_key)
    profile_path = configuration.save_stored_plane_settings(base_url=base_url, workspace=workspace, api_key=api_key, profile=arguments.profile)
    if client == "codex":
        configured = _install_codex(dry_run=arguments.dry_run)
    else:
        configured = _install_json_client(client, _opencode_config_path(arguments.config_file) if client == "opencode" else _zed_settings_path(arguments.config_file), dry_run=arguments.dry_run)
    print(f"Plane Workflow is configured for {client}. Settings: {profile_path}. Client: {configured}.")
    return 0


def command_status(arguments: argparse.Namespace) -> int:
    try:
        settings = configuration.load_stored_plane_settings(arguments.profile)
    except configuration.ConfigurationError as error:
        print(json.dumps({"status": "needs_setup", "configured": False, "next_command": "plane-workflow setup", "reason": str(error)}, indent=2))
        return 1
    print(
        json.dumps(
            {
                "status": "configured" if settings else "needs_setup",
                "configured": settings is not None,
                "profile": settings.profile if settings else None,
                "base_url": settings.base_url if settings else None,
                "workspace": settings.workspace if settings else None,
                "active_project": _project_view(settings.active_project) if settings else None,
                "detected_clients": detected_clients(),
                "next_command": None if settings else "plane-workflow setup",
            },
            indent=2,
        )
    )
    return 0 if settings else 1


def _project_view(project: configuration.StoredPlaneProject | None) -> dict[str, str | None] | None:
    if project is None:
        return None
    return {"id": project.id, "identifier": project.identifier, "name": project.name}


def command_workspace_list(_: argparse.Namespace) -> int:
    profiles = configuration.list_stored_plane_profiles()
    print(
        json.dumps(
            {
                "status": "configured" if profiles else "needs_setup",
                "workspaces": [
                    {
                        "profile": profile.profile,
                        "base_url": profile.base_url,
                        "workspace": profile.workspace,
                        "active": profile.active,
                        "active_project": _project_view(profile.active_project),
                    }
                    for profile in profiles
                ],
            },
            indent=2,
        )
    )
    return 0 if profiles else 1


def command_workspace_activate(arguments: argparse.Namespace) -> int:
    profile = configuration.activate_stored_plane_profile(arguments.profile)
    print(
        json.dumps(
            {
                "status": "activated",
                "workspace": profile.workspace,
                "profile": profile.profile,
                "active_project": _project_view(profile.active_project),
            },
            indent=2,
        )
    )
    return 0


def _active_stored_settings() -> configuration.StoredPlaneSettings:
    settings = configuration.load_stored_plane_settings()
    if settings is None:
        raise SetupError("No active Plane workspace is configured. Run plane-workflow setup first.")
    return settings


def command_project_list(_: argparse.Namespace) -> int:
    settings = _active_stored_settings()
    api = server.PlaneApi(
        server.PlaneSettings(
            base_url=settings.base_url,
            workspace=settings.workspace,
            api_key=settings.api_key,
            profile=settings.profile,
        )
    )
    projects = api.projects()
    print(
        json.dumps(
            {
                "status": "projects",
                "workspace": settings.workspace,
                "active_project": _project_view(settings.active_project),
                "projects": [
                    {"id": project.get("id"), "identifier": project.get("identifier"), "name": project.get("name")}
                    for project in projects
                ],
            },
            indent=2,
        )
    )
    return 0


def command_project_activate(arguments: argparse.Namespace) -> int:
    settings = _active_stored_settings()
    api = server.PlaneApi(
        server.PlaneSettings(
            base_url=settings.base_url,
            workspace=settings.workspace,
            api_key=settings.api_key,
            profile=settings.profile,
        )
    )
    project = api.project(arguments.project_id)
    active_project = configuration.set_stored_active_project(
        profile=settings.profile,
        project_id=str(project.get("id") or arguments.project_id),
        identifier=str(project["identifier"]) if project.get("identifier") else None,
        name=str(project["name"]) if project.get("name") else None,
    )
    print(
        json.dumps(
            {
                "status": "activated",
                "workspace": settings.workspace,
                "profile": settings.profile,
                "active_project": _project_view(active_project),
            },
            indent=2,
        )
    )
    return 0


def command_remove(arguments: argparse.Namespace) -> int:
    client = _choose_client(arguments.client)
    if not _confirm(f"Remove Plane Workflow from {client} and delete profile {arguments.profile!r}?", yes=arguments.yes):
        print("Removal cancelled; no settings were changed.")
        return 0
    if client == "codex":
        removed_client = _remove_codex(dry_run=arguments.dry_run)
    else:
        path = _opencode_config_path(arguments.config_file) if client == "opencode" else _zed_settings_path(arguments.config_file)
        removed_client = _remove_json_client(client, path, dry_run=arguments.dry_run)
    removed_profile = configuration.remove_stored_plane_settings(arguments.profile) if not arguments.dry_run else True
    print(f"Removed client entry: {removed_client}. Removed profile: {removed_profile}.")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="plane-workflow", description="Plane Workflow MCP setup and launcher")
    subcommands = parser.add_subparsers(dest="command")
    setup = subcommands.add_parser("setup", help="configure a client and securely store Plane credentials")
    setup.add_argument("--client", choices=CLIENTS)
    setup.add_argument("--profile", default="default")
    setup.add_argument("--base-url")
    setup.add_argument("--workspace")
    setup.add_argument("--config-file", help="override the OpenCode or Zed settings path")
    setup.add_argument("--non-interactive", action="store_true", help="read the API key from PLANE_API_KEY")
    setup.add_argument("--dry-run", action="store_true")
    setup.add_argument("--yes", action="store_true", help="skip the client-change confirmation")
    setup.set_defaults(handler=command_setup)
    status = subcommands.add_parser("status", help="show setup status without exposing credentials")
    status.add_argument("--profile")
    status.set_defaults(handler=command_status)
    workspace = subcommands.add_parser("workspace", help="list or switch configured Plane workspaces")
    workspace_commands = workspace.add_subparsers(dest="workspace_command", required=True)
    workspace_commands.add_parser("list", help="list configured workspaces and their selected projects").set_defaults(handler=command_workspace_list)
    workspace_activate = workspace_commands.add_parser("activate", help="switch the active workspace profile")
    workspace_activate.add_argument("profile")
    workspace_activate.set_defaults(handler=command_workspace_activate)
    project = subcommands.add_parser("project", help="list or switch projects in the active workspace")
    project_commands = project.add_subparsers(dest="project_command", required=True)
    project_commands.add_parser("list", help="list projects in the active workspace").set_defaults(handler=command_project_list)
    project_activate = project_commands.add_parser("activate", help="select a project for work-item operations")
    project_activate.add_argument("project_id")
    project_activate.set_defaults(handler=command_project_activate)
    remove = subcommands.add_parser("remove", help="remove a configured client and local credentials")
    remove.add_argument("--client", choices=CLIENTS)
    remove.add_argument("--profile", default="default")
    remove.add_argument("--config-file")
    remove.add_argument("--dry-run", action="store_true")
    remove.add_argument("--yes", action="store_true")
    remove.set_defaults(handler=command_remove)
    subcommands.add_parser("mcp", help="start the stdio MCP server").set_defaults(handler=lambda _: server.mcp.run() or 0)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    arguments = parser.parse_args(argv)
    if not getattr(arguments, "command", None):
        parser.print_usage()
        print("First-time setup: plane-workflow setup")
        return 2
    try:
        return int(arguments.handler(arguments))
    except (SetupError, configuration.ConfigurationError, server.PlaneWorkflowError) as error:
        print(f"Error: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
