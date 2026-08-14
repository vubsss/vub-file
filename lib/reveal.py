"""Open the desktop's file manager at a search result.

Enter on a result reveals the file rather than launching it, and "reveal"
means the containing folder opened with the file *selected* — not just the
folder opened blind. The freedesktop.org `org.freedesktop.FileManager1`
D-Bus interface is what does the selecting; it's implemented by Nautilus,
Dolphin, Nemo, Thunar and PCManFM, and activating it starts the file manager
if it isn't already running.

Anything outside that (a bare window manager, a file manager without the
interface, no gi) falls back to `xdg-open` on the folder, which loses the
selection but still lands in the right place.

gi is imported lazily inside _show() so the pure helpers here stay testable
without GTK installed, matching how the rest of lib/ avoids importing
Ulauncher.
"""

from __future__ import annotations

import logging
import os
import subprocess
import threading
from pathlib import Path

logger = logging.getLogger(__name__)

BUS_NAME = "org.freedesktop.FileManager1"
OBJECT_PATH = "/org/freedesktop/FileManager1"
INTERFACE = "org.freedesktop.FileManager1"

# Generous enough to cover a cold file-manager start (the D-Bus call activates
# it), short enough that a wedged service doesn't leak the worker thread.
_TIMEOUT_MS = 15000


def target_for(path: str) -> tuple[str, str]:
    """Return the (D-Bus method, URI) pair that reveals `path`.

    A directory is opened as itself (ShowFolders); anything else is opened in
    its parent with the item selected (ShowItems).
    """
    method = "ShowFolders" if os.path.isdir(path) else "ShowItems"
    return method, Path(path).absolute().as_uri()


def fallback_command(path: str) -> list[str]:
    """The xdg-open argv used when FileManager1 is unavailable."""
    folder = path if os.path.isdir(path) else os.path.dirname(path)
    return ["xdg-open", folder]


def _show(method: str, uri: str) -> None:
    from gi.repository import Gio, GLib

    bus = Gio.bus_get_sync(Gio.BusType.SESSION, None)
    bus.call_sync(
        BUS_NAME,
        OBJECT_PATH,
        INTERFACE,
        method,
        GLib.Variant("(ass)", ([uri], "")),
        None,
        Gio.DBusCallFlags.NONE,
        _TIMEOUT_MS,
        None,
    )


def reveal_sync(path: str) -> None:
    """Reveal `path`, blocking until the file manager has been asked to."""
    try:
        _show(*target_for(path))
    except Exception:
        logger.debug("FileManager1 unavailable for %s, falling back", path, exc_info=True)
        try:
            subprocess.Popen(fallback_command(path))
        except OSError:
            logger.exception("could not reveal %s", path)


def reveal(path: str) -> None:
    """Reveal `path` off the caller's thread.

    Activating a cold file manager over D-Bus can take a second or two, and
    this runs on the extension's event loop — blocking there would stall the
    next query.
    """
    threading.Thread(
        target=reveal_sync, args=(path,), daemon=True, name="vub-file-reveal"
    ).start()
