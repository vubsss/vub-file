from lib.index import Entry
from lib.matcher import search


def _entry(path: str) -> Entry:
    name = path.rsplit("/", 1)[-1]
    return Entry(
        path=path,
        name=name,
        name_lower=name.lower(),
        dir=path.rsplit("/", 1)[0],
        is_dir=False,
        mtime=0.0,
    )


def test_exact_match_beats_prefix_match():
    entries = [_entry("/home/u/test123"), _entry("/home/u/test")]
    results = search(entries, "test")
    assert [e.name for e in results] == ["test", "test123"]


def test_prefix_beats_word_boundary():
    entries = [_entry("/home/u/my_test.py"), _entry("/home/u/testing.py")]
    results = search(entries, "test")
    assert [e.name for e in results] == ["testing.py", "my_test.py"]


def test_word_boundary_beats_plain_substring():
    entries = [_entry("/home/u/retesting.py"), _entry("/home/u/my_test.py")]
    results = search(entries, "test")
    assert [e.name for e in results] == ["my_test.py", "retesting.py"]


def test_non_matching_entries_are_excluded():
    entries = [_entry("/home/u/apple.txt"), _entry("/home/u/test.txt")]
    results = search(entries, "test")
    assert [e.name for e in results] == ["test.txt"]


def test_top_k_limit_is_respected():
    entries = [_entry(f"/home/u/test{i}.txt") for i in range(20)]
    results = search(entries, "test", limit=5)
    assert len(results) == 5


def test_empty_query_returns_no_results():
    entries = [_entry("/home/u/test.txt")]
    assert search(entries, "") == []


def test_boost_function_can_reorder_same_tier_results():
    entries = [_entry("/home/u/test_a.py"), _entry("/home/u/test_b.py")]

    def boost(path: str) -> float:
        return 500.0 if path.endswith("test_b.py") else 0.0

    results = search(entries, "test", boost=boost)
    assert [e.name for e in results] == ["test_b.py", "test_a.py"]
