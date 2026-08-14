from lib.ignore import IgnoreMatcher, Rule, load_user_rules, parse_rules


def test_default_ignored_dir_names_are_ignored():
    matcher = IgnoreMatcher()
    for name in (".git", "node_modules", "__pycache__", ".venv"):
        assert matcher.is_ignored(name, name, is_dir=True) is True


def test_non_ignored_paths_pass_through():
    matcher = IgnoreMatcher()
    assert matcher.is_ignored("Documents", "Documents", is_dir=True) is False
    assert matcher.is_ignored("notes.txt", "notes.txt", is_dir=False) is False
    assert matcher.is_ignored("Documents/notes.txt", "notes.txt", is_dir=False) is False


def test_user_pattern_is_layered_on_top_of_defaults():
    rules = parse_rules(["*.log", "secrets/"])
    matcher = IgnoreMatcher(rules=rules)
    assert matcher.is_ignored("app.log", "app.log", is_dir=False) is True
    assert matcher.is_ignored("secrets", "secrets", is_dir=True) is True
    # dir_only pattern must not match a plain file of the same name
    assert matcher.is_ignored("secrets", "secrets", is_dir=False) is False


def test_negation_re_includes_a_path():
    rules = parse_rules(["*.log", "!keep.log"])
    matcher = IgnoreMatcher(rules=rules)
    assert matcher.is_ignored("debug.log", "debug.log", is_dir=False) is True
    assert matcher.is_ignored("keep.log", "keep.log", is_dir=False) is False


def test_anchored_pattern_only_matches_at_relative_root():
    rules = parse_rules(["/only_root_file.txt"])
    matcher = IgnoreMatcher(rules=rules)
    assert matcher.is_ignored("only_root_file.txt", "only_root_file.txt", is_dir=False) is True
    assert (
        matcher.is_ignored(
            "sub/only_root_file.txt", "only_root_file.txt", is_dir=False
        )
        is False
    )


def test_load_user_rules_from_file(tmp_path):
    ignore_file = tmp_path / ".vub-file-ignore"
    ignore_file.write_text("# comment\n*.tmp\n\nbuild_output/\n")
    rules = load_user_rules(ignore_file)
    assert Rule(pattern="*.tmp", negate=False, dir_only=False, anchored=False) in rules
    assert Rule(pattern="build_output", negate=False, dir_only=True, anchored=False) in rules


def test_load_user_rules_missing_file_returns_empty(tmp_path):
    assert load_user_rules(tmp_path / "does-not-exist") == []
