# Three workflows to try

Complete the [quick start](../README.md#quick-start) and select a project first.
These prompts are instructions to the agent, not an automatic approval mechanism.
Use `dry_run=true` explicitly for write previews and only apply the reviewed change
after approval. Resolve IDs from Plane instead of inventing them.

## 1. Turn a bug report into a structured task

```text
Confirm the active Plane workspace and project and read its workflow context.
Retrying checkout after a timeout can create two orders. Draft a bug to ensure
that retries create only one order. Scope it to checkout retry handling and its
regression tests. Acceptance criteria: repeating a request creates one order;
a failed first attempt can be retried; the existing successful flow still works.
Check for similar work, apply the project's available planning defaults, and ask
for any missing required information. Call create_standard_work_item with
work_item_type="bug" and dry_run=true. Show the preview and wait for my approval.
```

**Expected:** a duplicate/similarity warning or a preview containing the structured
description and planning fields. No Plane data changes during the preview. In
strict mode, missing required planning information must be resolved first.

After checking the preview, request application of those exact fields. The agent
should retrieve the resulting item and show its real identifier; an error is not
a successful creation.

## 2. Complete a task with verification

Use this only after work is implemented and verification has actually run. Replace
`ITEM_IDENTIFIER` with an existing started item. If work has not started, preview
and apply `start_standard_work_item` when implementation begins.

```text
Read ITEM_IDENTIFIER in my active Plane project and its workflow context.
Use only the implementation and verification evidence from this conversation to
draft its completion record. Ask me for missing evidence. Do not claim a test ran
unless we have its result. Preview complete_standard_work_item with dry_run=true,
show the summary, verification, and destination state, and wait for approval.
Omit actual_minutes because we have not measured active work time.
```

**Expected:** a completion preview or a clear explanation of missing evidence or
an invalid starting state. After approval, the completion operation writes the
record before the state change. If it returns `completion_pending`, resolve the
reported error and retry the same operation instead of adding a duplicate comment.
The server requires verification text; it cannot independently prove tests ran.

## 3. Get a project briefing and shareable report

```text
Confirm my active Plane workspace and project. Use get_project_briefing to show
active-work totals and overdue, stale, unassigned, unestimated, and unscheduled
items. Include identifiers and call out truncated lists. Do not change Plane data.
Inspect get_work_item_relations for an item only if I ask about its blockers.
```

**Expected:** totals and bounded attention lists. Categories may overlap, so do
not add their counts together as a unique-item total. Empty lists are valid.

To export after reviewing the briefing:

```text
Export this project's backlog and in-progress work as a PDF, grouped by state.
Save it outside the repository and show me the file path. Do not modify Plane data.
```

**Expected:** a local PDF through `export_work_items_report`. Report generation
writes a local file but does not update Plane. Check the contents before sharing.
