"""Turn local git history into proposed Plane work items. Reads git only; never calls Plane."""

from __future__ import annotations

import re
import subprocess
from collections import Counter
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

CONVENTIONAL = re.compile(r"^(?P<type>[a-zA-Z]+)(?:\((?P<scope>[^)]+)\))?!?:\s*(?P<description>.+)$")
TYPE_TO_WORK_ITEM = {"fix": "bug", "feat": "improvement", "perf": "improvement", "refactor": "improvement"}
COMPLEXITY_LINES = (("tiny", 20), ("small", 150), ("medium", 600))
MAX_CRITERIA = 10
RECORD = "\x1e"
FIELD = "\x1f"


class BackfillError(RuntimeError):
    """A git or input problem the user can correct."""


@dataclass
class Commit:
    hash: str
    authored_at: datetime
    author: str
    subject: str
    files: list[str] = field(default_factory=list)
    lines_changed: int = 0

    @property
    def conventional(self) -> re.Match[str] | None:
        return CONVENTIONAL.match(self.subject)

    @property
    def description(self) -> str:
        match = self.conventional
        text = match.group("description") if match else self.subject
        text = text.strip().rstrip(".")
        return text[:1].upper() + text[1:]


def _git(repo: Path, *arguments: str) -> str:
    try:
        result = subprocess.run(["git", "-C", str(repo), *arguments], text=True, capture_output=True, check=False)
    except OSError as error:
        raise BackfillError("git is not available on PATH.") from error
    if result.returncode != 0:
        raise BackfillError(f"git {arguments[0]} failed: {result.stderr.strip() or result.stdout.strip()}")
    return result.stdout


def repository_root(path: str) -> Path:
    candidate = Path(path).expanduser()
    if not candidate.is_dir():
        raise BackfillError(f"Repository path does not exist: {path}")
    return Path(_git(candidate, "rev-parse", "--show-toplevel").strip())


def read_commits(repo: Path, *, since: str, until: str | None = None, author: str | None = None) -> list[Commit]:
    """Read non-merge commits, oldest first, with changed files and line counts."""
    arguments = ["log", "--no-merges", "--reverse", f"--since={since}", "--date=iso-strict", f"--format={RECORD}%H{FIELD}%aI{FIELD}%an{FIELD}%s", "--numstat"]
    if until:
        arguments.append(f"--until={until}")
    if author:
        arguments.append(f"--author={author}")
    commits: list[Commit] = []
    for record in _git(repo, *arguments).split(RECORD)[1:]:
        header, _, numstat = record.partition("\n")
        commit_hash, authored, author_name, subject = header.split(FIELD, 3)
        commit = Commit(commit_hash, datetime.fromisoformat(authored), author_name, subject.strip())
        for line in numstat.splitlines():
            parts = line.split("\t")
            if len(parts) != 3:
                continue
            added, deleted, path = parts
            commit.files.append(path)
            commit.lines_changed += sum(int(value) for value in (added, deleted) if value.isdigit())
        commits.append(commit)
    return commits


def uncommitted_files(repo: Path) -> list[str]:
    return [line[3:].strip() for line in _git(repo, "status", "--porcelain").splitlines() if line.strip()]


def _module_for(commit: Commit, module_map: dict[str, str]) -> str | None:
    votes: Counter[str] = Counter()
    for path in commit.files:
        prefix = max((prefix for prefix in module_map if path.startswith(prefix)), key=len, default=None)
        if prefix is not None:
            votes[module_map[prefix]] += 1
    return votes.most_common(1)[0][0] if votes else None


def _group_key(commit: Commit, module_map: dict[str, str]) -> str:
    mapped = _module_for(commit, module_map)
    if mapped:
        return mapped
    match = commit.conventional
    if match and match.group("scope"):
        return match.group("scope").strip()
    top_levels = Counter(path.split("/", 1)[0] for path in commit.files if "/" in path)
    return top_levels.most_common(1)[0][0] if top_levels else "General"


def _complexity(lines_changed: int) -> str:
    return next((name for name, limit in COMPLEXITY_LINES if lines_changed <= limit), "large")


def _work_item_type(commits: list[Commit]) -> str:
    types = Counter(TYPE_TO_WORK_ITEM.get((commit.conventional.group("type") if commit.conventional else "").casefold(), "task") for commit in commits)
    return types.most_common(1)[0][0]


def _next_business_day(value: date, weekdays: set[int]) -> date:
    while value.weekday() not in weekdays:
        value += timedelta(days=1)
    return value


def _local_date(moment: datetime, timezone_name: str | None) -> date:
    return moment.astimezone(ZoneInfo(timezone_name)).date() if timezone_name else moment.date()


def propose_items(
    commits: list[Commit],
    *,
    weekdays: set[int],
    timezone_name: str | None = None,
    module_map: dict[str, str] | None = None,
    max_gap_days: int = 3,
) -> list[dict[str, Any]]:
    """Group commits by module, scope, or top-level folder, splitting a group when work pauses longer than max_gap_days."""
    if max_gap_days < 0:
        raise BackfillError("max_gap_days must be zero or more.")
    groups: dict[str, list[list[Commit]]] = {}
    for commit in commits:
        runs = groups.setdefault(_group_key(commit, module_map or {}), [])
        if runs and (commit.authored_at - runs[-1][-1].authored_at).days <= max_gap_days:
            runs[-1].append(commit)
        else:
            runs.append([commit])
    items: list[dict[str, Any]] = []
    for module, runs in groups.items():
        for run in runs:
            lead = max(run, key=lambda commit: commit.lines_changed)
            first_day = _local_date(run[0].authored_at, timezone_name)
            last_day = _local_date(run[-1].authored_at, timezone_name)
            start = _next_business_day(first_day, weekdays)
            target = max(start, _next_business_day(last_day, weekdays))
            lines_changed = sum(commit.lines_changed for commit in run)
            files = sorted({path for commit in run for path in commit.files})
            items.append(
                {
                    "module": module,
                    "title": lead.description,
                    "work_item_type": _work_item_type(run),
                    "complexity": _complexity(lines_changed),
                    "start_date": start.isoformat(),
                    "target_date": target.isoformat(),
                    "committed": True,
                    "lines_changed": lines_changed,
                    "files_changed": len(files),
                    "commits": [
                        {"hash": commit.hash, "date": _local_date(commit.authored_at, timezone_name).isoformat(), "subject": commit.subject}
                        for commit in run
                    ],
                    "idempotency_key": f"git:{run[0].hash}",
                }
            )
    items.sort(key=lambda item: (item["start_date"], item["module"]))
    for index, item in enumerate(items, start=1):
        item["id"] = str(index)
    return items


def uncommitted_item(files: list[str], *, today: date, weekdays: set[int], key_suffix: str) -> dict[str, Any]:
    start = _next_business_day(today, weekdays)
    top_levels = Counter(path.split("/", 1)[0] for path in files if "/" in path)
    return {
        "module": top_levels.most_common(1)[0][0] if top_levels else "General",
        "title": "Finish uncommitted work in progress",
        "work_item_type": "task",
        "complexity": "small",
        "start_date": start.isoformat(),
        "target_date": start.isoformat(),
        "committed": False,
        "lines_changed": None,
        "files_changed": len(files),
        "files": files[:50],
        "commits": [],
        "idempotency_key": f"git-wip:{key_suffix}",
    }


def acceptance_criteria(item: dict[str, Any]) -> list[str]:
    if not item["commits"]:
        return [f"Uncommitted changes in {item['files_changed']} files are finished and committed"]
    subjects = [CONVENTIONAL.sub(r"\g<description>", commit["subject"]).strip() for commit in item["commits"]]
    unique = list(dict.fromkeys(subject[:1].upper() + subject[1:] for subject in subjects if subject))
    if len(unique) > MAX_CRITERIA:
        unique = unique[: MAX_CRITERIA - 1] + [f"{len(unique) - MAX_CRITERIA + 1} more changes listed in the commits"]
    return unique


def completion_record(item: dict[str, Any]) -> dict[str, Any]:
    commits = item["commits"]
    first, last = commits[0], commits[-1]
    span = first["date"] if first["date"] == last["date"] else f"{first['date']} to {last['date']}"
    return {
        "summary": f"Reconstructed from git history: {len(commits)} commit{'s' if len(commits) != 1 else ''} from {span}.",
        "verification": [
            "Evidence is the git commits listed below. No tests were run as part of this backfill.",
        ],
        "implementation_notes": [f"{commit['hash'][:10]} {commit['subject']}" for commit in commits[:30]],
    }
