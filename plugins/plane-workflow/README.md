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
key, then configures a selected client. Run setup again with a unique profile
name to add another workspace, for example
`plane-workflow setup --profile client-a`. For non-interactive environments,
use the `PLANE_BASE_URL`, `PLANE_WORKSPACE_SLUG`, and `PLANE_API_KEY`
environment variables.

## Workspace and project context

Each configured workspace profile has its own active project. The selected
workspace and project are shown by `plane-workflow status` and are used by the
MCP work-item tools when `project_id` is omitted.

```bash
plane-workflow workspace list
plane-workflow workspace activate client-a
plane-workflow project list
plane-workflow project activate <project-id>
```

The MCP server provides equivalent tools: `list_configured_plane_workspaces`,
`activate_plane_workspace`, `get_active_plane_context`, `list_plane_projects`,
and `activate_plane_project`.

Before a work-item mutation, the plugin confirms that the work item is in the
selected project. When an active project is selected, mutation tools also
reject a conflicting `project_id`; switch projects first instead of risking a
change in the wrong project.

For clone instructions, development, optional Mattermost bot setup, and
security guidance, see the repository README.
