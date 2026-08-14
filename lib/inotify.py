"""Minimal ctypes wrapper over the Linux inotify syscalls.

Written directly against inotify_init1(2)/inotify_add_watch(2)/
inotify_rm_watch(2)/inotify(7) rather than depending on a package like
`watchdog`, so lib/watcher.py has no third-party dependency to require
users to pip install (Ulauncher doesn't install extension dependencies
for them).
"""

from __future__ import annotations

import ctypes
import ctypes.util
import errno
import os
import select
import struct
from dataclasses import dataclass
from enum import IntFlag

_libc = ctypes.CDLL(ctypes.util.find_library("c"), use_errno=True)

_libc.inotify_init1.argtypes = [ctypes.c_int]
_libc.inotify_init1.restype = ctypes.c_int

_libc.inotify_add_watch.argtypes = [ctypes.c_int, ctypes.c_char_p, ctypes.c_uint32]
_libc.inotify_add_watch.restype = ctypes.c_int

_libc.inotify_rm_watch.argtypes = [ctypes.c_int, ctypes.c_int]
_libc.inotify_rm_watch.restype = ctypes.c_int

IN_NONBLOCK = 0o4000
IN_CLOEXEC = 0o2000000


class Flags(IntFlag):
    ACCESS = 0x00000001
    MODIFY = 0x00000002
    ATTRIB = 0x00000004
    CLOSE_WRITE = 0x00000008
    CLOSE_NOWRITE = 0x00000010
    OPEN = 0x00000020
    MOVED_FROM = 0x00000040
    MOVED_TO = 0x00000080
    CREATE = 0x00000100
    DELETE = 0x00000200
    DELETE_SELF = 0x00000400
    MOVE_SELF = 0x00000800
    UNMOUNT = 0x00002000
    Q_OVERFLOW = 0x00004000
    IGNORED = 0x00008000
    ONLYDIR = 0x01000000
    DONT_FOLLOW = 0x02000000
    EXCL_UNLINK = 0x04000000
    MASK_CREATE = 0x10000000
    MASK_ADD = 0x20000000
    ISDIR = 0x40000000
    ONESHOT = 0x80000000


# What lib/watcher.py subscribes each watched directory to: enough to keep
# the index in sync (CREATE/DELETE/MOVED_*) plus enough to notice a watched
# directory itself disappearing or getting renamed away (DELETE_SELF/
# MOVE_SELF), so stale watch descriptors can be pruned.
DEFAULT_WATCH_FLAGS = (
    Flags.CREATE
    | Flags.DELETE
    | Flags.MOVED_FROM
    | Flags.MOVED_TO
    | Flags.DELETE_SELF
    | Flags.MOVE_SELF
)

_EVENT_HEADER_FMT = "iIII"  # wd(int32), mask(uint32), cookie(uint32), name_len(uint32)
_EVENT_HEADER_SIZE = struct.calcsize(_EVENT_HEADER_FMT)
_READ_BUFFER_SIZE = 64 * 1024


@dataclass(frozen=True)
class Event:
    wd: int
    mask: int
    cookie: int
    name: str


def _errno_error(what: str) -> OSError:
    err = ctypes.get_errno()
    return OSError(err, f"{what}: {os.strerror(err)}")


def _parse_events(data: bytes):
    offset = 0
    while offset < len(data):
        wd, mask, cookie, name_len = struct.unpack_from(_EVENT_HEADER_FMT, data, offset)
        offset += _EVENT_HEADER_SIZE
        raw_name = data[offset : offset + name_len]
        offset += name_len
        name = raw_name.split(b"\x00", 1)[0].decode("utf-8", "surrogateescape")
        yield Event(wd=wd, mask=mask, cookie=cookie, name=name)


class Inotify:
    def __init__(self) -> None:
        fd = _libc.inotify_init1(IN_NONBLOCK | IN_CLOEXEC)
        if fd < 0:
            raise _errno_error("inotify_init1")
        self.fd = fd

    def add_watch(self, path: str, mask: int = DEFAULT_WATCH_FLAGS) -> int:
        wd = _libc.inotify_add_watch(self.fd, path.encode("utf-8", "surrogateescape"), mask)
        if wd < 0:
            raise _errno_error(f"inotify_add_watch({path!r})")
        return wd

    def rm_watch(self, wd: int) -> None:
        rc = _libc.inotify_rm_watch(self.fd, wd)
        if rc < 0:
            err = ctypes.get_errno()
            if err == errno.EINVAL:
                # Watch is already gone (e.g. its directory was deleted,
                # which auto-removes the watch) — nothing left to clean up.
                return
            raise OSError(err, f"inotify_rm_watch({wd}): {os.strerror(err)}")

    def read(self, timeout: float | None = None) -> list[Event]:
        """Read pending events. With a timeout, returns [] if none arrive in time."""
        if timeout is not None:
            ready, _, _ = select.select([self.fd], [], [], timeout)
            if not ready:
                return []
        try:
            data = os.read(self.fd, _READ_BUFFER_SIZE)
        except BlockingIOError:
            return []
        return list(_parse_events(data))

    def close(self) -> None:
        os.close(self.fd)

    def __enter__(self) -> Inotify:
        return self

    def __exit__(self, *exc_info) -> None:
        self.close()
