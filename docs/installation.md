# Installation and configuration

## Requirements

- Python 3.11 or newer
- [uv](https://docs.astral.sh/uv/)
- Access to a Plane instance, workspace, and API key
- One of Claude Code, Codex, Cursor, Claude Desktop, OpenCode, or Zed when using
  the guided client setup

## From source

For the current released wheel, use the [quick start](../README.md#quick-start).
To install unreleased changes, use a clone:

```bash
git clone https://github.com/amirhosseinkz/plane-workflow-mcp.git plane-workflow-mcp
cd plane-workflow-mcp
uv tool install ./plugins/plane-workflow
```

Run guided setup for a supported client:

```bash
plane-workflow setup --client codex
plane-workflow status
```

The setup command asks for the Plane base URL, workspace slug, and API key. It
stores the API key in your operating-system keyring and writes only non-secret
settings to the local configuration directory. It adds the MCP command to the
selected client after showing the pending change.

Other clients: `--client claude-code` (registers with `claude mcp add --scope user`),
`--client cursor` (`~/.cursor/mcp.json`), `--client claude-desktop`
(`claude_desktop_config.json`), `--client opencode`, or `--client zed`. You can preview a setup without writing anything:

```bash
plane-workflow setup --client codex --dry-run
```

For CI or an ephemeral environment, provide credentials through environment
variables instead of local setup:

```bash
export PLANE_BASE_URL="https://plane.example.test"
export PLANE_WORKSPACE_SLUG="example-workspace"
export PLANE_API_KEY="replace-with-a-secret-from-your-CI-store"
plane-workflow mcp
```

`PLANE_WORKFLOW_HOME` changes the local settings directory. Advanced workflow
profiles can be stored outside the repository with `PLANE_WORKFLOW_CONFIG`.
Never commit API keys, private profile files, or generated reports.

## Update

```bash
plane-workflow --version
plane-workflow status
```

`status` asks GitHub for the latest release. The request uses a three-second timeout
and sends no Plane data. If a newer version exists, `update_available.update_command`
holds the install command, for example
`uv tool install --force <wheel URL of the new release>`. Restart the client afterwards.
Set `PLANE_WORKFLOW_NO_UPDATE_CHECK=1` to skip the lookup.

## Workspaces and projects

Configure each Plane workspace with a unique profile, then select the active
workspace and project before creating or updating work items:

```bash
plane-workflow setup --profile client-a
plane-workflow workspace list
plane-workflow workspace activate client-a
plane-workflow project list
plane-workflow project activate PROJECT_ID
plane-workflow status
```

Replace `PROJECT_ID` with an ID from the project list.

Each workspace profile retains its own active project. MCP clients can use
`get_active_plane_context`, `list_configured_plane_workspaces`,
`activate_plane_workspace`, `list_plane_projects`, and
`activate_plane_project` for the same flow.

When an active project is selected, work-item mutation tools use it by default
and reject a conflicting `project_id`. They also confirm that a referenced work
item belongs to the selected project, preventing accidental changes in the
wrong project.

## Install the Codex plugin

The repository includes a Codex plugin marketplace entry:

```bash
codex plugin marketplace add https://github.com/amirhosseinkz/plane-workflow-mcp.git
codex plugin add plane-workflow@plane-workflow-community
```

Restart the client after installing a plugin. The standalone MCP installation
above works independently of the plugin.

## Optional Mattermost bot

The optional bot is for a team that wants approved Mattermost users to manage
Plane work items through direct messages. It is not installed with the MCP
server or Codex plugin.

```bash
cd plugins/plane-workflow/mattermost-bot
uv sync --locked
uv run python configure.py
uv run python main.py --check
uv run python main.py
```

The configuration helper should be given your own Mattermost URL, Plane URL,
workspace, project, credentials, and allowlist. It writes local secrets to
`.env`; do not commit that file or the bot's `data/` directory. The
`launch_agent.py` helper installs a macOS background service. On other
platforms, run the foreground command under your own process supervisor.

Every write is presented as a draft first. The bot should use a dedicated
least-privilege Plane service account and a restrictive direct-message
allowlist.

## Client compatibility

These are setup adapters, not a blanket claim that every version of each client
has been tested. Automated checks exercise generated configuration and mocked
CLI invocation. A live client-to-Plane session is a separate check.

| Client | Setup | Evidence in this repository | Live verification |
| --- | --- | --- | --- |
| Claude Code | `plane-workflow setup --client claude-code` | Mocked `claude mcp` registration test | Manual `claude mcp add` registration used in daily work; adapter not yet verified live |
| Cursor | `plane-workflow setup --client cursor` | `mcpServers` merge and removal test | Not verified |
| Claude Desktop | `plane-workflow setup --client claude-desktop` | `mcpServers` merge and removal test | Not verified |
| Codex | `plane-workflow setup --client codex` | Mocked `codex mcp` registration and replacement tests | Not verified for this documentation update |
| OpenCode | `plane-workflow setup --client opencode` | JSONC merge, backup, secret-free entry tests | Not verified for this documentation update |
| Zed | `plane-workflow setup --client zed` | Local context-server configuration test | Not verified for this documentation update |
| Other stdio clients | Manually register `plane-workflow mcp` | No dedicated setup adapter | Not verified |

For other clients, use their documented stdio configuration format with executable
`plane-workflow` and argument `mcp`. If the client cannot find it, use the absolute
executable path reported by `command -v plane-workflow` (PowerShell:
`(Get-Command plane-workflow).Source`). No API key belongs in the client command.
The OS user launching the server must have access to the configured keyring.

For JSON-configured clients (Cursor, Claude Desktop, OpenCode, Zed), `--config-file PATH`
overrides the settings path. Setup
preserves other JSON values and creates an initial `.plane-workflow-backup`;
comments are removed when JSONC is rewritten. Codex setup requires its CLI on PATH.

## First successful request

After selecting a project, restart the client and use the prompt from the
[quick start](../README.md#quick-start). The expected result is a read-only project
briefing with totals and item identifiers. A successful response with zero items
means the connection works; it does not mean setup failed.

Illustrative agent output (not a live result):

```text
Project: Example
Active items: 6
Overdue: 1 — EXAMPLE-12, Fix checkout retry
Unassigned: 2 — EXAMPLE-14, Add retry test; EXAMPLE-15, Review empty state
No Plane data changed.
```

## Troubleshooting

| Symptom | Next step |
| --- | --- |
| `plane-workflow` not found | Run `uv tool update-shell`, open a new shell, and retry. GUI clients may need the absolute executable path. |
| Connection validation fails | Check the API base URL, workspace slug, and API key permissions. Setup validates project access before saving. |
| Keyring error | Unlock/configure your OS keyring. For headless use, provide environment variables as shown above. |
| No active project | Run `plane-workflow project list`, then `plane-workflow project activate PROJECT_ID`. |
| Client does not list tools | Restart it and check its MCP logs and executable path. Avoid registering the plugin and standalone server twice. |
| Strict planning rejects creation | Read `get_workflow_options` and configure real state/member/estimate values; see [planning](workflows.md#planning-lifecycle). |

`plane-workflow status` reports stored configuration, not a fresh API health check.
Environment-only credentials are used by the MCP server but are not reflected as a
stored setup by `status`; use `diagnose_plane_connection` through the client.
