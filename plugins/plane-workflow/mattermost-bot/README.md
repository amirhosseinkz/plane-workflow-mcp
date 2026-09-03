# Plane Workflow Mattermost Bot

This optional service lets approved Mattermost users manage Plane work items
through direct messages. It is a local-project companion, not a component
installed by the Codex plugin: clone this repository and run it from
`plugins/plane-workflow/mattermost-bot`. Its locked environment installs the
parent `plane-workflow-mcp` project as an editable local dependency, so do not
copy the bot directory by itself.

## Requirements

- Python 3.11 or newer and [uv](https://docs.astral.sh/uv/)
- A Mattermost bot account and a dedicated Plane service-account API key
- A locally authenticated Codex CLI account
- Your own Mattermost URL, Plane URL, workspace, project, and trusted-user
  allowlist

## Configure and run

After cloning the repository, change into
`plugins/plane-workflow/mattermost-bot`, install the locked environment, and
run the local setup helper:

```bash
uv sync --locked
uv run python configure.py
```

The helper collects the deployment-specific URLs, workspace and project
selection, credentials, and Mattermost allowlist. It writes the values to a
local `.env` file. You may instead copy `.env.example` to `.env` and fill it
in yourself. Never commit either a real `.env` file or the `data/` directory.

Verify connectivity before processing messages:

```bash
uv run python main.py --check
```

Then start the bot in the foreground:

```bash
uv run python main.py
```

The bot listens only to direct messages when `MATTERMOST_DM_ONLY=true`. Every
Plane-changing action is prepared as a draft; users must reply with
`confirm <draft-id>` to apply it or `cancel <draft-id>` to discard it.

The v0.5 tool catalog supports filtered work-item lists, project attention
briefings, dependency inspection and creation, and factual cancellation in
addition to planning, start, completion, audit, and module operations. Relation
creation and cancellation follow the same draft-and-confirm flow as other
writes.

## Background service

`launch_agent.py` is an optional macOS convenience. It installs a local
launch-agent service on macOS only:

```bash
uv run python launch_agent.py install
```

Remove it later with:

```bash
uv run python launch_agent.py uninstall
```

On Linux or Windows, use the foreground command with your platform's process
supervisor. This repository does not bundle a service definition for those
platforms.

## Security

- Give the bot a dedicated Plane service-account key with the minimum required
  permissions.
- Allowlist only trusted Mattermost usernames.
- Keep `.env` and `data/` on the machine that runs the bot.
- Use the local Codex CLI only for interpreting direct messages; it should not
  receive credentials or private configuration values in prompts.
- The `--check` command verifies the bot account, allowlist, local Codex
  sign-in, and Plane connection without changing a work item.
