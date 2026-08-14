"""In-memory file index, built once and kept live by lib/watcher.py.

Symlinked directories are deliberately not descended into (they're indexed
as plain, non-directory entries) — this keeps the walk simple and immune to
symlink cycles without needing a visited-inode tracking scheme.
"""

from __future__ import annotations

import os
import stat as stat_module
from dataclasses import dataclass
from pathlib import Path

from lib.ignore import IgnoreMatcher


@dataclass
class Entry:
    path: str
    name: str
    name_lower: str
    dir: str
    is_dir: bool
    mtime: float


def _make_entry(path: str, name: str, is_dir: bool, mtime: float) -> Entry:
    return Entry(
        path=path,
        name=name,
        name_lower=name.lower(),
        dir=os.path.dirname(path),
        is_dir=is_dir,
        mtime=mtime,
    )


def _walk(root: str, matcher: IgnoreMatcher) -> tuple[list[Entry], list[str]]:
    entries: list[Entry] = []
    dirs: list[str] = []
    stack = [(root, "")]
    while stack:
        abs_dir, rel_dir = stack.pop()
        try:
            scanned = list(os.scandir(abs_dir))
        except OSError:
            continue
        for de in scanned:
            name = de.name
            rel_path = f"{rel_dir}/{name}" if rel_dir else name
            try:
                is_dir = de.is_dir(follow_symlinks=False)
                st = de.stat(follow_symlinks=False)
            except OSError:
                continue
            if matcher.is_ignored(rel_path, name, is_dir):
                continue
            abs_path = de.path
            entries.append(_make_entry(abs_path, name, is_dir, st.st_mtime))
            if is_dir:
                dirs.append(abs_path)
                stack.append((abs_path, rel_path))
    return entries, dirs


class FileIndex:
    def __init__(self) -> None:
        self._entries: dict[str, Entry] = {}
        self._dirs: set[str] = set()

    @classmethod
    def build(
        cls, roots: list[str], matcher: IgnoreMatcher | None = None
    ) -> FileIndex:
        matcher = matcher or IgnoreMatcher()
        index = cls()
        for root in roots:
            root = str(Path(root).expanduser())
            if not os.path.isdir(root):
                continue
            index._dirs.add(root)
            entries, dirs = _walk(root, matcher)
            for entry in entries:
                index._entries[entry.path] = entry
            index._dirs.update(dirs)
        return index

    def entries(self):
        return self._entries.values()

    def directories(self) -> set[str]:
        return self._dirs

    def get(self, path: str) -> Entry | None:
        return self._entries.get(path)

    def __len__(self) -> int:
        return len(self._entries)

    def add_or_update(self, path: str) -> Entry | None:
        """(Re)index a single path. Used by the watcher on create/modify events."""
        try:
            st = os.stat(path, follow_symlinks=False)
        except OSError:
            self.remove(path)
            return None
        is_dir = stat_module.S_ISDIR(st.st_mode)
        entry = _make_entry(path, os.path.basename(path), is_dir, st.st_mtime)
        self._entries[path] = entry
        if is_dir:
            self._dirs.add(path)
        return entry

    def remove(self, path: str) -> None:
        self._entries.pop(path, None)
        was_dir = path in self._dirs
        self._dirs.discard(path)
        if was_dir:
            prefix = path + "/"
            for child_path in list(self._entries):
                if child_path.startswith(prefix):
                    self._entries.pop(child_path, None)
            for child_dir in list(self._dirs):
                if child_dir.startswith(prefix):
                    self._dirs.discard(child_dir)
