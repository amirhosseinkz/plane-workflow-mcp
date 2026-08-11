# Plane Workflow MCP

Plane Workflow MCP is an open-source [Model Context Protocol
(MCP)](https://modelcontextprotocol.io/) server for [Plane](https://plane.so/)
project management. It lets Codex and other AI coding clients create, update,
audit, and export Plane work items through configurable workflows, read-only
reporting, and guarded write operations. The repository also contains an
optional Mattermost direct-message bot that uses the same workflow rules.

Licensed under the [MIT License](LICENSE).

## Requirements

- Python 3.11 or newer
- [uv](https://docs.astral.sh/uv/)
- Access to a Plane instance, workspace, and API key
- One of Codex, OpenCode, or Zed when using the guided client setup

## Install the standalone MCP server

Until a package release is published, install from a clone of this repository.

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

To configure OpenCode or Zed instead, pass `--client opencode` or
`--client zed`. You can preview a setup without writing anything:

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

## Reports

Ask the MCP client for a report in normal language, for example:

> Export this project's backlog and in-progress work items as a PDF, grouped by state.

The `export_work_items_report` tool produces `.docx` or `.pdf` reports. It
reads Plane data but does not change it. Treat generated reports as potentially
sensitive and store them outside the repository.

## Development

The core MCP server and optional bot have separate locked environments.

```bash
cd plugins/plane-workflow
uv sync --locked
uv lock --check
uv run python -m unittest discover -s tests -v
uv build
```

```bash
cd plugins/plane-workflow/mattermost-bot
uv sync --locked
uv lock --check
uv run python -m unittest discover -s tests -v
```

The GitHub Actions workflow runs these checks for every pull request. See
[CONTRIBUTING.md](CONTRIBUTING.md) for contribution expectations, the
[security policy](SECURITY.md) for private vulnerability reporting, and
[SUPPORT.md](SUPPORT.md) for help channels.

## Publishing checklist

Before making a release, maintainers should:

1. Confirm the MIT license remains appropriate for the intended distribution.
2. Confirm GitHub repository metadata, marketplace name, and package project
   URLs match the release destination.
3. Enable GitHub private vulnerability reporting and configure repository
   discussions or support channels.
4. Verify that no organization-specific endpoints, project identifiers,
   reports, credentials, local profiles, or generated artifacts are present in
   the files or Git history being published.
5. Create a tagged release only after CI is green.
