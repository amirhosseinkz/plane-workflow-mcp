# Changelog

All notable changes to this project are documented in this file. The project
uses [Semantic Versioning](https://semver.org/).

## [Unreleased]

## [0.7.0] - 2026-10-28

### Added

- Backfill Plane from git history. `plan_git_backfill` reads `git log`, groups commits
  into work items, and dates them on the project's business days without writing
  anything. `apply_git_backfill` previews, then creates, starts, and completes each
  item with a completion comment that cites its commits. Uncommitted work is only
  started. Re-runs resume without duplicates. Also available as `plane-workflow backfill`.

### Changed

- When an `idempotency_key` is given, the creation `external_id` depends only on the
  project and the key, so a retry with a changed title still returns the first item.

## [0.6.1] - 2026-10-28

### Added

- Official MCP Registry metadata (`server.json`, name
  `io.github.amirhosseinkz/plane-workflow-mcp`). The publish workflow registers each
  release after uploading it to PyPI.
- `glama.json` listing the maintainer for the Glama directory.

### Changed

- Install and update from PyPI: `uv tool install plane-workflow-mcp`. The update
  hint in `plane-workflow status` now uses the PyPI command.
- Dependency updates; fastmcp stays below 4.

## [0.6.0] - 2026-10-28

### Added

- Outcome-led quick start, sourced official-server comparison, client compatibility
  matrix, and copyable task, completion, and briefing workflows.
- Reproducible offline creation preview and a live-demo recording script.
- Clean-install distribution smoke checks for the CLI, bundled profiles, and MCP
  tool discovery.

- README animation rendered from an offline walkthrough of the real create flow
  (`scripts/demo_walkthrough.py`, `scripts/render_demo_gif.py`).
- Claude Code plugin marketplace (`/plugin marketplace add amirhosseinkz/plane-workflow-mcp`)
  with the MCP server and the Plane Workflow skill, and `setup --client none` to
  store credentials without registering a client.
- Guided setup for Claude Code (`--client claude-code`, user scope), Cursor, and
  Claude Desktop. Clients launched from a desktop app get the absolute launcher path.
- `idempotency_key` on `create_standard_work_item`. Creates carry a stable
  `external_id`, so a retry after a timeout or conflict returns the existing item
  (`already_created`) instead of creating a duplicate.
- `plane-workflow --version`, and `plane-workflow status` reports the installed
  version and, when a newer GitHub release exists, the command to update.
- `confirm_project_identifier` on project-scoped write tools changes a non-active
  project for one call when it matches that project's identifier; the active
  project is unchanged.

### Changed

- Plane requests retry HTTP 429 (honoring `Retry-After`) and, for reads, 502/503/504
  and network errors with exponential backoff. Writes that get no response are not
  resent and are reported as possibly applied.
- Creation reuses one project work-item listing for two minutes for duplicate
  checks, instead of paging the whole project on every create.
- Quick start installs the existing versioned GitHub wheel without cloning.
- The modules now ship inside the `plane_workflow_mcp` package instead of as
  top-level `cli`, `server`, `configuration`, and `reports` modules. The
  `plane-workflow` command is unchanged; `python -m plane_workflow_mcp` also works.
- Successful guided setup explains project selection and suggests a read-only
  first request.
- Advanced setup, workflow, and release instructions moved into dedicated guides.

### Fixed

- Rate-limit, server, and network failures are no longer reported as "work item
  was not found in project"; only HTTP 404 gets that explanation.
- Setting an estimate on a project without estimate points returns an actionable
  error instead of a bare HTTP 400.

## [0.5.0] - 2026-09-04

### Added

- Bounded-response `list_work_items` queries with local filters that work across Plane
  editions.
- Read-only `get_project_briefing` summaries for overdue, stale, unassigned,
  unestimated, and unscheduled active work.
- Read-only work-item relation inspection and preview-first, same-project
  relation creation with post-write verification.
- Preview-first `cancel_standard_work_item` lifecycle with a factual,
  retry-safe cancellation record.

### Changed

- Mattermost routing can use project briefings, filtered work-item lists,
  relations, and the cancellation lifecycle; the companion bot is versioned
  as 0.3.0.
- Plane API failures include a bounded, sanitized server detail when one is
  available.

### Fixed

- Work-item pagination now follows Plane's cursor contract and reads
  `total_results`, preventing repeated first-page results in projects with more
  than 100 work items.
- Connection diagnostics now use the selected project when no explicit project
  ID is supplied.

### Safety

- Generic work-item updates can no longer bypass the dedicated cancellation
  lifecycle.
- Relation creation validates every target against the selected project,
  requires review of relation direction, and reports targets Plane silently
  omitted.

## [0.4.0] - 2026-09-03

### Added

- Advisory and strict project planning profiles with `tiny`, `small`,
  `medium`, and `large` complexity policies.
- Configurable default assignee, labels, unstarted/started/completed states,
  timezone, business days, and complexity-to-estimate-point mappings.
- Business-day planning of start and target dates when complexity is supplied.
- Numeric estimate mappings for self-hosted Plane versions that do not expose
  the estimate-point catalog endpoint.
- Preview-first `start_standard_work_item` and
  `complete_standard_work_item` lifecycle tools.
- Factual completion comments and optional `actual_minutes` Plane worklogs.

### Changed

- Standard creation now applies configured planning defaults and, in strict
  mode, requires scope, complexity, assignment, an estimate mapping, dates, and
  an unstarted state.
- Ordinary task creation now applies the default `Task` type label in addition
  to the existing Bug and Improvement type labels.
- Standard updates no longer permit direct transitions to completed states;
  completion goes through the dedicated lifecycle operation.
- Plugin metadata, prompts, and documentation now describe planning, starting,
  completion, and practical v0.3.x-v0.4.0 verification.

### Safety

- Start and completion mutations support previews, validate state types, and
  retain active-project and wrong-project protections.
- Completion records are written before the completed-state transition and can
  be retried without duplicating matching comments or worklogs.
- Completion guidance forbids fabricated verification or timing, copying an
  estimate into actual time, and delaying completion to imitate human activity.

## [0.3.1] - 2026-08-19

### Changed

- Documented workspace and project selection, switching, and wrong-project
  safety checks in the repository README.

## [0.3.0] - 2026-08-19

### Added

- Public-release documentation, contribution guidance, security policy, issue
  forms, continuous integration, and dependency update automation.
- Multiple named Plane workspace profiles, each retaining its own selected
  project.
- CLI and MCP tools to inspect and switch the active workspace and project.
- Project-aware work-item validation that explains when an item is targeted
  through the wrong project.

### Changed

- Package metadata now declares its long description and direct keyring
  dependency.
- Work-item mutation tools now default to the active project and reject a
  conflicting project selection before changing Plane.

## [0.2.0]

### Added

- Configurable Plane workflow MCP server with guided client setup and report
  export support.
