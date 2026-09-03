# Changelog

All notable changes to this project are documented in this file. The project
uses [Semantic Versioning](https://semver.org/).

## [Unreleased]

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
