from lib.reveal import fallback_command, reveal_sync, target_for


def test_file_uses_show_items_so_the_file_is_selected(tmp_path):
    path = tmp_path / "notes.txt"
    path.write_text("a")

    method, uri = target_for(str(path))

    assert method == "ShowItems"
    assert uri == path.as_uri()


def test_directory_opens_itself_rather_than_being_selected_in_its_parent(tmp_path):
    method, uri = target_for(str(tmp_path))

    assert method == "ShowFolders"
    assert uri == tmp_path.as_uri()


def test_uri_escapes_awkward_characters(tmp_path):
    path = tmp_path / "my notes #1 &.txt"
    path.write_text("a")

    _, uri = target_for(str(path))

    assert " " not in uri
    assert "%20" in uri
    assert "%23" in uri


def test_fallback_opens_the_parent_of_a_file(tmp_path):
    path = tmp_path / "notes.txt"
    path.write_text("a")

    assert fallback_command(str(path)) == ["xdg-open", str(tmp_path)]


def test_fallback_opens_a_directory_itself(tmp_path):
    assert fallback_command(str(tmp_path)) == ["xdg-open", str(tmp_path)]


def test_reveal_falls_back_to_xdg_open_when_the_dbus_call_fails(tmp_path, monkeypatch):
    path = tmp_path / "notes.txt"
    path.write_text("a")
    launched = []

    def _explode(method, uri):
        raise RuntimeError("no FileManager1 on this desktop")

    monkeypatch.setattr("lib.reveal._show", _explode)
    monkeypatch.setattr("lib.reveal.subprocess.Popen", launched.append)

    reveal_sync(str(path))

    assert launched == [["xdg-open", str(tmp_path)]]


def test_reveal_survives_a_missing_xdg_open(tmp_path, monkeypatch):
    path = tmp_path / "notes.txt"
    path.write_text("a")

    def _explode(*args, **kwargs):
        raise RuntimeError("no FileManager1 on this desktop")

    def _no_xdg_open(argv):
        raise OSError(2, "No such file or directory: 'xdg-open'")

    monkeypatch.setattr("lib.reveal._show", _explode)
    monkeypatch.setattr("lib.reveal.subprocess.Popen", _no_xdg_open)

    reveal_sync(str(path))  # must not raise
