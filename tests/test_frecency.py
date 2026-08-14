import time as time_module

from lib.frecency import HALF_LIFE_SECONDS, Frecency
from lib.store import Store


def test_boost_is_zero_for_unknown_path(tmp_path):
    with Store(tmp_path / "index.db") as store:
        frecency = Frecency(store)
        assert frecency.boost("/home/u/never_opened.txt") == 0.0


def test_repeated_recent_opens_outrank_one_off_old_open(tmp_path, monkeypatch):
    real_time = time_module.time
    with Store(tmp_path / "index.db") as store:
        frecency = Frecency(store)

        old_time = real_time() - HALF_LIFE_SECONDS * 10
        monkeypatch.setattr("lib.store.time.time", lambda: old_time)
        frecency.record_open("/home/u/old_once.txt")

        monkeypatch.setattr("lib.store.time.time", real_time)
        for _ in range(5):
            frecency.record_open("/home/u/recent_often.txt")

        recent_boost = frecency.boost("/home/u/recent_often.txt")
        old_boost = frecency.boost("/home/u/old_once.txt")
        assert recent_boost > old_boost
        assert old_boost > 0.0  # decayed, but not zero


def test_top_orders_by_decayed_score(tmp_path, monkeypatch):
    real_time = time_module.time
    with Store(tmp_path / "index.db") as store:
        frecency = Frecency(store)

        old_time = real_time() - HALF_LIFE_SECONDS * 10
        monkeypatch.setattr("lib.store.time.time", lambda: old_time)
        for _ in range(20):
            frecency.record_open("/home/u/old_but_frequent.txt")

        monkeypatch.setattr("lib.store.time.time", real_time)
        frecency.record_open("/home/u/recent_once.txt")

        assert frecency.top(limit=2)[0] == "/home/u/recent_once.txt"


def test_boost_stays_below_matcher_tier_gap(tmp_path):
    with Store(tmp_path / "index.db") as store:
        frecency = Frecency(store)
        for _ in range(10000):
            frecency.record_open("/home/u/opened_a_lot.txt")
        # matcher.py's ranking tiers are 1000 points apart; frecency must
        # never be able to flip that ordering on its own.
        assert frecency.boost("/home/u/opened_a_lot.txt") < 1000.0
