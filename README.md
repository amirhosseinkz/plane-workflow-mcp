# Plane Workflow MCP

**Keep Plane tasks in sync with your coding agent, using your team's workflow rules.**

Turn a bug description into a structured work item, preview changes before applying
them, and record verification when work is completed. An independent, open-source
[MCP](https://modelcontextprotocol.io/) server for [Plane](https://plane.so/).

## From a bug report to a planned task

> “Retrying checkout can create two orders. Draft a bug with acceptance criteria
> in the selected project. Show the preview before writing anything.”

| Step | What happens |
| --- | --- |
| Draft | The agent reads the project's workflow and checks for similar work. |
| Preview | You review the title, description, labels, and available planning fields. |
| Apply | After your approval, the agent calls the write operation. |
| Verify | The agent retrieves the created item and shows the result from Plane. |

This is an illustrative walkthrough, not a recording or a claim of measured time
saved. [Run the offline example or record the 45-second demo](docs/demo.md).

## Three useful workflows

- **Turn a bug into a reviewable task.** Include current behavior, expected behavior,
  scope, and acceptance criteria; apply configured planning defaults.
- **Close work with evidence.** Record a factual completion summary and verification
  before moving a started item to Done.
- **Find work that needs attention.** Get a read-only briefing of overdue, stale,
  unassigned, unestimated, and unscheduled work.

[Copy the prompts and expected results](docs/examples.md).

## Quick start

You need Python 3.11+, [uv](https://docs.astral.sh/uv/), a Plane workspace and API
key, and a client that can run a local MCP server.

Install the published **v0.5.0 GitHub release** without cloning:

```bash
uv tool install https://github.com/amirhosseinkz/plane-workflow-mcp/releases/download/v0.5.0/plane_workflow_mcp-0.5.0-py3-none-any.whl
plane-workflow setup --client codex
plane-workflow project list
```

Replace `PROJECT_ID` below with an ID from that list:

```bash
plane-workflow project activate PROJECT_ID
plane-workflow status
```

Setup checks access to Plane, stores the API key in your OS keyring, and registers
the server with the selected client. Use `--client opencode` or `--client zed`
for their setup adapters. Restart your client after setup.

For your first result, paste this into the client:

```text
Use Plane Workflow to confirm my active workspace and project, then show overdue
and unassigned work in that project. Include item identifiers and totals. Do not
change any Plane data. Tell me if a result list is truncated.
```

An empty list is a valid result. If no project is selected, select one before
retrying. [Installation, troubleshooting, and client compatibility](docs/installation.md).

The command above installs the released version; unreleased changes in this
checkout require the [source installation](docs/installation.md#from-source).
There is no PyPI release advertised yet.

## When to choose this or the official Plane MCP

Choose this server when you want configurable planning requirements, a structured
completion record, and project-specific workflows. Choose the official server
when you want broad Plane resource coverage or a hosted OAuth connection.

| Need | Plane Workflow MCP | Official Plane MCP |
| --- | --- | --- |
| Team planning rules | Advisory or strict profiles for required planning fields | General resource operations; no equivalent profile policy documented in the reviewed README |
| Review changes | Explicit `dry_run=true` previews for supported writes | Review/confirmation depends on the client; no equivalent preview workflow documented in the reviewed README |
| Completion | Dedicated operation requires a started item, summary, and verification | Work-item updates, comments, and worklogs available as operations |
| Reporting | Project attention briefings and DOCX/PDF exports | Work-item queries, counts, and grouping through PQL |
| Connection | Local stdio, API key, guided setup | Local stdio or hosted HTTP with OAuth/API token |

Comparison checked against the [official README at a pinned revision](https://github.com/makeplane/plane-mcp-server/blob/beee888f24fc65229a41bc4e0ede20cf4bc59444/README.md)
on September 27, 2026. “Not documented” does not mean impossible or unsupported.

**Review is a client workflow, not a server-enforced approval gate.** Ask your
agent to preview first and wait for your approval. Some write tools default to
`dry_run=false`; the server does not prove a human approved a call. Configured
planning requirements and lifecycle checks are enforced by the server. Tasks are
updated when the agent calls tools; there is no background code-to-task sync.

## Documentation

- [Installation and client compatibility](docs/installation.md)
- [Workflow examples](docs/examples.md)
- [Planning, lifecycle, dependencies, and reports](docs/workflows.md)
- [Offline demo and recording script](docs/demo.md)
- [Optional Mattermost bot](plugins/plane-workflow/mattermost-bot/README.md)
- [Development](CONTRIBUTING.md) · [Release checks](docs/releasing.md)
- [Support](SUPPORT.md) · [Security](SECURITY.md) · [Changelog](CHANGELOG.md)

MIT licensed. Community project; not affiliated with Plane.
