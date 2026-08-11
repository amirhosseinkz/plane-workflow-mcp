#!/usr/bin/env bash

set -euo pipefail

ROOT="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"

cd "$ROOT"
if [ -n "${UV_COMMAND:-}" ]; then
  exec "$UV_COMMAND" run python main.py
fi
exec uv run python main.py
