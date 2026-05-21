"""Session state + branch guard helpers shared across `edd*` CLIs."""

import json
import subprocess
from pathlib import Path

SESSION_PATH = Path(".edd/session.json")
GUARDED_BRANCHES = {"main", "master"}


def load_session() -> dict:
    """Return parsed `.edd/session.json` or empty dict if file missing."""
    if not SESSION_PATH.exists():
        return {}
    return json.loads(SESSION_PATH.read_text())


def git_branch() -> str | None:
    """Current git branch name, or None on detached HEAD."""
    r = subprocess.run(
        ["git", "branch", "--show-current"],
        capture_output=True,
        text=True,
        timeout=5,
    )
    return r.stdout.strip() or None


def assert_active_branch(allow_main: bool = False) -> str:
    """Refuse to proceed unless on a non-default branch. Returns the branch name.

    Hard-fails when on `main`/`master` or detached HEAD — prevents
    accidental `main`-tagged traces. Pass `allow_main=True` to override.
    """
    branch = git_branch()
    if allow_main:
        return branch or "detached"
    if not branch:
        raise SystemExit(
            "refusing to run on detached HEAD — checkout a feature branch "
            "or pass --allow-main if this is intentional"
        )
    if branch in GUARDED_BRANCHES:
        raise SystemExit(
            f"refusing to run on `{branch}` — topic branch required so "
            f"traces tag as `<topic>` not `{branch}`. "
            "Pass --allow-main to override."
        )
    return branch


def session_tags() -> list[str]:
    """Extra session tags beyond the branch tag.

    Branch name = topic = tag — branch already encodes identity.
    Returns empty; preserved for callers that pass --tag extras.
    """
    return []


def branch_tag_warning(branch_tag: str) -> str | None:
    """Return warning string if `branch_tag` is main/master, else None."""
    if branch_tag in GUARDED_BRANCHES:
        return (
            f"branch-tag `{branch_tag}` is `{branch_tag}` — "
            "this usually means you forgot to check out a topic branch before "
            "`edd run`. Continuing, but the experiment will mix with all other "
            f"`{branch_tag}`-tagged traces."
        )
    return None
