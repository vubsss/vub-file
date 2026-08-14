"""SQLite persistence for the file index and frecency data (stdlib sqlite3).

Two responsibilities live here on purpose: the index cache (so a restarted
extension has instant search results instead of waiting on a fresh walk)
and frecency (so "most relevant" survives restarts too). Both are cheap,
single-file, dependency-free with sqlite3 from the standard library.
"""

from __future__ import annotations

import sqlite3
import time
from pathlib import Path

from lib.index import Entry, FileIndex

DEFAULT_DB_PATH = Path("~/.cache/vub-file/index.db").expanduser()

_SCHEMA = """
CREATE TABLE IF NOT EXISTS files (
    path TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    name_lower TEXT NOT NULL,
    dir TEXT NOT NULL,
    is_dir INTEGER NOT NULL,
    mtime REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS frecency (
    path TEXT PRIMARY KEY,
    score REAL NOT NULL,
    last_used REAL NOT NULL
);
"""


class Store:
    def __init__(self, db_path: Path | str = DEFAULT_DB_PATH):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(self.db_path))
        self._conn.executescript(_SCHEMA)
        self._conn.commit()

    def close(self) -> None:
        self._conn.close()

    def __enter__(self) -> Store:
        return self

    def __exit__(self, *exc_info) -> None:
        self.close()

    # --- file index persistence ---

    def save_index(self, index: FileIndex) -> None:
        with self._conn:
            self._conn.execute("DELETE FROM files")
            self._conn.executemany(
                "INSERT INTO files (path, name, name_lower, dir, is_dir, mtime) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                [
                    (e.path, e.name, e.name_lower, e.dir, int(e.is_dir), e.mtime)
                    for e in index.entries()
                ],
            )

    def load_index(self) -> FileIndex:
        cur = self._conn.execute(
            "SELECT path, name, name_lower, dir, is_dir, mtime FROM files"
        )
        entries = (
            Entry(
                path=path,
                name=name,
                name_lower=name_lower,
                dir=dir_,
                is_dir=bool(is_dir),
                mtime=mtime,
            )
            for path, name, name_lower, dir_, is_dir, mtime in cur
        )
        return FileIndex.from_entries(entries)

    def upsert_file(self, entry: Entry) -> None:
        with self._conn:
            self._conn.execute(
                "INSERT INTO files (path, name, name_lower, dir, is_dir, mtime) "
                "VALUES (?, ?, ?, ?, ?, ?) "
                "ON CONFLICT(path) DO UPDATE SET "
                "name=excluded.name, name_lower=excluded.name_lower, "
                "dir=excluded.dir, is_dir=excluded.is_dir, mtime=excluded.mtime",
                (
                    entry.path,
                    entry.name,
                    entry.name_lower,
                    entry.dir,
                    int(entry.is_dir),
                    entry.mtime,
                ),
            )

    def delete_file(self, path: str) -> None:
        with self._conn:
            self._conn.execute(
                "DELETE FROM files WHERE path = ? OR path LIKE ?", (path, path + "/%")
            )

    # --- frecency persistence ---

    def get_frecency(self, path: str) -> tuple[float, float] | None:
        row = self._conn.execute(
            "SELECT score, last_used FROM frecency WHERE path = ?", (path,)
        ).fetchone()
        return tuple(row) if row is not None else None

    def bump_frecency(self, path: str, increment: float = 1.0) -> None:
        now = time.time()
        with self._conn:
            self._conn.execute(
                "INSERT INTO frecency (path, score, last_used) VALUES (?, ?, ?) "
                "ON CONFLICT(path) DO UPDATE SET "
                "score = score + excluded.score, last_used = excluded.last_used",
                (path, increment, now),
            )

    def top_frecent(self, limit: int = 8) -> list[str]:
        cur = self._conn.execute(
            "SELECT path FROM frecency ORDER BY score DESC, last_used DESC LIMIT ?",
            (limit,),
        )
        return [row[0] for row in cur]

    def all_frecency(self) -> list[tuple[str, float, float]]:
        cur = self._conn.execute("SELECT path, score, last_used FROM frecency")
        return [tuple(row) for row in cur]
