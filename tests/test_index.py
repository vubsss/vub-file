import os

from lib.ignore import IgnoreMatcher, parse_rules
from lib.index import FileIndex


def _build_tree(tmp_path):
    (tmp_path / "a.txt").write_text("a")
    sub = tmp_path / "sub"
    sub.mkdir()
    (sub / "b.txt").write_text("b")
    nm = tmp_path / "node_modules"
    nm.mkdir()
    (nm / "should_not_appear.txt").write_text("x")
    deep = nm / "deep"
    deep.mkdir()
    (deep / "also_not_appear.txt").write_text("y")
    return tmp_path


def test_build_indexes_files_and_dirs(tmp_path):
    _build_tree(tmp_path)
    index = FileIndex.build([str(tmp_path)])

    paths = {e.path for e in index.entries()}
    assert str(tmp_path / "a.txt") in paths
    assert str(tmp_path / "sub") in paths
    assert str(tmp_path / "sub" / "b.txt") in paths


def test_ignored_subtree_is_never_descended_into(tmp_path, monkeypatch):
    _build_tree(tmp_path)

    real_scandir = os.scandir
    scanned_dirs = []

    def spy_scandir(path):
        scanned_dirs.append(str(path))
        return real_scandir(path)

    monkeypatch.setattr(os, "scandir", spy_scandir)

    index = FileIndex.build([str(tmp_path)])

    node_modules = str(tmp_path / "node_modules")
    assert node_modules not in scanned_dirs
    assert not any(p.startswith(node_modules) for p in scanned_dirs)

    paths = {e.path for e in index.entries()}
    assert not any("node_modules" in p for p in paths)
    assert node_modules not in index.directories()


def test_entry_shape(tmp_path):
    _build_tree(tmp_path)
    index = FileIndex.build([str(tmp_path)])

    entry = index.get(str(tmp_path / "a.txt"))
    assert entry is not None
    assert entry.name == "a.txt"
    assert entry.name_lower == "a.txt"
    assert entry.dir == str(tmp_path)
    assert entry.is_dir is False
    assert entry.mtime > 0

    dir_entry = index.get(str(tmp_path / "sub"))
    assert dir_entry is not None
    assert dir_entry.is_dir is True


def test_custom_ignore_matcher_is_respected(tmp_path):
    _build_tree(tmp_path)
    (tmp_path / "ignored_by_rule.tmp").write_text("z")
    matcher = IgnoreMatcher(rules=parse_rules(["*.tmp"]))
    index = FileIndex.build([str(tmp_path)], matcher=matcher)
    paths = {e.path for e in index.entries()}
    assert str(tmp_path / "ignored_by_rule.tmp") not in paths
    # node_modules isn't ignored by this custom matcher (it has no defaults)
    assert str(tmp_path / "node_modules") in paths


def test_add_or_update_and_remove(tmp_path):
    _build_tree(tmp_path)
    index = FileIndex.build([str(tmp_path)])

    new_file = tmp_path / "new.txt"
    new_file.write_text("new")
    entry = index.add_or_update(str(new_file))
    assert entry is not None
    assert index.get(str(new_file)) is not None

    os.remove(new_file)
    index.remove(str(new_file))
    assert index.get(str(new_file)) is None


def test_remove_directory_purges_descendants(tmp_path):
    _build_tree(tmp_path)
    index = FileIndex.build([str(tmp_path)])

    sub_path = str(tmp_path / "sub")
    b_path = str(tmp_path / "sub" / "b.txt")
    assert index.get(sub_path) is not None
    assert index.get(b_path) is not None

    index.remove(sub_path)

    assert index.get(sub_path) is None
    assert index.get(b_path) is None
    assert sub_path not in index.directories()
