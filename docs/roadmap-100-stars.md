# Roadmap: from 5 to 100 GitHub stars

Status: **draft for maintainer review.** Nothing in this plan has been posted,
published, or pushed. Dates are targets, not commitments.

## Where we are (baseline, 2026-10-28)

| Signal | Value | Source |
| --- | --- | --- |
| Stars / forks | 5 / 0 | GitHub API |
| Repository views, last 14 days | 1 view, 1 unique visitor | GitHub traffic API |
| Referring sites | none recorded | GitHub traffic API |
| Release wheel downloads (all versions) | 6 | GitHub release assets |
| Official Plane MCP server | 351 stars | `makeplane/plane-mcp-server` |
| Plane itself | ~61.6k stars | `makeplane/plane` |

**Diagnosis: the project did not fail, it was not seen.** One unique visitor in two
weeks means the social posts produced no clicks. There is no evidence of people
arriving and leaving; there is evidence of nobody arriving. So the first job is
discovery (listings, the right communities, a reason to click), and the second is
a first-run experience that turns a visitor into a star within two minutes.

Two things also work against the current pitch:

1. **"Workflow rules for Plane" is a feature, not a reason to click.** Every Plane MCP
   server "creates work items". The README leads with a bug-to-task walkthrough that
   the official server, used with any capable agent, can roughly do too.
2. **The README talks to Codex users first.** The largest MCP client audience today is
   Claude Code / Claude Desktop / Cursor, and the guided setup does not support
   Claude Code at all.

## Positioning

**Who it is for:** developers and small teams who run **Plane (especially
self-hosted)** and do most of their work through a coding agent (Claude Code, Codex,
Cursor, OpenCode, Zed). They are behind on updating Plane because the work happens
in the terminal and in git, not in the tracker.

**The one job it does better than anything else:** *keep Plane truthful about the
work you actually did.* The agent turns real evidence (commits, diffs, test runs)
into properly planned, started, and completed Plane items, with a preview first and
a completion record that cites the evidence.

**One-liner:** *Your git history already knows what you did. Let your agent put it in Plane.*

**Why not the official server:** the official server is a broad, thin API wrapper
(projects, work items, cycles, modules; hosted OAuth). It is the right choice for
"read or edit anything in Plane". This project is the right choice for "make Plane
reflect reality with no manual typing": git-aware backfill, an enforced
plan → start → complete lifecycle, business-day scheduling, dry-run previews,
duplicate checks, and wrong-project guards. Say this in one sentence in the README
and keep the long comparison table in a doc page.

Competitors checked: the official server ([makeplane/plane-mcp-server](https://github.com/makeplane/plane-mcp-server)),
kelvin6365/plane-mcp-server (Node, basic issue CRUD), ItsJennyFiggy/plane-mcp (Go,
tool-scoping profiles). Adjacent: Jira/Linear MCP servers that read commit links or
update status from branch names. **None found that backfills a tracker from git
history.** That gap is the hero feature.

## Improvement list, verified against the code

Effort: S (< half a day), M (1–2 days), L (3+ days). Impact is on adoption, not on
code quality.

| # | Item | Verified in code | Keep? | Effort | Adoption impact |
| --- | --- | --- | --- | --- | --- |
| 1 | **Claude Code setup adapter** (`setup --client claude-code`, using `claude mcp add --scope user`) | `cli.py:19` `CLIENTS = ("codex", "opencode", "zed")` | Keep, **P0** | S | High. Claude Code is the biggest MCP audience; today they must hand-register. Add Cursor and Claude Desktop JSON adapters in the same pass (M). |
| 2 | **429 retry with backoff** (honor `Retry-After`, jittered exponential, retry idempotent GETs; never blind-retry POST) | `server.py:361` single `session.request`, no retry | Keep, **P0** | S | High. Real use hit 429 constantly; a first-run failure kills the star. |
| 3 | **Do not mask errors as "not found"**: only map 404 to the wrong-project message; pass 429/5xx/timeouts through | `server.py:665-671` wraps every `PlaneWorkflowError` | Keep, **P0** | S | Medium. Misleading errors make the agent take wrong actions (activate other projects, retry). |
| 4 | **Cheap duplicate check**: search by title (Plane `search`/`name` filter, or the first N recently updated items) instead of listing every item | `server.py:2707` `api.work_items(project_id)` pages through the whole project | Keep, **P0** | M | High for real projects (200+ items): fixes slowness and is the main 429 source. |
| 5 | **Idempotent create**: deterministic `external_id`/`external_source` (hash of project + title + client key); before retrying a failed/timed-out POST, look the item up by it | completion and cancellation already use `external_id` (`server.py:1489`, `1547`); create does not | Keep, **P0** | M | High for batch/backfill. Without it, the hero feature creates duplicates. |
| 6 | **Strict mode without estimates**: detect "project has no estimate points" and return a clear error naming the setting, or fall back (skip estimate, warn) when the profile allows it | `server.py:1397-1400` passes an int through when the catalog is unavailable, then Plane returns a bare 400 | Keep, P1 | S | Medium. Strict mode is a selling point; a bare 400 makes it look broken. |
| 7 | **Safe per-call project override**: allow `project_id` different from the active project when the call also passes `confirm_project_identifier` (e.g. `"WEB"`) that matches; keep the active-project default | `server.py:651` rejects any non-active `project_id` | Keep, P1 | S | Medium. Needed for multi-project backfill; keeps the safety story. |
| 8 | **Document "completed_at is always now"** (Plane sets it on transition) and how backfilled items show their real dates (start/target dates + commit-cited comment) | not documented | Keep, P2 | S | Low alone; required for the hero feature to be honest. |
| 9 | **Request timeout 30s**: keep 30s for GETs; on POST timeout, do the idempotency lookup from #5 instead of reporting failure | `server.py:361` | Merge into #5 | — | — |
| 10 | **PyPI release + `uvx plane-workflow-mcp`** one-command run (README says "no PyPI release yet") | README quick start uses a long wheel URL | **Add**, P0 | S | High. Every registry and awesome list expects `uvx name` / `pip install name`. The official MCP Registry needs a package registry entry. |
| 11 | **Claude Code plugin marketplace entry** (like the existing Codex one, with the skill) | only `.agents/` Codex marketplace | **Add**, P1 | S | Medium. One more install path and listing surface. |
| 12 | **README rewrite** (see below) | README leads with features and a defensive comparison | **Add**, P0 | M | High. Converts the visitors that listings bring. |
| 13 | **Real demo GIF** (30s, top of README) | `docs/demo.md` says no recording exists | **Add**, P0 | M | High. The single biggest star driver for dev tools. |
| 14 | **Repo hygiene for first impressions**: description mentions "Codex setup"; add topics `claude-code`, `cursor`, `self-hosted`, `git`; remove committed `dist/` and `__pycache__` if tracked; move the Mattermost bot link lower | `gh repo view` | **Add**, P1 | S | Low–medium. |

Dropped/deferred: nothing dropped. Background code-to-task sync, a hosted HTTP
transport, and OAuth are deferred: the official server already covers hosted use,
and they do not support the positioning.

## The hero feature: backfill Plane from git history

Validated in a real session: a full day of back-filling company Plane projects from
git across several repositories. Today an agent can do it only by hand-orchestrating
dozens of tool calls, hitting 429s and duplicates on the way. Make it one flow.

**User story:** "Read this repo's history since 1 Sep, group it into tasks under
modules, show me the plan, then put it in Plane as completed work."

**Design (preview-first, two tools plus a CLI):**

1. `plan_git_backfill(repo_path, since, until=None, author=None, include_uncommitted=False, project_id=None)`
   *read-only*: runs `git log` locally (no network), groups commits into candidate
   work items (by conventional-commit scope, path prefix → module mapping from the
   profile, or time proximity), proposes titles, modules, complexity, and
   **human-paced start/target dates that skip the profile's non-business days**,
   and marks items that already exist (by `external_id` = repo + first commit hash).
   Returns a plan ID (reuse the existing standardization-plan storage pattern).
2. The agent (and the user) edit the plan in conversation: merge, split, rename,
   drop.
3. `apply_git_backfill(plan_id, dry_run=True)`: creates → starts → completes each
   item with idempotent `external_id`s, rate-limited, resumable after a failure, and
   writes a completion comment listing the cited commit hashes and subjects.
   Uncommitted work becomes an *started* item instead of a completed one.
4. CLI mirror for people without an agent: `plane-workflow backfill --since 2026-09-01 --dry-run`.

**Honesty rules (fit the existing completion guidance):** never invent verification;
the completion comment states that it was reconstructed from git; dates are planned
from commit timestamps, and `completed_at` is the backfill time (documented, #8).

**Depends on:** #2, #4, #5, #7. That is why the robustness fixes come first.

**Effort:** L (about 3–5 days with tests using a fixture git repo).

## README rewrite plan

Target: a visitor understands the value in 5 seconds and has a first result in
2 minutes.

1. **Title + one-liner:** "Plane Workflow MCP — your git history already knows what
   you did. Let your agent put it in Plane."
2. **Demo GIF** directly below (30s: `git log` → preview table → items appear in
   Plane as Done with commit hashes).
3. **Three bullets** of outcomes: backfill from git; plan → start → complete with
   evidence; project briefing (overdue/stale/unassigned).
4. **Install in one block per client**, Claude Code first:
   `uvx plane-workflow-mcp setup --client claude-code`, then Codex, Cursor, OpenCode, Zed.
5. **First prompt to paste** (read-only briefing, then a backfill dry run).
6. **"vs the official Plane MCP"** in two sentences; link the full table in `docs/`.
7. Badges: PyPI version, CI, license, MCP Registry.
8. Everything else (Mattermost bot, profiles, strict mode, releasing) moves to `docs/`.

Keep the project's honesty standard: the GIF is a real recording on a disposable
project, not a mock-up.

## Product work, in order

| Phase | Work | Effort |
| --- | --- | --- |
| 1. Robustness + setup (v0.6.0) | #1 Claude Code (+Cursor, Claude Desktop), #2 429 backoff, #3 error mapping, #4 cheap duplicate check, #5 idempotent create, #6 estimate error, #7 project override, #10 PyPI | ~4–5 days |
| 2. README + demo (v0.6.0 release) | #12 README rewrite, #14 hygiene, #11 Claude Code plugin entry | ~2 days |
| 3. Hero (v0.7.0) | git backfill tools + CLI, #8 docs, real GIF of backfill (#13) | ~4–5 days |

Phase 2 can ship with a GIF of the briefing + lifecycle; re-record it for the hero
in phase 3. **Do not start distribution before phase 2 is out** — sending people
to the current README wastes the one chance each channel gives.

## Distribution plan

Order matters: listings first (permanent, compounding traffic), then communities
that own the audience, then broad launches once the hero exists.

| Step | When | Where | Message / action |
| --- | --- | --- | --- |
| 1 | after v0.6.0 | **Official MCP Registry** (`server.json`, needs PyPI) | — |
| 2 | after v0.6.0 | PR to **punkpeye/awesome-mcp-servers** and **appcypher/awesome-mcp-servers** (Project management section) | "plane-workflow-mcp — Plane work items with planning rules, lifecycle, and project briefings for self-hosted Plane." |
| 3 | after v0.6.0 | **Glama, Smithery, mcp.so, PulseMCP, MCP Market** listings | Same one-liner + GIF |
| 4 | after v0.6.0 | **Plane community**: Discord `#showcase`/community channel, `makeplane/plane` GitHub Discussions (Show and tell) | "If you run Plane with Claude Code or Codex: an MCP server that plans, starts and completes items with your team's rules. Works with self-hosted. Feedback wanted." |
| 5 | after v0.6.0 | Ask Plane to list it on their integrations/community page; open a friendly issue on the official MCP repo pointing to it as a workflow layer | — |
| 6 | after v0.7.0 | **r/selfhosted** (Plane is a common self-hosted Jira alternative there) | "I back-filled 3 months of work into my self-hosted Plane from git history with one prompt" + GIF + honest limits |
| 7 | after v0.7.0 | **Show HN** (Tue–Thu, ~8–10am US Eastern) | "Show HN: Backfill your issue tracker from git history with an AI agent (Plane, MCP)" |
| 8 | after v0.7.0 | r/ClaudeAI, r/mcp, r/LocalLLaMA (only if it fits rules), dev.to / Medium write-up, X/LinkedIn with the GIF | Post the write-up "Your git history already knows what you did" |
| 9 | ongoing | Answer "Plane + AI" questions on Discord/Reddit/GitHub when relevant; reply to every issue within 24h | — |

Rules: one post per community, read its self-promotion rules first, disclose
authorship, no vote rings. Each post needs maintainer approval before sending.

## Milestones

Measured with GitHub traffic (views/uniques/referrers, 14-day window), stars,
PyPI downloads (pypistats), and issues/discussions from people other than the
maintainer. Capture the numbers on the day before each distribution step.

| Milestone | Target date | Views (14d uniques) | Stars | Installs | Evidence of use |
| --- | --- | --- | --- | --- | --- |
| M0 baseline | 2026-10-28 | 1 | 5 | 6 wheel downloads | — |
| M1 v0.6.0 + listings | ~2026-11-15 | 100 | 20 | 50 PyPI/month | 1 external issue or discussion |
| M2 Plane community | ~2026-11-30 | 300 | 40 | 150 PyPI/month | 3 external users report a first result |
| M3 v0.7.0 hero + r/selfhosted | ~2026-12-20 | 1,000 | 70 | 300 PyPI/month | 1 external contributor PR |
| M4 Show HN + write-up | ~2027-01-15 | 2,500+ | **100** | 500 PyPI/month | listed in ≥ 3 directories with backlinks |

If M1 misses its view target, the problem is listings/messaging; if views come but
stars do not (conversion < 3%), the problem is the README and first run — fix those
before posting anywhere else.

## Next concrete step (pending approval)

Phase 1 on a new branch: Claude Code setup adapter, 429 backoff, honest error
mapping, cheap duplicate check, idempotent create, clear strict-estimate error,
safe project override, and a PyPI-ready package — each with tests in
`plugins/plane-workflow/tests/`, no calls to any live Plane instance.
