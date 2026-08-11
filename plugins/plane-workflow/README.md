# Plane Workflow MCP

Plane Workflow MCP is a configurable MCP server and command-line setup tool
for using Plane work items from supported coding clients.

It provides:

- guided configuration for Codex, OpenCode, and Zed;
- operating-system keyring storage for Plane API keys;
- configurable project workflow profiles;
- read-only work-item report exports; and
- preview-first operations for changes to Plane work items.

## Installation

This project is currently distributed from source rather than a package
registry. Use Python 3.11 or newer, clone the public repository, and from the
repository root install the local package with uv:

```bash
uv tool install ./plugins/plane-workflow
plane-workflow setup
```

After a maintainer publishes a registry release, the package can instead be
installed with `uv tool install plane-workflow-mcp`.

The setup command securely collects a Plane base URL, workspace slug, and API
key, then configures a selected client. For non-interactive environments, use
the `PLANE_BASE_URL`, `PLANE_WORKSPACE_SLUG`, and `PLANE_API_KEY` environment
variables.

For clone instructions, development, optional Mattermost bot setup, and
security guidance, see the repository README.
