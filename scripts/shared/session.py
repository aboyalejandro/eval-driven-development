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
    accidental `sim-main` traces. Pass `allow_main=True` to override.
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
            f"refusing to run on `{branch}` — feature branch required so "
            f"traces tag as `sim-<branch>` instead of `sim-{branch}`. "
            "Pass --allow-main to override."
        )
    return branch


def session_mode() -> str:
    """Stripped string value of session.json `mode` key, or empty string."""
    return str(load_session().get("mode", "")).strip()


def session_tags() -> list[str]:
    """Tags derived from `.edd/session.json` — propagated to dataset / experiment / optimization."""
    s = load_session()
    tags: list[str] = []
    if t := s.get("topic"):
        tags.append(f"topic-{t}")
    if (m := s.get("mode")) is not None:
        tags.append(f"mode-{m}")
    if (a := s.get("aggression")) is not None:
        tags.append(f"aggression-{a}")
    return tags


def branch_tag_warning(branch_tag: str) -> str | None:
    """Return warning string if `branch_tag` references main/master, else None."""
    for guarded in GUARDED_BRANCHES:
        if branch_tag.endswith(f"-{guarded}") or branch_tag == f"sim-{guarded}":
            return (
                f"branch-tag `{branch_tag}` references the `{guarded}` branch — "
                "this usually means you forgot to check out a feature branch before "
                "`edd run`. Continuing, but the experiment will mix with anything "
                f"else tagged `sim-{guarded}`."
            )
    return None
