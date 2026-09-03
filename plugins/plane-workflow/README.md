# Plane Workflow MCP

Plane Workflow MCP is a configurable MCP server and command-line setup tool
for using Plane work items from supported coding clients.

It provides:

- guided configuration for Codex, OpenCode, and Zed;
- operating-system keyring storage for Plane API keys;
- configurable project workflow profiles;
- advisory or strict planning with complexity, estimates, and business-day
  dates;
- preview-first start and completion operations with factual completion
  records;
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

## Configure planning

Call `get_project_workflow_context` before writing and
`get_workflow_options` before choosing assignment, state, cycle, or estimate
values. The options response returns Plane IDs for project members, states, and
estimate points. An estimate setting is an estimate-point ID, not the displayed
point number when the catalog is available. Self-hosted Plane versions that do
not expose that catalog can use non-negative numeric point mappings instead.
`default_labels` contains existing label names rather than IDs.

Planning profiles support two policies:

- `advisory` uses available defaults while allowing a work item to be created
  without every planning field;
- `strict` requires scope, complexity, assignment, an estimate mapping,
  planned dates, and an unstarted state.

The supported complexity values are `tiny`, `small`, `medium`, and `large`.
They describe breadth, risk, dependencies, uncertainty, and verification
effort; they do not represent actual elapsed time. Each value can map to a
Plane estimate-point ID and `lead_business_days`.

This generic strict override shows all v0.4.0 planning keys:

```json
{
  "planning": {
    "mode": "strict",
    "default_assignee_id": "<member-id-from-get_workflow_options>",
    "default_labels": ["<existing-label-name>"],
    "default_unstarted_state_id": "<backlog-or-unstarted-state-id>",
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

Pass the object to `validate_workflow_profile`. Then call
`save_project_workflow_profile` with the selected project and the validated
profile; review its preview before saving. Project-bound overrides are local
configuration. Do not commit a real profile or publish its Plane IDs.

When `complexity` is provided and dates are omitted,
`create_standard_work_item` sets `start_date` to the current day if it is a
configured business day, otherwise the next one. It computes `target_date`
from that date and the complexity's inclusive `lead_business_days`, skipping
days outside `business_days`. Explicit dates use `YYYY-MM-DD`.
Set `timezone` to the project's IANA timezone so automatically recorded dates
use the team's local calendar rather than the server's location.

## Plan, start, and complete work

Use the lifecycle tools in order and preview every mutation with `dry_run=true`
before applying it:

1. `create_standard_work_item` creates planned work. Supply `scope` and one of
   the four complexity values when strict planning is active. Configured
   assignment, labels, unstarted state, estimate point, and dates are applied
   unless explicit supported values override them.
2. `start_standard_work_item` records when implementation actually begins. It
   uses `default_started_state_id` unless `state_id` is supplied and uses the
   actual current date unless an explicit factual `start_date` is supplied.
3. `update_standard_work_item` handles non-completion edits. It cannot be used
   to move work directly to a completed state.
4. `complete_standard_work_item` requires the item to be started, a concise
   factual `summary`, and one or more `verification` entries that actually
   occurred. Optional implementation notes and follow-ups must also be factual.
   It records the comment before changing to `default_completed_state_id` or an
   explicitly supplied completed state.

Supply `actual_minutes` only when the positive whole number is known active
implementation and verification time. The tool then records an optional Plane
worklog before completing the state transition. Omit it when unknown; never
copy an estimate into actual time, fabricate human activity, or delay a
completed item to create a plausible-looking timeline.

Completion retries are designed to reuse the same completion comment and
worklog. If the tool returns `completion_pending`, report the failed stage,
resolve the API problem, and retry the same completion rather than creating a
manual duplicate record.

## Practical testing for v0.3.0 through v0.4.0

Test against a disposable workspace and project with sanitized names and a
least-privilege account.

1. Preview guided setup, complete it for a supported client, and verify status
   without displaying or storing an API key in client-visible configuration.
2. Cover the v0.3.x workspace/project flow by configuring two named workspaces,
   activating each one, choosing a project, and confirming each workspace
   retains its selection. Repeat with `list_configured_plane_workspaces`,
   `activate_plane_workspace`, `list_plane_projects`,
   `activate_plane_project`, and `get_active_plane_context`.
3. Verify v0.3.x project guards by supplying a conflicting project to a
   mutation and by referencing an item from another project; neither attempt
   should change Plane data.
4. Run `diagnose_plane_connection`, `get_project_workflow_context`, and
   `get_workflow_options`. Confirm state types, member IDs, estimate-point IDs,
   and reported capabilities match the selected disposable project.
5. Preview `validate_workflow_profile` and
   `save_project_workflow_profile`. In advisory mode, preview an item with
   partial planning. In strict mode, verify missing requirements fail, then
   exercise `tiny`, `small`, `medium`, and `large`; confirm default assignment,
   labels, states, estimate mappings, and dates skip non-business days.
6. Preview and apply a standard work item in the disposable project. Preview
   and apply its start, confirming the started state and factual start date.
7. Preview completion with a real summary and verification. Apply it without
   `actual_minutes` and confirm no worklog is created. On another disposable
   item, provide known active minutes and confirm comment, worklog, then state
   transition ordering. Retry a simulated `completion_pending` operation and
   confirm it does not duplicate the comment or worklog.
8. Verify `update_standard_work_item` rejects a direct completed-state
   transition. Run `audit_work_items` and a sanitized report export to retain
   coverage of the read-only workflow features.
9. Run the package checks:

```bash
uv sync --locked
uv lock --check
uv run python -m unittest discover -s tests -v
uv build
```

Before release, inspect the diff and build contents for credentials, real
workspace/project/member/state/estimate IDs, local profiles, generated reports,
and unrelated files.

For clone instructions, development, optional Mattermost bot setup, and
security guidance, see the repository README.
