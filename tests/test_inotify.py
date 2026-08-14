import os
import time

from lib.inotify import Flags, Inotify


def _collect_events(inotify, expected_count, timeout=3.0):
    events = []
    deadline = time.time() + timeout
    while time.time() < deadline and len(events) < expected_count:
        events.extend(inotify.read(timeout=0.5))
    return events


def test_add_watch_returns_positive_descriptor(tmp_path):
    with Inotify() as inotify:
        wd = inotify.add_watch(str(tmp_path))
        assert wd >= 0


def test_create_and_delete_events_are_observed(tmp_path):
    with Inotify() as inotify:
        inotify.add_watch(str(tmp_path))

        (tmp_path / "a.txt").write_text("hi")
        os.remove(tmp_path / "a.txt")

        events = _collect_events(inotify, expected_count=2)

        create_events = [e for e in events if e.mask & Flags.CREATE and e.name == "a.txt"]
        delete_events = [e for e in events if e.mask & Flags.DELETE and e.name == "a.txt"]
        assert create_events, f"no CREATE event seen among {events}"
        assert delete_events, f"no DELETE event seen among {events}"


def test_rm_watch_stops_events(tmp_path):
    with Inotify() as inotify:
        wd = inotify.add_watch(str(tmp_path))
        inotify.rm_watch(wd)

        (tmp_path / "b.txt").write_text("hi")

        events = inotify.read(timeout=0.5)
        # An IGNORED event fires when the watch is removed, but no CREATE.
        assert not any(e.mask & Flags.CREATE for e in events)


def test_rm_watch_on_already_removed_watch_does_not_raise(tmp_path):
    with Inotify() as inotify:
        wd = inotify.add_watch(str(tmp_path))
        inotify.rm_watch(wd)
        inotify.rm_watch(wd)  # second removal should be a no-op, not raise


def test_delete_self_event_on_watched_directory_removal(tmp_path):
    watched_dir = tmp_path / "watched"
    watched_dir.mkdir()
    with Inotify() as inotify:
        inotify.add_watch(str(watched_dir))
        os.rmdir(watched_dir)

        events = _collect_events(inotify, expected_count=1)
        assert any(e.mask & Flags.DELETE_SELF for e in events)
