#!/usr/bin/env python3
"""postToolUse hook: format and lint the Python files the agent has just written.

Runs ``ruff format`` and ``ruff check --fix`` on edited files under ``portfolio_utils/``
and ``tests/``, then reports remaining ruff and pydoclint findings to the agent as
additional context so they are fixed immediately instead of at the end of the turn.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

import _hooklib as hl  # noqa: E402

TRACKED_DIRS = ("portfolio_utils/", "tests/")


def edited_python_files(event: dict[str, Any], root: Path) -> list[str]:
    """Return existing .py files under the tracked folders touched by the tool call."""
    name = hl.tool_name(event)
    args = hl.tool_args(event)
    if not hl.is_edit(name, args):
        return []
    files = {hl.relative(p, root) for p in hl.target_paths(args)}
    return sorted(
        f for f in files
        if f.endswith(".py") and f.startswith(TRACKED_DIRS) and (root / f).is_file()
    )


def lint(files: list[str], root: Path) -> str:
    """Auto-fix the files and return the remaining findings (empty if clean)."""
    python = hl.venv_python(root)
    if hl.run([python, "-m", "ruff", "--version"], root, timeout=10)[0] != 0:
        return ""  # dev environment not installed yet: nothing to do
    hl.run([python, "-m", "ruff", "format", *files], root, timeout=30)
    hl.run([python, "-m", "ruff", "check", "--fix", "--quiet", *files], root, timeout=30)
    reports: list[str] = []
    code, out = hl.run(
        [python, "-m", "ruff", "check", "--no-fix", "--output-format", "concise", *files],
        root, timeout=30,
    )
    if code != 0:
        reports.append("ruff:\n" + hl.tail(out, lines=40))
    src_files = [f for f in files if f.startswith("portfolio_utils/")]
    pydoclint = hl.venv_tool(root, "pydoclint")
    if src_files and pydoclint:
        code, out = hl.run([pydoclint, *src_files], root, timeout=30)
        if code != 0:
            reports.append("pydoclint:\n" + hl.tail(out, lines=40))
    return "\n\n".join(reports)


def main() -> None:
    """Entry point."""
    try:
        event = hl.read_event()
        root = hl.repo_root(event)
        files = edited_python_files(event, root)
        report = lint(files, root) if files else ""
        if report:
            hl.emit({
                "additionalContext": (
                    f"Files were auto-formatted with ruff. Remaining findings in {files} "
                    f"must be fixed before finishing:\n{report}"
                )
            })
        else:
            hl.emit({})
    except Exception:  # noqa: BLE001 - linting is advisory, never break the session
        hl.emit({})


if __name__ == "__main__":
    main()
