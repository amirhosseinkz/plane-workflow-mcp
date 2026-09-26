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

## Reports

Ask the MCP client for a report in normal language, for example:

> Export this project's backlog and in-progress work items as a PDF, grouped by state.

The `export_work_items_report` tool produces `.docx` or `.pdf` reports. It
reads Plane data but does not change it. Treat generated reports as potentially
sensitive and store them outside the repository.
