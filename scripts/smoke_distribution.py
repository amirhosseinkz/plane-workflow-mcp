#!/usr/bin/env python3
"""Install built artifacts outside the checkout and check CLI/MCP startup."""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import subprocess
import tempfile

MCP_CHECK = '''
import asyncio
import importlib.resources
import json
import sys
from fastmcp import Client
from fastmcp.client.transports import StdioTransport

async def check():
    profiles = importlib.resources.files("plane_workflow_mcp").joinpath("profiles.json")
    assert json.loads(profiles.read_text())["default"]["planning"]["mode"] == "advisory"
    transport = StdioTransport(command=sys.executable, args=["-m", "plane_workflow_mcp", "mcp"])
    async with Client(transport) as client:
        names = {tool.name for tool in await client.list_tools()}
        required = {"create_standard_work_item", "get_project_briefing", "complete_standard_work_item"}
        assert required <= names, required - names
    print("Bundled profiles and MCP discovery passed.")

asyncio.run(check())
'''


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path, help="directory containing the built wheel and sdist")
    args = parser.parse_args()
    artifacts = sorted(args.directory.resolve().glob("*.whl")) + sorted(args.directory.resolve().glob("*.tar.gz"))
    if not artifacts:
        parser.error("no distribution artifacts found")
    for artifact in artifacts:
        with tempfile.TemporaryDirectory(prefix="plane-workflow-smoke-") as directory:
            root = Path(directory)
            environment = os.environ.copy()
            # Do not inherit a developer's Plane credentials, profiles, or import paths.
            for key in tuple(environment):
                if key.startswith("PLANE_") or key in {"PYTHONPATH", "PYTHONHOME", "VIRTUAL_ENV"}:
                    environment.pop(key)
            environment["PLANE_WORKFLOW_HOME"] = str(root / "settings")
            venv = root / "venv"
            subprocess.run(["uv", "venv", str(venv)], check=True, cwd=root, env=environment)
            executable = venv / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
            subprocess.run(["uv", "pip", "install", "--python", str(executable), str(artifact)], check=True, cwd=root, env=environment)
            launcher = venv / ("Scripts/plane-workflow.exe" if os.name == "nt" else "bin/plane-workflow")
            command = [str(launcher)]
            subprocess.run([*command, "--help"], check=True, cwd=root, env=environment)
            client_config = root / "opencode.json"
            subprocess.run([
                *command, "setup", "--client", "opencode", "--config-file", str(client_config),
                "--dry-run", "--yes",
            ], check=True, cwd=root, env=environment)
            if client_config.exists() or (root / "settings").exists():
                raise RuntimeError("Setup preview unexpectedly wrote configuration")
            subprocess.run([str(executable), "-c", MCP_CHECK], check=True, cwd=root, env=environment, timeout=60)
            print(f"Distribution smoke check passed: {artifact.name}", flush=True)


if __name__ == "__main__":
    main()
