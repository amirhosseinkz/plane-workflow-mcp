# Release and distribution

## Practical release testing

Use a disposable Plane workspace and project, generic test data, and a
least-privilege account. Do not put credentials or real organization IDs in
fixtures, command output, screenshots, or reports.

1. Run `plane-workflow setup --client <client> --dry-run`, complete setup, and
   verify `plane-workflow status` without exposing the API key.
2. Exercise the v0.3.x context flow: configure two workspace profiles, switch
   with `workspace activate`, select a project with `project activate`, and
   confirm each workspace retains its selected project. Repeat through the MCP
   workspace/project list and activation tools.
3. In a disposable second project, verify a mutation with a conflicting
   `project_id` is rejected and an item from the wrong project is not changed.
4. Run `diagnose_plane_connection`, `get_project_workflow_context`, and
   `get_workflow_options`; confirm capabilities and IDs reflect the selected
   project. Preview profile validation and saving before persisting an override.
5. In `advisory` mode, preview creation with partial planning data. In `strict`
   mode, confirm incomplete planning is rejected, then preview all four
   complexity values and verify configured defaults, estimate-point IDs, and
   business-day dates.
6. In the disposable project, preview and apply creation, start, and completion.
   Confirm start records the real start date; completion requires a factual
   summary plus real verification, writes its comment before Done, and creates
   a worklog only when a known `actual_minutes` value is supplied. Retry any
   `completion_pending` result and confirm records are not duplicated.
7. Confirm generic updates cannot bypass completion or cancellation. Retry a
   cancellation and confirm its factual comment is not duplicated.
8. Run filtered work-item queries, inspect the project briefing, and preview and
   apply a same-project blocker relation after reviewing its direction.
9. Run a read-only audit and export a sanitized DOCX or PDF report.
10. Run the automated checks shown above and inspect the release diff to ensure
   it contains no credentials, private IDs, generated reports, or unrelated
   artifacts.

## Publishing checklist

Before making a release, maintainers should:

1. Confirm the MIT license remains appropriate for the intended distribution.
2. Confirm GitHub repository metadata, marketplace name, and package project
   URLs match the release destination.
3. Enable GitHub private vulnerability reporting and configure repository
   discussions or support channels.
4. Verify that no organization-specific endpoints, project identifiers,
   reports, credentials, local profiles, or generated artifacts are present in
   the files or Git history being published.
5. Create a tagged release only after CI is green.

## Build and verify the installable artifacts

From the repository root:

```bash
uv build --project plugins/plane-workflow --out-dir dist
python scripts/smoke_distribution.py dist
```

Use an empty output directory so old versions are not mixed with the release.
The smoke check installs each wheel and source archive in a temporary environment
outside the checkout, checks bundled profiles, previews setup, and discovers tools
through an actual stdio MCP connection. It does not connect to Plane or prove
compatibility with a GUI client. CI runs this check on every build.

## Distribution status

v0.6.0 is available as a wheel and source archive on GitHub Releases. The README
uses the exact wheel URL and can be used without a clone. PyPI returned no project
for `plane-workflow-mcp` when checked on September 27, 2026; do not advertise a
registry installation until a release has actually been uploaded and verified.

For a future PyPI release, the maintainer must have access to the package name and
configure registry credentials or a trusted publisher. Use a new version for code
changes; never silently replace a published release artifact with an unreleased build.
Update the version and lockfile, run all checks, build the artifacts, and publish
those exact files using `uv publish`. Keep credentials out of commands and source.
Only then verify installation from a fresh environment and update the README's
install command. Package upload and registry account setup are not part of the
local documentation update.

The `Publish to PyPI` workflow (`.github/workflows/publish.yml`) builds, smoke-tests,
and uploads the artifacts with PyPI trusted publishing when a GitHub release is
published, or when run manually. It needs a one-time trusted publisher on PyPI for
project `plane-workflow-mcp`, owner `amirhosseinkz`, repository
`plane-workflow-mcp`, workflow `publish.yml`, environment `pypi`. No API token is
stored in the repository.

See [uv's publishing guide](https://docs.astral.sh/uv/guides/package/) for the
registry authentication and upload procedure.
