"""Gitignore-style ignore rules used to prune the file index walk.

Rules are evaluated in order; the last matching rule wins, mirroring
gitignore semantics (so a later `!pattern` can re-include something an
earlier broader rule excluded).
"""

from __future__ import annotations

import fnmatch
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

DEFAULT_IGNORE_NAMES = (
    ".git",
    ".hg",
    ".svn",
    "node_modules",
    "__pycache__",
    ".venv",
    "venv",
    ".cache",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    "build",
    "dist",
    "target",
    ".tox",
    ".idea",
    ".vscode",
    ".Trash",
)

USER_IGNORE_FILE = Path("~/.vub-file-ignore").expanduser()


@dataclass(frozen=True)
class Rule:
    pattern: str
    negate: bool
    dir_only: bool
    anchored: bool


def _parse_line(line: str) -> Rule | None:
    line = line.rstrip("\n").strip()
    if not line or line.startswith("#"):
        return None
    negate = line.startswith("!")
    if negate:
        line = line[1:]
    dir_only = line.endswith("/")
    if dir_only:
        line = line[:-1]
    anchored = line.startswith("/")
    if anchored:
        line = line[1:]
    if not line:
        return None
    return Rule(pattern=line, negate=negate, dir_only=dir_only, anchored=anchored)


def parse_rules(lines: Iterable[str]) -> list[Rule]:
    rules = []
    for line in lines:
        rule = _parse_line(line)
        if rule is not None:
            rules.append(rule)
    return rules


def default_rules() -> list[Rule]:
    return [
        Rule(pattern=name, negate=False, dir_only=False, anchored=False)
        for name in DEFAULT_IGNORE_NAMES
    ]


def load_user_rules(path: Path = USER_IGNORE_FILE) -> list[Rule]:
    if not path.is_file():
        return []
    with path.open("r", encoding="utf-8", errors="ignore") as f:
        return parse_rules(f)


class IgnoreMatcher:
    def __init__(self, rules: list[Rule] | None = None):
        if rules is not None:
            self.rules = list(rules)
        else:
            self.rules = default_rules() + load_user_rules()

    @staticmethod
    def _rule_matches(rule: Rule, rel_path: str, name: str, is_dir: bool) -> bool:
        if rule.dir_only and not is_dir:
            return False
        if rule.anchored or "/" in rule.pattern:
            return fnmatch.fnmatch(rel_path, rule.pattern)
        return fnmatch.fnmatch(name, rule.pattern)

    def is_ignored(self, rel_path: str, name: str, is_dir: bool) -> bool:
        """rel_path is the entry's path relative to the indexed root, '/'-separated."""
        ignored = False
        for rule in self.rules:
            if self._rule_matches(rule, rel_path, name, is_dir):
                ignored = not rule.negate
        return ignored
