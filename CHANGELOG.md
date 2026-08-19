# Changelog

All notable changes to this project are documented in this file. The project
uses [Semantic Versioning](https://semver.org/).

## [Unreleased]

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
