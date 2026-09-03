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

## Planning lifecycle

Version 0.4.0 adds a preview-first lifecycle for planning, starting, and
completing work. Project workflow profiles can use either planning mode:

- `advisory` applies configured defaults when available but permits incomplete
  planning data;
- `strict` requires scope, a `tiny`, `small`, `medium`, or `large` complexity,
  assignment, an unstarted state, an estimate mapping, and planned dates before
  creation.

Complexity is a planning judgment based on scope, risk, dependencies,
uncertainty, and verification effort. It is not elapsed time. A profile can map
each complexity to a Plane estimate-point ID, or a non-negative numeric point
value on self-hosted servers without the estimate catalog, plus a positive
number of lead business days. When complexity is supplied and dates are
omitted, the server chooses the current or next configured business day for
`start_date` and counts configured business days through `target_date`.

Use `get_workflow_options` to obtain valid member, state, and available
estimate-point IDs before configuring defaults. Labels are configured by name.
A generic strict planning override looks like this:

```json
{
  "planning": {
    "mode": "strict",
    "default_assignee_id": "<member-id>",
    "default_labels": ["<existing-label-name>"],
    "default_unstarted_state_id": "<unstarted-state-id>",
    "default_started_state_id": "<started-state-id>",
    "default_completed_state_id": "<completed-state-id>",
    "timezone": "UTC",
    "business_days": ["monday", "tuesday", "wednesday", "thursday", "friday"],
    "complexity": {
      "tiny": {"estimate": 1, "lead_business_days": 1},
      "small": {"estimate": 2, "lead_business_days": 2},
      "medium": {"estimate": 3, "lead_business_days": 4},
      "large": {"estimate": 5, "lead_business_days": 7}
    }
  }
}
```

Preview the override with `validate_workflow_profile`, then use
`save_project_workflow_profile` first as a preview and only save it after
review. Keep real IDs in the local profile location, not in repository examples
or bug reports.

The standard lifecycle is:

1. Preview and create planned work with `create_standard_work_item`.
2. Preview and apply `start_standard_work_item` when implementation actually
   begins; it records the actual start date and a valid started state.
3. Use `update_standard_work_item` for non-completion changes.
4. Preview and apply `complete_standard_work_item` with a factual summary and
   verification that actually occurred. It records the completion comment
   before moving the item to a configured completed state.

`complete_standard_work_item` can also record a Plane worklog when
`actual_minutes` is known active work time. Omit it when the duration is not
known. Never infer actual time from an estimate, fabricate human timing, or
delay a completed transition to make activity appear more human.
Set the planning `timezone` to the project's IANA timezone so generated and
actual lifecycle dates follow the team's local calendar.

## Workspaces and projects

Configure each Plane workspace with a unique profile, then select the active
workspace and project before creating or updating work items:

```bash
plane-workflow setup --profile client-a
plane-workflow workspace list
plane-workflow workspace activate client-a
plane-workflow project list
plane-workflow project activate <project-id>
plane-workflow status
```

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

## Practical release testing

Use a disposable Plane workspace and project, generic test data, and a
least-privilege account. Do not put credentials or real organization IDs in
fixtures, command output, screenshots, or reports.

1. Run `plane-workflow setup --client <client> --dry-run`, complete setup, and
   verify `plane-workflow status` without exposing the API key.
2. Exercise the v0.3.x context flow: configure two workspace profiles, switch
   with `workspace activate`, select a project with `project activate`, and
   confirm each workspace retains its selected project. Repeat through the MCP
   workspace/project list and activation tools.
3. In a disposable second project, verify a mutation with a conflicting
   `project_id` is rejected and an item from the wrong project is not changed.
4. Run `diagnose_plane_connection`, `get_project_workflow_context`, and
   `get_workflow_options`; confirm capabilities and IDs reflect the selected
   project. Preview profile validation and saving before persisting an override.
5. In `advisory` mode, preview creation with partial planning data. In `strict`
   mode, confirm incomplete planning is rejected, then preview all four
   complexity values and verify configured defaults, estimate-point IDs, and
   business-day dates.
6. In the disposable project, preview and apply creation, start, and completion.
   Confirm start records the real start date; completion requires a factual
   summary plus real verification, writes its comment before Done, and creates
   a worklog only when a known `actual_minutes` value is supplied. Retry any
   `completion_pending` result and confirm records are not duplicated.
7. Confirm generic updates cannot bypass the completion lifecycle. Run a
   read-only audit and export a sanitized DOCX or PDF report.
8. Run the automated checks shown above and inspect the release diff to ensure
   it contains no credentials, private IDs, generated reports, or unrelated
   artifacts.

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
