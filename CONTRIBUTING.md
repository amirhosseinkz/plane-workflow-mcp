# Contributing

Thank you for improving Plane Workflow MCP. By contributing, you agree to
follow the [Code of Conduct](CODE_OF_CONDUCT.md).

## Before you start

- Search existing issues and pull requests before opening a new one.
- Discuss significant behavior or API changes in an issue before investing in a
  large implementation.
- Do not include credentials, private endpoints, customer data, organization
  names, project identifiers, generated reports, or copied production logs in
  issues, pull requests, tests, or documentation.
- Use neutral fixture values such as `example.test`, `example-workspace`, and
  `EXAMPLE-123`.

## Development setup

Use Python 3.11 or newer and [uv](https://docs.astral.sh/uv/). The core MCP
server and optional Mattermost bot have separate environments.

```bash
cd plugins/plane-workflow
uv sync --locked
uv run python -m unittest discover -s tests -v
uv lock --check
uv build
```

```bash
cd plugins/plane-workflow/mattermost-bot
uv sync --locked
uv run python -m unittest discover -s tests -v
uv lock --check
```

When changing a dependency, regenerate the applicable `uv.lock` with `uv lock`
and include the resulting lockfile update in the same pull request.

## Pull requests

Keep pull requests focused and explain the user-visible behavior, testing, and
any configuration or migration impact. Before requesting review:

1. Run the relevant tests and lockfile checks above.
2. Build the core package when changing package metadata or distributable
   files.
3. Update documentation, tests, and [CHANGELOG.md](CHANGELOG.md) when they
   describe the changed behavior.
4. Confirm that generated files, local configuration, credentials, and
   organization-specific information are not included.

## Reporting bugs and requesting features

Use the repository issue forms for reproducible bugs and focused feature
requests. Security vulnerabilities must follow [SECURITY.md](SECURITY.md), not
the public issue tracker.
