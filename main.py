"""Ulauncher extension entry point — thin glue between lib/ and the Ulauncher API.

All the actual logic (indexing, watching, matching, ranking, persistence)
lives in lib/ and is unit-tested without Ulauncher installed. This file only
wires that logic to Ulauncher's event/action API.
"""

from __future__ import annotations

import logging
import threading

from ulauncher.api.client.EventListener import EventListener
from ulauncher.api.client.Extension import Extension
from ulauncher.api.shared.action.ExtensionCustomAction import ExtensionCustomAction
from ulauncher.api.shared.action.OpenAction import OpenAction
from ulauncher.api.shared.action.RenderResultListAction import RenderResultListAction
from ulauncher.api.shared.event import (
    ItemEnterEvent,
    KeywordQueryEvent,
    PreferencesEvent,
    PreferencesUpdateEvent,
)
from ulauncher.api.shared.item.ExtensionResultItem import ExtensionResultItem

from lib.frecency import Frecency
from lib.ignore import IgnoreMatcher, Rule, default_rules, load_user_rules
from lib.index import Entry, FileIndex
from lib.matcher import search
from lib.store import Store
from lib.watcher import Watcher

logger = logging.getLogger(__name__)

ICON = "images/icon.png"
DEFAULT_MAX_RESULTS = 8
_HIDDEN_RULE = Rule(pattern=".*", negate=False, dir_only=False, anchored=False)


def _split_roots(raw: str) -> list[str]:
    return [part.strip() for part in raw.split(",") if part.strip()]


def _parse_bool(value) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in ("1", "true", "yes", "on")
    return bool(value)


def _build_matcher(ignore_hidden: bool) -> IgnoreMatcher:
    rules = default_rules() + load_user_rules()
    if ignore_hidden:
        rules.append(_HIDDEN_RULE)
    return IgnoreMatcher(rules=rules)


def _build_item(entry: Entry) -> ExtensionResultItem:
    return ExtensionResultItem(
        icon=ICON,
        name=entry.name,
        description=entry.dir,
        on_enter=ExtensionCustomAction(entry.path, keep_app_open=False),
    )


class VubFileExtension(Extension):
    def __init__(self):
        super().__init__()
        self.store = Store()
        self.frecency = Frecency(self.store)
        self.index = FileIndex()
        self.watcher: Watcher | None = None
        self.search_roots = ["~"]
        self.max_results = DEFAULT_MAX_RESULTS
        self.ignore_hidden = True

        self.subscribe(KeywordQueryEvent, KeywordQueryEventListener())
        self.subscribe(ItemEnterEvent, ItemEnterEventListener())
        self.subscribe(PreferencesEvent, PreferencesEventListener())
        self.subscribe(PreferencesUpdateEvent, PreferencesUpdateEventListener())

    def start_indexing(self) -> None:
        """Serve from the on-disk cache immediately, then reconcile against
        the real filesystem and attach the live watcher in the background."""
        self.index = self.store.load_index()

        def _reconcile_and_watch() -> None:
            matcher = _build_matcher(self.ignore_hidden)
            fresh = FileIndex.build(self.search_roots, matcher=matcher)
            self.store.save_index(fresh)
            self.index = fresh
            if self.watcher is not None:
                self.watcher.close()
            self.watcher = Watcher(self.index, store=self.store, matcher=matcher)
            self.watcher.start()

        threading.Thread(
            target=_reconcile_and_watch, daemon=True, name="vub-file-reindex"
        ).start()


class KeywordQueryEventListener(EventListener):
    def on_event(self, event: KeywordQueryEvent, extension: VubFileExtension):
        query = (event.get_argument() or "").strip()

        if not query:
            paths = extension.frecency.top(limit=extension.max_results)
            entries = [extension.index.get(p) for p in paths]
            results = [e for e in entries if e is not None]
        else:
            results = search(
                extension.index.entries(),
                query,
                limit=extension.max_results,
                boost=extension.frecency.boost,
            )

        items = [_build_item(entry) for entry in results]
        return RenderResultListAction(items)


class ItemEnterEventListener(EventListener):
    def on_event(self, event: ItemEnterEvent, extension: VubFileExtension):
        path = event.get_data()
        extension.frecency.record_open(path)
        return OpenAction(path)


class PreferencesEventListener(EventListener):
    def on_event(self, event: PreferencesEvent, extension: VubFileExtension):
        prefs = event.preferences
        extension.search_roots = _split_roots(prefs.get("search_roots", "~"))
        extension.max_results = int(prefs.get("max_results", DEFAULT_MAX_RESULTS))
        extension.ignore_hidden = _parse_bool(prefs.get("ignore_hidden", True))
        extension.start_indexing()


class PreferencesUpdateEventListener(EventListener):
    def on_event(self, event: PreferencesUpdateEvent, extension: VubFileExtension):
        if event.id == "search_roots":
            extension.search_roots = _split_roots(event.new_value)
            extension.start_indexing()
        elif event.id == "max_results":
            extension.max_results = int(event.new_value)
        elif event.id == "ignore_hidden":
            extension.ignore_hidden = _parse_bool(event.new_value)
            extension.start_indexing()


if __name__ == "__main__":
    VubFileExtension().run()
