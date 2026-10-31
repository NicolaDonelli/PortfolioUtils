#!/usr/bin/env python3
"""preToolUse hook for PortfolioUtils.

Denies: access to secrets (.env, keys), dumping investing.com credentials, bypassing the
git hooks, commit messages that commitlint would reject.
Asks for confirmation: edits to quality configuration, files in data/, suppression
comments, direct package installs, force pushes / hard resets, direct calls to
investing.com from the terminal.
Prints exactly one JSON object; never raises (an exception would deny every tool call).
"""

from __future__ import annotations

import re
import shlex
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

import _hooklib as hl  # noqa: E402

SECRET_PATH = re.compile(
    r"(^|/)(\.env(\.(?!example$)[\w.-]+)?|[^/]*\.pem|[^/]*\.key|id_(rsa|ed25519)[^/]*"
    r"|\.netrc|\.pypirc|\.git-credentials)$",
    re.IGNORECASE,
)
SECRET_IN_SHELL = re.compile(
    r"(?:^|[\s'\"=/<>(:])\.env(?:\.(?!example\b)[\w-]+)?(?=$|[\s'\";|&)>])"
)
CREDENTIAL_DUMP = [
    re.compile(r"(\$\{?|\$env:|getenv\(\s*['\"]|environ[^\n]{0,20}['\"])INVESTING_", re.IGNORECASE),
    re.compile(r"\bINVESTING_PASSWORD\s*=", re.IGNORECASE),
    re.compile(r"\bprintenv\b"),
    re.compile(r"(^|[;&|]\s*)(env|set|export\s+-p)\s*($|[;&|])"),
    re.compile(r"\b(Get-ChildItem|gci|dir|ls)\s+env:", re.IGNORECASE),
]
HOOK_BYPASS = [
    re.compile(r"--no-verify\b"),
    re.compile(r"\bgit\s+commit\b[^;&|]*\s-[a-zA-Z]*n[a-zA-Z]*\b"),
    re.compile(r"\bpre-commit\s+uninstall\b"),
    re.compile(r"(^|\s)SKIP=\S+"),
    re.compile(r"\bcore\.hooksPath\b"),
    re.compile(r"\.git/hooks"),
]
ASK_SHELL = [
    (re.compile(r"\bgit\s+push\b.*(\s-f\b|--force)"), "Force push requested."),
    (re.compile(r"\bgit\s+(reset\s+--hard|clean\s+-[a-zA-Z]*f)"), "Destructive git operation."),
    (re.compile(r"\brm\b[^;&|]*(?<![\w.-])(data|\.git|tests)(?![\w-])"), "Deleting project data, tests or git metadata."),
    (re.compile(r"\b(pip|pip3)\s+install\b|\buv\s+(pip\s+install|add)\b"),
     "Direct package install: declare it in pyproject.toml and run make setup_dev (add-dependency skill)."),
    (re.compile(r"\b(curl|wget|Invoke-WebRequest|iwr|python3?\s+-c)\b[^;&|]*investing\.com", re.IGNORECASE),
     "Direct request to investing.com: keep real requests rare and throttled."),
]
COMMIT_HEADER = re.compile(
    r"^(fix|feat|doc|perf|refactor|style|test|chore)(\([\w./ -]+\))?!?: \S.*\.$"
)
PROTECTED_CONFIG = re.compile(
    r"^(pyproject\.toml|Makefile|\.pre-commit-config\.yaml|\.commitlintrc\.yaml|\.mcp\.json"
    r"|\.github/workflows/.+|\.github/hooks/.+|\.devcontainer/.+)$"
)
SUPPRESSION = re.compile(r"#\s*(noqa|type:\s*ignore|pragma:\s*no\s*cover)\b")


def _commit_message(command: str) -> str | None:
    """Extract the first ``-m`` message of a ``git commit`` command, if any."""
    match = re.search(r"\bgit\s+commit\b(.*)", command, re.DOTALL)
    if not match:
        return None
    try:
        tokens = shlex.split(match.group(1).split("&&")[0])
    except ValueError:
        return None
    for i, token in enumerate(tokens):
        if token in {"-m", "--message"} and i + 1 < len(tokens):
            return tokens[i + 1]
        if token.startswith("--message="):
            return token.split("=", 1)[1]
        if token.startswith("-m") and len(token) > 2 and not token.startswith("--"):
            return token[2:]
    return None


def check_shell(command: str) -> tuple[str, str] | None:
    """Return ``(decision, reason)`` for a terminal command, or ``None``."""
    if SECRET_IN_SHELL.search(command):
        return "deny", "Access to .env is not allowed: credentials must never enter the agent context."
    for pattern in CREDENTIAL_DUMP:
        if pattern.search(command):
            return "deny", "Commands that print environment variables or investing.com credentials are not allowed."
    for pattern in HOOK_BYPASS:
        if pattern.search(command):
            return "deny", "Bypassing pre-commit / commit-msg / pre-push hooks is not allowed; fix the failing check instead."
    message = _commit_message(command)
    if message is not None:
        header = message.strip().splitlines()[0] if message.strip() else ""
        if not COMMIT_HEADER.match(header):
            return "deny", (
                "Commit header must be '<type>(<scope>): <description>.' with type in "
                "fix|feat|doc|perf|refactor|style|test|chore, in English, ending with a period. "
                "Use the conventional-commit skill."
            )
    for pattern, reason in ASK_SHELL:
        if pattern.search(command):
            return "ask", reason
    return None


def check_files(name: str, args: Any, root: Path) -> tuple[str, str] | None:
    """Return ``(decision, reason)`` for read/edit tool calls, or ``None``."""
    paths = [hl.relative(p, root) for p in hl.target_paths(args)]
    if any(SECRET_PATH.search(p) for p in paths):
        return "deny", "Reading or writing secret files (.env, keys, credentials) is not allowed."
    if not hl.is_edit(name, args):
        return None
    protected = sorted({p for p in paths if PROTECTED_CONFIG.match(p)})
    if protected:
        return "ask", f"Editing quality/configuration files {protected}: confirm that no gate is being weakened."
    if any(p == "data" or p.startswith("data/") for p in paths):
        return "ask", "Writing into data/ (owner's downloaded prices). Test fixtures belong in tests/resources/."
    if SUPPRESSION.search(hl.new_content(args)):
        return "ask", "The edit adds a noqa / type: ignore / pragma: no cover comment: confirm it is justified."
    return None


def decide(event: dict[str, Any]) -> dict[str, Any]:
    """Compute the hook output for one preToolUse event."""
    name = hl.tool_name(event)
    args = hl.tool_args(event)
    root = hl.repo_root(event)
    command = hl.shell_command(name, args)
    result = check_shell(command) if command else check_files(name, args, root)
    if result is None:
        return {}
    decision, reason = result
    return {"permissionDecision": decision, "permissionDecisionReason": reason}


def main() -> None:
    """Entry point: never raise, always print one JSON object."""
    try:
        output = decide(hl.read_event())
    except Exception:  # noqa: BLE001 - a crash would deny every tool call
        output = {}
    hl.emit(output)


if __name__ == "__main__":
    main()
