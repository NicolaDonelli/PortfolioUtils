"""Shared helpers for the PortfolioUtils Copilot hooks (standard library only)."""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
from collections.abc import Iterator
from pathlib import Path
from typing import Any

SHELL_TOOLS = {
    "bash", "powershell", "shell", "execute", "terminal",
    "run_in_terminal", "runinterminal", "run_command",
}
EDIT_TOOLS = {
    "create", "edit", "write", "insert", "str_replace_editor", "apply_patch",
    "multi_edit", "create_file", "edit_file", "editfiles", "replace_string_in_file",
    "multi_replace_string_in_file", "insert_edit_into_file",
}
READ_TOOLS = {"view", "read", "read_file", "readfile", "grep", "glob", "rg", "search"}

_PATH_KEY = re.compile(r"(path|file|filename|filepath|target|uri)s?$", re.IGNORECASE)
_CONTENT_KEYS = {
    "new_str", "new_string", "newstring", "content", "file_text", "text", "patch",
    "input", "code", "newtext", "insert_text",
}
_PATCH_FILE = re.compile(r"^\*\*\* (?:Add|Update|Delete) File: (.+)$", re.MULTILINE)


def read_event() -> dict[str, Any]:
    """Read the hook event from stdin; return an empty dict on malformed input."""
    try:
        raw = sys.stdin.read()
        data = json.loads(raw) if raw.strip() else {}
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def emit(payload: dict[str, Any]) -> None:
    """Write exactly one JSON object on stdout."""
    sys.stdout.write(json.dumps(payload))
    sys.stdout.flush()


def tool_name(event: dict[str, Any]) -> str:
    """Return the tool name for both camelCase and VS Code compatible payloads."""
    name = event.get("toolName") or event.get("tool_name") or ""
    return str(name)


def tool_args(event: dict[str, Any]) -> Any:
    """Return the tool arguments, decoding them when they arrive as a JSON string."""
    args = event.get("toolArgs", event.get("tool_input", {}))
    if isinstance(args, str):
        try:
            return json.loads(args)
        except ValueError:
            is_shell = tool_name(event).lower() in SHELL_TOOLS
            return {"command": args} if is_shell else {"patch": args}
    return args


def walk_strings(obj: Any, key: str = "") -> Iterator[tuple[str, str]]:
    """Yield ``(key, value)`` for every string nested in ``obj``."""
    if isinstance(obj, str):
        yield key, obj
    elif isinstance(obj, dict):
        for k, v in obj.items():
            yield from walk_strings(v, str(k))
    elif isinstance(obj, list):
        for item in obj:
            yield from walk_strings(item, key)


def shell_command(name: str, args: Any) -> str:
    """Return the shell command of a terminal tool call, or an empty string."""
    if isinstance(args, dict):
        for key in ("command", "cmd", "script"):
            value = args.get(key)
            if isinstance(value, str):
                return value
    if name.lower() in SHELL_TOOLS and isinstance(args, str):
        return args
    return ""


def target_paths(args: Any) -> list[str]:
    """Collect file paths referenced by a tool call (including apply_patch bodies)."""
    paths: list[str] = []
    for key, value in walk_strings(args):
        if _PATH_KEY.search(key) and value and "\n" not in value:
            paths.append(value)
        if key.lower() in _CONTENT_KEYS or key == "":
            paths.extend(m.strip() for m in _PATCH_FILE.findall(value))
    return paths


def new_content(args: Any) -> str:
    """Concatenate the text a tool call is about to write."""
    chunks = [v for k, v in walk_strings(args) if k.lower() in _CONTENT_KEYS]
    return "\n".join(chunks)


def is_edit(name: str, args: Any) -> bool:
    """Tell whether the tool call writes files."""
    if name.lower() in EDIT_TOOLS:
        return True
    return isinstance(args, dict) and any(
        k.lower() in {"new_str", "new_string", "file_text", "patch"} for k in args
    )


def repo_root(event: dict[str, Any]) -> Path:
    """Return the repository root (git top level, else the event cwd)."""
    cwd = Path(str(event.get("cwd") or os.getcwd()))
    try:
        out = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"], cwd=cwd, capture_output=True,
            text=True, timeout=5, check=True,
        )
        return Path(out.stdout.strip())
    except (OSError, subprocess.SubprocessError):
        return cwd


def relative(path: str, root: Path) -> str:
    """Return ``path`` relative to ``root`` with forward slashes when possible."""
    p = Path(path)
    if p.is_absolute():
        try:
            p = p.resolve().relative_to(root.resolve())
        except ValueError:
            return p.as_posix()
    text = p.as_posix()
    while text.startswith("./"):
        text = text[2:]
    return text


def venv_python(root: Path) -> str:
    """Return the project venv interpreter, falling back to the current one."""
    for candidate in (root / ".venv/bin/python", root / ".venv/Scripts/python.exe"):
        if candidate.exists():
            return str(candidate)
    return sys.executable


def venv_tool(root: Path, tool: str) -> str | None:
    """Return the path of a console script installed in the venv, if any."""
    for candidate in (root / ".venv/bin" / tool, root / ".venv/Scripts" / f"{tool}.exe"):
        if candidate.exists():
            return str(candidate)
    return shutil.which(tool)


def run(cmd: list[str], root: Path, timeout: int) -> tuple[int, str]:
    """Run a command and return ``(exit code, combined output)``."""
    try:
        proc = subprocess.run(
            cmd, cwd=root, capture_output=True, text=True, timeout=timeout, check=False,
        )
    except subprocess.TimeoutExpired:
        return 124, f"Timed out after {timeout}s: {' '.join(cmd)}"
    except OSError as exc:
        return 127, f"Cannot run {' '.join(cmd)}: {exc}"
    return proc.returncode, (proc.stdout + proc.stderr).strip()


def tail(text: str, lines: int = 60, chars: int = 6000) -> str:
    """Keep the end of a long output."""
    kept = "\n".join(text.splitlines()[-lines:])
    return kept[-chars:]
