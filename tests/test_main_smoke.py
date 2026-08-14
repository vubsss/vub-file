"""Exercises main.py's event-listener wiring against a minimal stand-in for
the `ulauncher` package (which isn't installed in this environment — it's a
GTK desktop app's plugin API). This can't replace real end-to-end testing
inside Ulauncher, but it does catch import/attribute-naming mistakes and
verifies the listeners actually call into lib/ correctly.
"""

import sys
import types


def _install_ulauncher_stub():
    def make_module(name):
        mod = types.ModuleType(name)
        sys.modules[name] = mod
        return mod

    ulauncher = make_module("ulauncher")
    api = make_module("ulauncher.api")
    client = make_module("ulauncher.api.client")
    shared = make_module("ulauncher.api.shared")
    action_pkg = make_module("ulauncher.api.shared.action")
    item_pkg = make_module("ulauncher.api.shared.item")

    ulauncher.api = api
    api.client = client
    api.shared = shared
    shared.action = action_pkg
    shared.item = item_pkg

    ext_mod = make_module("ulauncher.api.client.Extension")

    class Extension:
        def __init__(self):
            self.listeners = {}

        def subscribe(self, event_type, listener):
            self.listeners[event_type] = listener

        def run(self):
            pass

    ext_mod.Extension = Extension
    client.Extension = ext_mod

    listener_mod = make_module("ulauncher.api.client.EventListener")

    class EventListener:
        pass

    listener_mod.EventListener = EventListener
    client.EventListener = listener_mod

    event_mod = make_module("ulauncher.api.shared.event")

    class KeywordQueryEvent:
        def __init__(self, argument):
            self._argument = argument

        def get_argument(self):
            return self._argument

    class ItemEnterEvent:
        def __init__(self, data):
            self._data = data

        def get_data(self):
            return self._data

    class PreferencesEvent:
        def __init__(self, preferences):
            self.preferences = preferences

    class PreferencesUpdateEvent:
        def __init__(self, id, new_value):
            self.id = id
            self.new_value = new_value

    event_mod.KeywordQueryEvent = KeywordQueryEvent
    event_mod.ItemEnterEvent = ItemEnterEvent
    event_mod.PreferencesEvent = PreferencesEvent
    event_mod.PreferencesUpdateEvent = PreferencesUpdateEvent
    shared.event = event_mod

    custom_action_mod = make_module("ulauncher.api.shared.action.ExtensionCustomAction")

    class ExtensionCustomAction:
        def __init__(self, data, keep_app_open=False):
            self.data = data
            self.keep_app_open = keep_app_open

    custom_action_mod.ExtensionCustomAction = ExtensionCustomAction
    action_pkg.ExtensionCustomAction = custom_action_mod

    open_action_mod = make_module("ulauncher.api.shared.action.OpenAction")

    class OpenAction:
        def __init__(self, path):
            self.path = path

    open_action_mod.OpenAction = OpenAction
    action_pkg.OpenAction = open_action_mod

    do_nothing_action_mod = make_module("ulauncher.api.shared.action.DoNothingAction")

    class DoNothingAction:
        pass

    do_nothing_action_mod.DoNothingAction = DoNothingAction
    action_pkg.DoNothingAction = do_nothing_action_mod

    render_action_mod = make_module("ulauncher.api.shared.action.RenderResultListAction")

    class RenderResultListAction:
        def __init__(self, items):
            self.items = items

    render_action_mod.RenderResultListAction = RenderResultListAction
    action_pkg.RenderResultListAction = render_action_mod

    result_item_mod = make_module("ulauncher.api.shared.item.ExtensionResultItem")

    class ExtensionResultItem:
        def __init__(self, icon, name, description, on_enter, on_alt_enter=None):
            self.icon = icon
            self.name = name
            self.description = description
            self.on_enter = on_enter
            self.on_alt_enter = on_alt_enter

    result_item_mod.ExtensionResultItem = ExtensionResultItem
    item_pkg.ExtensionResultItem = result_item_mod

    return types.SimpleNamespace(
        KeywordQueryEvent=KeywordQueryEvent,
        ItemEnterEvent=ItemEnterEvent,
        PreferencesEvent=PreferencesEvent,
        PreferencesUpdateEvent=PreferencesUpdateEvent,
        ExtensionCustomAction=ExtensionCustomAction,
        OpenAction=OpenAction,
        DoNothingAction=DoNothingAction,
        RenderResultListAction=RenderResultListAction,
        ExtensionResultItem=ExtensionResultItem,
    )


stub = _install_ulauncher_stub()

import main  # noqa: E402  (must come after the ulauncher stub is installed)
from lib.index import FileIndex  # noqa: E402


def _make_extension(tmp_path, monkeypatch):
    from lib.store import Store

    monkeypatch.setattr(main, "Store", lambda: Store(tmp_path / "index.db"))
    extension = main.VubFileExtension()
    extension.max_results = 8
    return extension


def test_keyword_query_returns_ranked_matches(tmp_path, monkeypatch):
    (tmp_path / "test_notes.txt").write_text("a")
    (tmp_path / "other.txt").write_text("b")
    extension = _make_extension(tmp_path, monkeypatch)
    extension.index = FileIndex.build([str(tmp_path)])

    event = stub.KeywordQueryEvent("test")
    action = main.KeywordQueryEventListener().on_event(event, extension)

    assert isinstance(action, stub.RenderResultListAction)
    names = [item.name for item in action.items]
    assert "test_notes.txt" in names
    assert "other.txt" not in names


def test_empty_query_returns_frecent_files(tmp_path, monkeypatch):
    (tmp_path / "opened_before.txt").write_text("a")
    extension = _make_extension(tmp_path, monkeypatch)
    extension.index = FileIndex.build([str(tmp_path)])
    target = str(tmp_path / "opened_before.txt")
    extension.frecency.record_open(target)

    event = stub.KeywordQueryEvent("")
    action = main.KeywordQueryEventListener().on_event(event, extension)

    assert [item.name for item in action.items] == ["opened_before.txt"]


def test_results_bind_reveal_to_enter_and_open_to_alt_enter(tmp_path, monkeypatch):
    (tmp_path / "test_notes.txt").write_text("a")
    extension = _make_extension(tmp_path, monkeypatch)
    extension.index = FileIndex.build([str(tmp_path)])

    event = stub.KeywordQueryEvent("test")
    item = main.KeywordQueryEventListener().on_event(event, extension).items[0]

    path = str(tmp_path / "test_notes.txt")
    assert item.on_enter.data == {"path": path, "action": "reveal"}
    assert item.on_alt_enter.data == {"path": path, "action": "open"}


def test_item_enter_reveals_file_and_records_frecency(tmp_path, monkeypatch):
    extension = _make_extension(tmp_path, monkeypatch)
    path = str(tmp_path / "some_file.txt")
    revealed = []
    monkeypatch.setattr(main, "reveal", revealed.append)

    event = stub.ItemEnterEvent({"path": path, "action": "reveal"})
    action = main.ItemEnterEventListener().on_event(event, extension)

    assert isinstance(action, stub.DoNothingAction)
    assert revealed == [path]
    assert extension.store.get_frecency(path) is not None


def test_item_alt_enter_opens_file_and_records_frecency(tmp_path, monkeypatch):
    extension = _make_extension(tmp_path, monkeypatch)
    path = str(tmp_path / "some_file.txt")
    monkeypatch.setattr(main, "reveal", _fail_if_called)

    event = stub.ItemEnterEvent({"path": path, "action": "open"})
    action = main.ItemEnterEventListener().on_event(event, extension)

    assert isinstance(action, stub.OpenAction)
    assert action.path == path
    assert extension.store.get_frecency(path) is not None


def _fail_if_called(path):
    raise AssertionError("reveal() should not run for the open action")


def test_preferences_event_sets_roots_and_max_results(tmp_path, monkeypatch):
    extension = _make_extension(tmp_path, monkeypatch)
    event = stub.PreferencesEvent(
        {"search_roots": str(tmp_path), "max_results": "5", "ignore_hidden": False}
    )

    main.PreferencesEventListener().on_event(event, extension)

    assert extension.search_roots == [str(tmp_path)]
    assert extension.max_results == 5
    assert extension.ignore_hidden is False


def test_preferences_update_event_updates_ignore_hidden(tmp_path, monkeypatch):
    extension = _make_extension(tmp_path, monkeypatch)
    event = stub.PreferencesUpdateEvent("ignore_hidden", "false")

    main.PreferencesUpdateEventListener().on_event(event, extension)

    assert extension.ignore_hidden is False


def test_build_matcher_respects_ignore_hidden():
    hidden_ignored = main._build_matcher(ignore_hidden=True)
    assert hidden_ignored.is_ignored(".hidden", ".hidden", is_dir=False) is True

    hidden_kept = main._build_matcher(ignore_hidden=False)
    assert hidden_kept.is_ignored(".hidden", ".hidden", is_dir=False) is False
    # defaults (node_modules etc.) still apply regardless of ignore_hidden
    assert hidden_kept.is_ignored("node_modules", "node_modules", is_dir=True) is True


def test_preferences_update_event_updates_max_results(tmp_path, monkeypatch):
    extension = _make_extension(tmp_path, monkeypatch)
    event = stub.PreferencesUpdateEvent("max_results", "3")

    main.PreferencesUpdateEventListener().on_event(event, extension)

    assert extension.max_results == 3
