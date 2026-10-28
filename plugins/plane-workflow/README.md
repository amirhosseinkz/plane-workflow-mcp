# Plane Workflow MCP

Keep Plane tasks in sync with your coding agent using configurable team workflows.
Draft structured tasks, preview changes, record completion evidence, and get
read-only project briefings or DOCX/PDF reports.

## Install and get your first result

Requires Python 3.11+, uv, and a Plane workspace with an API key.
Install from PyPI:

```bash
uv tool install plane-workflow-mcp
plane-workflow setup --client claude-code
plane-workflow project list
plane-workflow project activate PROJECT_ID
plane-workflow status
```

Replace `PROJECT_ID` with a listed ID. Setup also has `--client codex`, `cursor`,
`claude-desktop`, `opencode`, and `zed` adapters. Restart the client, then ask:

> Confirm my active Plane workspace and project, then show overdue and unassigned
> work. Include identifiers and totals, flag truncated lists, and do not change
> Plane data.

To use an unreleased checkout, run `uv tool install ./plugins/plane-workflow`
from the repository root instead.

## Workflow behavior

- Advisory planning accepts incomplete planning data; strict planning requires
  scope, complexity, assignment, an estimate mapping, dates, and an unstarted state.
- Project selection guards work-item mutations against conflicting projects.
- Completion requires a started item, a summary, and verification text; the
  completion record is written before the state transition.
- API keys are stored in the OS keyring by guided setup. Environment variables
  support headless use.

Preview supported writes with `dry_run=true` and ask the agent to wait for approval.
Some writes default to applying changes. Approval is a client workflow, not a
server-enforced human approval gate. Updates happen through tool calls, not a
background code-to-task sync.

## Documentation

- [Quick start and official-server comparison](https://github.com/amirhosseinkz/plane-workflow-mcp#readme)
- [Installation and client compatibility](https://github.com/amirhosseinkz/plane-workflow-mcp/blob/main/docs/installation.md)
- [Copyable workflow examples](https://github.com/amirhosseinkz/plane-workflow-mcp/blob/main/docs/examples.md)
- [Planning and workflow configuration](https://github.com/amirhosseinkz/plane-workflow-mcp/blob/main/docs/workflows.md)
- [Demo](https://github.com/amirhosseinkz/plane-workflow-mcp/blob/main/docs/demo.md)
- [Support](https://github.com/amirhosseinkz/plane-workflow-mcp/blob/main/SUPPORT.md)

MIT licensed. Independent community project; not affiliated with Plane.
