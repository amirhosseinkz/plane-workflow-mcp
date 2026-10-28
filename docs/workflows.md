# Configure team workflows

[Back to the quick start](../README.md#quick-start) · [Copyable examples](examples.md)

## Project visibility and dependencies

Version 0.5.0 adds bounded-response, read-only work discovery. Use `list_work_items` for
text, state, assignee, label, module, cycle, priority, date, and overdue filters.
Use `get_project_briefing` for active-work totals and attention lists covering
overdue, stale, unassigned, unestimated, and unscheduled work.

Use `get_work_item_relations` to inspect dependencies. Relation direction is
always from the source item: `blocking` means the source blocks the targets;
`blocked_by` means the targets block the source. `add_work_item_relation`
previews the change, validates same-project targets, and verifies Plane retained
the requested relations after confirmation. Destructive relation removal is not
exposed because supported Plane versions do not provide one consistent,
unambiguous public removal contract.

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
    "default_cancelled_state_id": "<cancelled-state-id>",
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
5. Preview and apply `cancel_standard_work_item` with a factual reason when work
   should stop. It records the reason before moving to a configured cancelled
   state, and generic updates cannot bypass this lifecycle.

`complete_standard_work_item` can also record a Plane worklog when
`actual_minutes` is known active work time. Omit it when the duration is not
known. Never infer actual time from an estimate, fabricate human timing, or
delay a completed transition to make activity appear more human.
Set the planning `timezone` to the project's IANA timezone so generated and
actual lifecycle dates follow the team's local calendar.

## Backfill from git history

`plan_git_backfill(repo_path, since, until=None, author=None, include_uncommitted=False, module_map=None, max_gap_days=3)`
is read-only. It runs `git log` locally and groups commits in this order:

1. `module_map` path prefix, for example `{"apps/web/": "Web"}`.
2. Conventional-commit scope, for example `feat(auth): ...` goes to `auth`.
3. Top-level folder.

A group is split into separate items when work pauses longer than `max_gap_days`.

Each item gets:

- **Type:** `fix` commits make a Bug, and `feat`, `perf`, and `refactor` make an
  Improvement. Anything else is a Task.
- **Complexity:** set from the number of changed lines.
- **Dates:** the first and last commit dates, moved onto the project's business days.

The plan marks items that are already in Plane and lists similar existing titles. It is
saved locally for 24 hours.

`apply_git_backfill(plan_id, titles=None, modules=None, skip=None, allow_create_modules=False, dry_run=True)`
previews by default. With `dry_run=false`, each committed item is created, then started
on its first commit date. It is then completed with a comment that lists its commits
and says that no tests were run as part of the backfill. Uncommitted work
(`include_uncommitted=true`) is only started.

**Idempotency.** Each item's `external_id` comes from its first commit. Re-running a
plan, even after renaming items, never creates duplicates. A failure stops the run,
and running the same call again resumes from where it stopped.

**Completion dates.** Plane sets `completed_at` to the moment of the call. The
historical dates are kept in `start_date`, `target_date`, and the completion comment.

From a terminal:

```bash
plane-workflow backfill --since 2026-09-01 --module apps/web/=Web
plane-workflow backfill --since 2026-09-01 --module apps/web/=Web --apply --create-modules
```

The first command only prints the plan. The second asks for confirmation before
writing to Plane.

## Batch work, retries, and other projects

- **Rate limits.** Requests that Plane answers with HTTP 429 are retried with backoff
  (honoring `Retry-After`). If the limit persists, the error says so; it is never
  reported as a missing work item.
- **Safe retries.** Each create sends a stable `external_id` built from the project,
  title, and optional `idempotency_key`. If a create times out or conflicts, retrying
  it returns `already_created` with the existing item. Pass a distinct
  `idempotency_key` with `allow_duplicate=true` to create separate items that share
  a title.
- **Duplicate checks in batches.** Creation reuses one project listing for two
  minutes. An item someone else created with the same title inside that window may
  not be flagged.
- **Another project for one call.** Write tools reject a `project_id` that is not the
  active project. To change another project without switching, also pass
  `confirm_project_identifier` with that project's identifier (for example `WEB`).
- **Completion dates.** Plane records `completed_at` when the item moves to Done, so
  it is always the time of the completion call. Back-filled work keeps its real dates
  in `start_date`, `target_date`, and the completion comment.

## Reports

Ask the MCP client for a report in normal language, for example:

> Export this project's backlog and in-progress work items as a PDF, grouped by state.

The `export_work_items_report` tool produces `.docx` or `.pdf` reports. It
reads Plane data but does not change it. Treat generated reports as potentially
sensitive and store them outside the repository.
