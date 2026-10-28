# Plane Workflow MCP

**Your git history already knows what you did. Let your agent put it in Plane.**

An open-source [MCP](https://modelcontextprotocol.io/) server for [Plane](https://plane.so/),
including self-hosted Plane. It turns weeks of commits into planned, started, and
completed Plane work items, dated on your business days, with completion notes
that cite the commits. Day to day, Claude Code, Codex, Cursor, and other agents use
it to plan, start, and complete work under your team's rules, previewing every change first.

[![CI](https://github.com/amirhosseinkz/plane-workflow-mcp/actions/workflows/ci.yml/badge.svg)](https://github.com/amirhosseinkz/plane-workflow-mcp/actions/workflows/ci.yml)

![Offline demo: git history becomes a previewed backfill plan, then completed Plane items that cite their commits](docs/demo-backfill.gif)

<sub>Offline demo: the real server code runs against a test fixture with synthetic data.
[Reproduce it](docs/demo.md).</sub>

## What it does

- **Backfill Plane from git.** `plan_git_backfill` reads `git log` and groups commits
  into work items by module, scope, or folder. Dates come from the commits and are
  moved onto your business days. Nothing is written until you approve the plan.
  `apply_git_backfill` then creates, starts, and completes each item, with a comment
  listing its commits. Re-running it never duplicates items. Also available as
  `plane-workflow backfill --since 2026-09-01`.
- **Plan → start → complete, with evidence.** New work gets scope, acceptance
  criteria, assignee, estimate, and start/target dates that skip your non-business
  days. Completion requires a started item, a factual summary, and real
  verification. It never fabricates either.
- **Preview first, safe to retry.** Write tools support `dry_run` previews. Creates
  check for duplicates and are idempotent, so a timeout followed by a retry does not
  create a second item. Rate limits are retried with backoff.
- **Know what needs attention.** Read-only briefings list overdue, stale, unassigned,
  unestimated, and unscheduled work. Reports export to DOCX or PDF.
- **Never touch the wrong project.** Writes are tied to the selected workspace and
  project, unless one call explicitly confirms another project's identifier.

## Quick start

Requires Python 3.11+, [uv](https://docs.astral.sh/uv/), and a Plane API key.

```bash
uv tool install plane-workflow-mcp
plane-workflow setup --client claude-code
```

Setup asks for your Plane URL, workspace, and API key. It checks the connection,
stores the key in your OS keyring, and registers the server with your client. Other
clients: `--client codex`, `cursor`, `claude-desktop`, `opencode`, or `zed`; any other
stdio client can run `plane-workflow mcp`. Add `--dry-run` to see the change first.

Using Claude Code? You can [install it as a plugin](docs/installation.md#install-the-claude-code-plugin)
instead, which also adds a skill for using the tools safely.

Select a project, then restart your client:

```bash
plane-workflow project list
plane-workflow project activate PROJECT_ID
```

### Update

`plane-workflow status` shows your version and tells you when a newer release
exists. Update with `uv tool install --force plane-workflow-mcp`, then restart your client. Your
setup, API key, and selected project are kept, so there is no need to run setup again.

## First prompt

```text
Read this repository's git history since September 1 and propose Plane work items
for it with plan_git_backfill. Show me the plan as a table. Do not write anything
to Plane until I approve.
```

Or start read-only:

```text
Use Plane Workflow to confirm my active workspace and project, then show overdue
and unassigned work in that project with identifiers and totals. Do not change
any Plane data.
```

Then try a write with a preview:

```text
Retrying checkout can create two orders. Draft a bug with acceptance criteria in
the active project using its workflow rules. Show the dry-run preview and wait for
my approval before creating it.
```

[More prompts with expected results](docs/examples.md) ·
[Run the offline demo](docs/demo.md)

## How it compares

The [official Plane MCP server](https://github.com/makeplane/plane-mcp-server) gives
broad access to Plane resources and hosted OAuth. This server adds a workflow layer
on top of Plane: planning rules, an enforced lifecycle, previews, idempotent writes,
and completion records. You can install both.
[Detailed comparison](docs/comparison.md).

Review happens in your client. The server enforces planning rules and lifecycle
checks, but it cannot prove a human approved a call. Plane is updated when the agent
calls a tool; there is no background sync.

## Documentation

- [Installation, clients, and troubleshooting](docs/installation.md)
- [Planning rules, lifecycle, batch work, and reports](docs/workflows.md)
- [Workflow examples](docs/examples.md) · [Offline demo](docs/demo.md)
- [Optional Mattermost bot](plugins/plane-workflow/mattermost-bot/README.md)
- [Roadmap](docs/roadmap-100-stars.md) · [Changelog](CHANGELOG.md)
- [Contributing](CONTRIBUTING.md) · [Support](SUPPORT.md) · [Security](SECURITY.md)

MIT licensed. Community project, not affiliated with Plane.
