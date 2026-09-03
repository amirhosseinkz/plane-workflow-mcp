---
name: plane-workflow
description: Create, update, audit, standardize, label, and organize Plane work items with the Plane Workflow MCP tools. Use when a user asks to create a Plane task or issue, turn a brief into a ticket, manage modules, or improve a Plane backlog.
---

# Plane Workflow

Use the `plane-workflow` MCP tools as the primary path for Plane work. The tools resolve the active local Plane connection and apply a generic workflow with optional project-specific profiles.

## Start Safely

1. For a first-time connection, call `get_plane_workflow_setup_status`. If it returns `needs_setup`, tell the user to run `plane-workflow setup`; do not ask them to paste an API key into the chat or a client config file.
2. Call `get_active_plane_context` before work-item changes. If the workspace or project is wrong, use `list_configured_plane_workspaces` and `activate_plane_workspace`, then `list_plane_projects` and `activate_plane_project`.
3. For an existing connection or unexpected failure, call `diagnose_plane_connection` with the project ID. Do not guess which Plane capabilities are enabled.
4. Call `get_project_workflow_context` before writing. Use `get_workflow_options` for state, cycle, assignee, and Plane estimate-point IDs.
5. Use `get_project_workflow_profile` to inspect local project rules. Use `validate_workflow_profile` and `save_project_workflow_profile` to preview and explicitly save a project override.

## Reports

1. For a report request, translate the user's language into `export_work_items_report` filters and layout. Resolve names exactly as Plane presents them; for example, use `filters={"state_names": ["Backlog", "In Progress"]}` for a backlog/in-progress report.
2. Use the requested `format` (`docx` or `pdf`), choose `group_by` and `columns` that fit the question, and state that the export is read-only for Plane.
3. Return the report path and the selected work-item count. Do not modify or standardize work items as part of a report unless the user separately asks for that.

## Create and Update Work

1. Turn the request into context, module, surface, outcome, explicit scope, type, priority, and observable acceptance criteria. Use only details the user supplied or clearly implied.
2. Judge complexity as `tiny`, `small`, `medium`, or `large` from breadth, risk, dependencies, uncertainty, and verification effort. This is a planning judgment, not a claim about elapsed time.
3. Call `find_duplicate_candidates` when the request may overlap existing work. `create_standard_work_item` also stops exact and high-similarity duplicates unless the user deliberately allows one.
4. Call `create_standard_work_item` for new work. In strict mode the server requires scope, complexity, assignment, an estimate mapping, planned dates, and an unstarted state. Profile defaults are policy, not invented values.
5. Call `start_standard_work_item` when implementation begins. Preview first, then apply it so the actual start date and started state are recorded.
6. Call `update_standard_work_item` for non-completion changes to a specific item. It preserves labels and descriptions and rejects direct transitions to a completed state.
7. Never invent a release association; the diagnostic reports whether Plane supports it.

## Complete Work

1. Use `complete_standard_work_item` for every transition to Done. Do not use the generic update tool.
2. Supply a concise factual summary and at least one verification step that was actually performed. Include implementation notes and follow-ups only when they are real.
3. Supply `actual_minutes` only when actual active time is known. Never copy the estimate into actual time and never delay a completed task to make its timeline look human.
4. Preview the exact completion comment and state transition before applying them. The server records the comment and optional worklog before moving the item to Done.
5. If the result is `completion_pending`, report the failed stage and retry the same completion safely after the underlying API problem is resolved.

## Evidence

- Call `add_work_item_evidence_links` to preview evidence links first, then set `confirm=true` only after the links are reviewed.
- Call `upload_work_item_attachment` to preview a local file's name, size, and type. Set `confirm=true` only when the user has authorized upload of that file.

## Audit and Cleanup

1. Call `audit_work_items` for a read-only structural and quality review. Treat advisory findings as prompts for judgment, not automatic rewrites.
2. Call `create_standardization_plan` to save a deterministic cleanup proposal. Read it with `get_standardization_plan` and present its actions before writing.
3. Call `apply_standardization_plan` without confirmation for a final preview. Set `confirm=true` only after explicit approval. It skips items changed since the plan was created.

## Guardrails

- Do not hardcode a title prefix, product, language, module, or label taxonomy. The active project profile may define one.
- Prefer the active project rather than supplying `project_id` for mutations. The plugin rejects a conflicting project ID and checks that a referenced work item belongs to the selected project.
- Treat `Bug` and `Improvement` as type labels, not title prefixes or redundant description text.
- Preserve useful labels, descriptions, assignees, dates, and relationships when updating existing work.
- Do not fabricate elapsed time, testing, implementation difficulty, collaboration, or human activity. Natural wording must remain factual.
- Do not treat title similarity or audit advice as proof. Ask when a decision materially changes the work item.
