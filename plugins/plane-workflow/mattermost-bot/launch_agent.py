"""Install or remove the local macOS background service for this bot."""

from __future__ import annotations

import argparse
import os
import plistlib
import shutil
import subprocess
import sys
from pathlib import Path


LABEL = "com.planeworkflow.mattermost-bot"
ROOT = Path(__file__).resolve().parent
TARGET = Path.home() / "Library" / "LaunchAgents" / f"{LABEL}.plist"


def _require_macos() -> None:
    if sys.platform != "darwin":
        raise RuntimeError("The launch-agent helper is available only on macOS. Run main.py under your platform's process supervisor instead.")


def _uv_executable() -> str:
    configured = os.environ.get("UV_COMMAND", "").strip()
    if configured:
        return configured
    discovered = shutil.which("uv")
    if discovered:
        return discovered
    raise RuntimeError("uv is not installed or is not available in PATH. Install uv, or set UV_COMMAND to its executable path.")


def _service_specification() -> dict[str, object]:
    data_dir = ROOT / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    return {
        "Label": LABEL,
        "ProgramArguments": [_uv_executable(), "run", "python", str(ROOT / "main.py")],
        "WorkingDirectory": str(ROOT),
        "RunAtLoad": True,
        "KeepAlive": True,
        "ProcessType": "Background",
        "StandardOutPath": str(data_dir / "bot.log"),
        "StandardErrorPath": str(data_dir / "bot.error.log"),
    }


def install() -> None:
    _require_macos()
    TARGET.parent.mkdir(parents=True, exist_ok=True)
    domain = f"gui/{os.getuid()}"
    subprocess.run(["launchctl", "bootout", domain, str(TARGET)], check=False, capture_output=True)
    TARGET.write_bytes(plistlib.dumps(_service_specification()))
    subprocess.run(["launchctl", "bootstrap", domain, str(TARGET)], check=True)
    print(f"Installed and started {LABEL}.")


def uninstall() -> None:
    _require_macos()
    domain = f"gui/{os.getuid()}"
    subprocess.run(["launchctl", "bootout", domain, str(TARGET)], check=False, capture_output=True)
    TARGET.unlink(missing_ok=True)
    print(f"Removed {LABEL}.")


def main() -> int:
    parser = argparse.ArgumentParser(description="Manage the local Mattermost Plane bot service.")
    parser.add_argument("action", choices=("install", "uninstall"))
    action = parser.parse_args().action
    try:
        if action == "install":
            install()
        else:
            uninstall()
    except RuntimeError as error:
        parser.exit(2, f"Service was not changed: {error}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
