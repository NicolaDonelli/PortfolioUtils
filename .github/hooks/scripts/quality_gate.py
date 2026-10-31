#!/usr/bin/env python3
"""agentStop hook: do not let the agent finish while the quality gate is red.

When Python files under portfolio_utils/ or tests/ (or pyproject.toml) changed since the
last green run, it runs the same targets as ``make checks`` except licensecheck
(network): check_format, check_lint, mypy, tests. On failure it blocks the stop and
hands the errors back to the agent, at most MAX_ATTEMPTS times in a row.
Set PORTFOLIO_UTILS_QUALITY_GATE=off to disable it temporarily.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

import _hooklib as hl  # noqa: E402

MAX_ATTEMPTS = 3
STATE_FILE = ".make_cache/.copilot_quality_gate.json"


def changed_files(root: Path) -> list[str]:
    """Return changed or untracked files relevant for the gate."""
    code, out = hl.run(["git", "status", "--porcelain", "--untracked-files=all"], root, timeout=10)
    if code != 0:
        return []
    files = [line[3:].split(" -> ")[-1].strip('"') for line in out.splitlines() if len(line) > 3]
    return sorted(
        f for f in files
        if f == "pyproject.toml" or (f.endswith(".py") and f.startswith(("portfolio_utils/", "tests/")))
    )


def fingerprint(root: Path, files: list[str]) -> str:
    """Hash the current content of the relevant files."""
    digest = hashlib.sha256()
    for name in files:
        path = root / name
        digest.update(name.encode())
        digest.update(path.read_bytes() if path.is_file() else b"<deleted>")
    return digest.hexdigest()


def load_state(root: Path) -> dict[str, Any]:
    """Read the persisted gate state."""
    try:
        data = json.loads((root / STATE_FILE).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def save_state(root: Path, state: dict[str, Any]) -> None:
    """Persist the gate state in the git-ignored make cache."""
    path = root / STATE_FILE
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state), encoding="utf-8")


def gate_commands(root: Path) -> list[tuple[str, list[str], int]]:
    """Return the checks to run: make targets when available, tools directly otherwise."""
    if shutil.which("make") and shutil.which("bash"):
        return [
            (t, ["make", "--no-print-directory", t], 600 if t == "tests" else 300)
            for t in ("check_format", "check_lint", "mypy", "tests")
        ]
    python = hl.venv_python(root)
    pydoclint = hl.venv_tool(root, "pydoclint") or "pydoclint"
    return [
        ("check_format", [python, "-m", "ruff", "format", "--check"], 120),
        ("ruff", [python, "-m", "ruff", "check", "--no-fix"], 120),
        ("pydoclint", [pydoclint, "portfolio_utils"], 120),
        ("mypy", [python, "-m", "mypy"], 300),
        ("tests", [python, "-m", "pytest"], 600),
    ]


def run_gate(root: Path) -> list[str]:
    """Run every check and return the failure reports."""
    failures = []
    for label, cmd, timeout in gate_commands(root):
        code, out = hl.run(cmd, root, timeout=timeout)
        if code != 0:
            failures.append(f"### {label} (exit {code})\n{hl.tail(out, lines=50, chars=3000)}")
    return failures


def decide(event: dict[str, Any]) -> dict[str, Any]:
    """Compute the hook output for one agentStop event."""
    if os.environ.get("PORTFOLIO_UTILS_QUALITY_GATE", "on").lower() == "off":
        return {}
    root = hl.repo_root(event)
    files = changed_files(root)
    if not files:
        return {}
    state = load_state(root)
    current = fingerprint(root, files)
    if state.get("green") == current:
        return {}
    attempts = int(state.get("attempts", 0)) if state.get("last") == current or event.get(
        "stop_hook_active", False
    ) else 0
    if attempts >= MAX_ATTEMPTS:
        save_state(root, {"green": state.get("green"), "last": current, "attempts": 0})
        return {}
    failures = run_gate(root)
    if not failures:
        save_state(root, {"green": current, "last": current, "attempts": 0})
        return {}
    save_state(root, {"green": state.get("green"), "last": current, "attempts": attempts + 1})
    reason = (
        "The PortfolioUtils quality gate failed on the files you changed. Fix the root causes "
        "(do not weaken configuration, no blanket noqa/type: ignore), re-run the failing "
        "targets, then finish. Attempt "
        f"{attempts + 1}/{MAX_ATTEMPTS}.\n\n" + "\n\n".join(failures)
    )
    return {"decision": "block", "reason": reason}


def main() -> None:
    """Entry point."""
    try:
        output = decide(hl.read_event())
    except Exception:  # noqa: BLE001 - never trap the agent because of a hook bug
        output = {}
    hl.emit(output)


if __name__ == "__main__":
    main()
