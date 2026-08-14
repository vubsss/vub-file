"""Keeps a FileIndex (and its Store) live via inotify instead of rescans.

Holds one inotify watch per non-ignored indexed directory. CREATE/DELETE/
MOVED_FROM/MOVED_TO apply directly to the in-memory index and the sqlite
store — no full rescans. If a directory's watch can't be added (almost
always ENOSPC, the fs.inotify.max_user_watches limit), that one directory
falls back to periodic polling instead of the extension crashing.

Known limitation: ignore-rule matching on newly created entries only sees
the entry's bare name, not its full path relative to the indexed root, so
a user ignore pattern anchored with a leading `/` or containing `/` (rather
than a plain basename like the built-in defaults) won't be re-evaluated
correctly for paths discovered after the initial index build.
"""

from __future__ import annotations

import errno
import logging
import os
import threading
import time

from lib.ignore import IgnoreMatcher
from lib.index import Entry, FileIndex
from lib.inotify import Event, Flags, Inotify
from lib.store import Store

logger = logging.getLogger(__name__)

DEFAULT_POLL_FALLBACK_INTERVAL = 30.0  # seconds, for ENOSPC-fallback directories


class Watcher:
    def __init__(
        self,
        index: FileIndex,
        store: Store | None = None,
        matcher: IgnoreMatcher | None = None,
        poll_interval: float = DEFAULT_POLL_FALLBACK_INTERVAL,
        inotify: Inotify | None = None,
    ):
        self._index = index
        self._store = store
        self._matcher = matcher or IgnoreMatcher()
        self._poll_interval = poll_interval
        self._inotify = inotify or Inotify()
        self._wd_to_path: dict[int, str] = {}
        self._path_to_wd: dict[str, int] = {}
        self._unwatched_dirs: set[str] = set()
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._last_poll = 0.0

        for directory in list(index.directories()):
            self._add_watch(directory)

    # --- watch bookkeeping ---

    def _add_watch(self, path: str) -> None:
        if path in self._path_to_wd or path in self._unwatched_dirs:
            return
        try:
            wd = self._inotify.add_watch(path)
        except OSError as exc:
            if exc.errno == errno.ENOSPC:
                logger.warning(
                    "inotify watch limit hit (fs.inotify.max_user_watches); "
                    "falling back to polling for %s",
                    path,
                )
            else:
                logger.warning("could not watch %s: %s", path, exc)
            self._unwatched_dirs.add(path)
            return
        self._wd_to_path[wd] = path
        self._path_to_wd[path] = wd

    def _remove_watch(self, path: str) -> None:
        wd = self._path_to_wd.pop(path, None)
        if wd is not None:
            self._inotify.rm_watch(wd)
            self._wd_to_path.pop(wd, None)
        self._unwatched_dirs.discard(path)

    def _drop_watch_bookkeeping(self, wd: int) -> None:
        path = self._wd_to_path.pop(wd, None)
        if path is not None:
            self._path_to_wd.pop(path, None)

    # --- index/store mutation ---

    def _persist_upsert(self, entry: Entry | None) -> None:
        if self._store is not None and entry is not None:
            self._store.upsert_file(entry)

    def _persist_remove(self, path: str) -> None:
        if self._store is not None:
            self._store.delete_file(path)

    def _forget(self, path: str) -> None:
        self._index.remove(path)
        self._persist_remove(path)
        self._remove_watch(path)

    def _learn(self, path: str, name: str, is_dir: bool) -> None:
        if self._matcher.is_ignored(name, name, is_dir):
            return
        entry = self._index.add_or_update(path)
        self._persist_upsert(entry)
        if is_dir:
            self._add_watch(path)

    # --- event handling ---

    def _handle_event(self, event: Event) -> None:
        if event.mask & Flags.IGNORED:
            self._drop_watch_bookkeeping(event.wd)
            return

        parent = self._wd_to_path.get(event.wd)
        if parent is None:
            return

        if not event.name:
            if event.mask & (Flags.DELETE_SELF | Flags.MOVE_SELF):
                self._forget(parent)
            return

        path = os.path.join(parent, event.name)

        if event.mask & (Flags.DELETE | Flags.MOVED_FROM):
            self._forget(path)
            return

        if event.mask & (Flags.CREATE | Flags.MOVED_TO):
            is_dir = bool(event.mask & Flags.ISDIR)
            self._learn(path, event.name, is_dir)

    def _process_available(self, timeout: float) -> int:
        events = self._inotify.read(timeout=timeout)
        for event in events:
            self._handle_event(event)
        return len(events)

    def process_pending(self, timeout: float = 1.0) -> int:
        """Synchronously process whatever inotify events are (or become,
        within `timeout` seconds) available. Meant for tests and for
        manually pumping the watcher outside of its background thread."""
        return self._process_available(timeout)

    # --- ENOSPC fallback polling ---

    def poll_unwatched(self) -> None:
        for directory in list(self._unwatched_dirs):
            if not os.path.isdir(directory):
                self._forget(directory)
                continue
            try:
                current_names = set(os.listdir(directory))
            except OSError:
                continue
            indexed_names = {
                os.path.basename(e.path) for e in self._index.entries() if e.dir == directory
            }
            for name in current_names - indexed_names:
                path = os.path.join(directory, name)
                is_dir = os.path.isdir(path)
                self._learn(path, name, is_dir)
            for name in indexed_names - current_names:
                self._forget(os.path.join(directory, name))

    def _maybe_poll_unwatched(self) -> None:
        now = time.time()
        if now - self._last_poll < self._poll_interval:
            return
        self._last_poll = now
        self.poll_unwatched()

    # --- lifecycle ---

    def start(self) -> None:
        if self._thread is not None:
            return
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run, daemon=True, name="vub-file-watcher")
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout=2.0)
            self._thread = None

    def close(self) -> None:
        self.stop()
        self._inotify.close()

    def _run(self) -> None:
        while not self._stop_event.is_set():
            self._process_available(timeout=1.0)
            self._maybe_poll_unwatched()
