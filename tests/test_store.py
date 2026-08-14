from lib.index import Entry, FileIndex
from lib.store import Store


def _entry(path: str, is_dir: bool = False, mtime: float = 123.0) -> Entry:
    name = path.rsplit("/", 1)[-1]
    return Entry(
        path=path,
        name=name,
        name_lower=name.lower(),
        dir=path.rsplit("/", 1)[0],
        is_dir=is_dir,
        mtime=mtime,
    )


def test_save_and_load_index_round_trip(tmp_path):
    index = FileIndex.from_entries(
        [
            _entry("/home/u/a.txt"),
            _entry("/home/u/sub", is_dir=True),
            _entry("/home/u/sub/b.txt"),
        ]
    )

    with Store(tmp_path / "index.db") as store:
        store.save_index(index)

    with Store(tmp_path / "index.db") as store:
        loaded = store.load_index()

    original = {e.path: e for e in index.entries()}
    reloaded = {e.path: e for e in loaded.entries()}
    assert original.keys() == reloaded.keys()
    for path, entry in original.items():
        assert reloaded[path] == entry
    assert "/home/u/sub" in loaded.directories()


def test_upsert_and_delete_file(tmp_path):
    with Store(tmp_path / "index.db") as store:
        store.upsert_file(_entry("/home/u/new.txt"))
        loaded = store.load_index()
        assert loaded.get("/home/u/new.txt") is not None

        store.delete_file("/home/u/new.txt")
        loaded = store.load_index()
        assert loaded.get("/home/u/new.txt") is None


def test_delete_file_purges_directory_descendants(tmp_path):
    with Store(tmp_path / "index.db") as store:
        store.upsert_file(_entry("/home/u/sub", is_dir=True))
        store.upsert_file(_entry("/home/u/sub/child.txt"))

        store.delete_file("/home/u/sub")
        loaded = store.load_index()
        assert loaded.get("/home/u/sub") is None
        assert loaded.get("/home/u/sub/child.txt") is None


def test_upsert_file_overwrites_existing_row(tmp_path):
    with Store(tmp_path / "index.db") as store:
        store.upsert_file(_entry("/home/u/a.txt", mtime=1.0))
        store.upsert_file(_entry("/home/u/a.txt", mtime=2.0))
        loaded = store.load_index()
        assert loaded.get("/home/u/a.txt").mtime == 2.0


def test_frecency_bump_and_top(tmp_path):
    with Store(tmp_path / "index.db") as store:
        assert store.get_frecency("/home/u/a.txt") is None

        store.bump_frecency("/home/u/a.txt")
        store.bump_frecency("/home/u/a.txt")
        store.bump_frecency("/home/u/b.txt")

        score_a, _ = store.get_frecency("/home/u/a.txt")
        score_b, _ = store.get_frecency("/home/u/b.txt")
        assert score_a == 2.0
        assert score_b == 1.0

        assert store.top_frecent(limit=1) == ["/home/u/a.txt"]
        assert store.top_frecent(limit=2) == ["/home/u/a.txt", "/home/u/b.txt"]
