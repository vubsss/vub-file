import errno
import os

from lib.ignore import IgnoreMatcher, parse_rules
from lib.index import FileIndex
from lib.store import Store
from lib.watcher import Watcher


def _build_index(tmp_path):
    (tmp_path / "existing.txt").write_text("hi")
    return FileIndex.build([str(tmp_path)])


def test_create_and_delete_are_reflected_in_index(tmp_path):
    index = _build_index(tmp_path)
    watcher = Watcher(index)
    try:
        new_path = tmp_path / "new.txt"
        new_path.write_text("hi")
        watcher.process_pending(timeout=2.0)
        assert index.get(str(new_path)) is not None

        os.remove(new_path)
        watcher.process_pending(timeout=2.0)
        assert index.get(str(new_path)) is None
    finally:
        watcher.close()


def test_new_subdirectory_is_watched_and_its_children_indexed(tmp_path):
    index = _build_index(tmp_path)
    watcher = Watcher(index)
    try:
        sub = tmp_path / "sub"
        sub.mkdir()
        watcher.process_pending(timeout=2.0)
        assert index.get(str(sub)) is not None
        assert str(sub) in index.directories()

        child = sub / "child.txt"
        child.write_text("hi")
        watcher.process_pending(timeout=2.0)
        assert index.get(str(child)) is not None
    finally:
        watcher.close()


def test_rename_moves_the_entry(tmp_path):
    index = _build_index(tmp_path)
    watcher = Watcher(index)
    try:
        old_path = tmp_path / "old_name.txt"
        old_path.write_text("hi")
        watcher.process_pending(timeout=2.0)
        assert index.get(str(old_path)) is not None

        new_path = tmp_path / "new_name.txt"
        os.rename(old_path, new_path)
        watcher.process_pending(timeout=2.0)

        assert index.get(str(old_path)) is None
        assert index.get(str(new_path)) is not None
    finally:
        watcher.close()


def test_store_is_kept_in_sync(tmp_path):
    index = _build_index(tmp_path)
    with Store(tmp_path / "index.db") as store:
        watcher = Watcher(index, store=store)
        try:
            new_path = tmp_path / "new.txt"
            new_path.write_text("hi")
            watcher.process_pending(timeout=2.0)

            reloaded = store.load_index()
            assert reloaded.get(str(new_path)) is not None

            os.remove(new_path)
            watcher.process_pending(timeout=2.0)

            reloaded = store.load_index()
            assert reloaded.get(str(new_path)) is None
        finally:
            watcher.close()


def test_ignored_new_file_is_not_indexed(tmp_path):
    index = _build_index(tmp_path)
    matcher = IgnoreMatcher(rules=parse_rules(["*.tmp"]))
    watcher = Watcher(index, matcher=matcher)
    try:
        ignored_path = tmp_path / "scratch.tmp"
        ignored_path.write_text("hi")
        watcher.process_pending(timeout=2.0)
        assert index.get(str(ignored_path)) is None
    finally:
        watcher.close()


def test_enospc_falls_back_to_polling(tmp_path, monkeypatch):
    index = _build_index(tmp_path)
    watcher = Watcher(index)
    try:
        blocked_dir = tmp_path / "blocked"
        real_add_watch = watcher._inotify.add_watch

        def flaky_add_watch(path):
            if path == str(blocked_dir):
                raise OSError(errno.ENOSPC, "No space left on device")
            return real_add_watch(path)

        monkeypatch.setattr(watcher._inotify, "add_watch", flaky_add_watch)

        blocked_dir.mkdir()
        watcher.process_pending(timeout=2.0)

        assert str(blocked_dir) in watcher._unwatched_dirs
        assert index.get(str(blocked_dir)) is not None

        # A file created inside the unwatched dir won't generate inotify
        # events (no watch on it) — only the poll fallback finds it.
        new_file = blocked_dir / "child.txt"
        new_file.write_text("hi")
        assert index.get(str(new_file)) is None

        watcher.poll_unwatched()
        assert index.get(str(new_file)) is not None
    finally:
        watcher.close()
