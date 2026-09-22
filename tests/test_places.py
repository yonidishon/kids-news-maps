import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from tools.places import pick, resolve, save_cache

ROAD_HIT = {
    "osm_id": 863741479, "lat": "32.1494430", "lon": "35.2678608",
    "category": "highway", "type": "trunk", "addresstype": "road",
    "display_name": "עוקף חווארה", "address": {"country_code": "ps"},
}
TOWN_HIT = {
    "osm_id": 1381532, "lat": "31.9489012", "lon": "34.8884857",
    "category": "boundary", "type": "administrative", "addresstype": "town",
    "display_name": "לוד, נפת רמלה, מחוז המרכז, ישראל", "address": {"country_code": "il"},
}
OBLAST_HIT = {
    "osm_id": 1, "lat": "55.7522", "lon": "37.6156",
    "category": "boundary", "type": "administrative", "addresstype": "state",
    "display_name": "Moscow Oblast, רוסיה", "address": {"country_code": "ru"},
}
CITY_HIT = {
    "osm_id": 2, "lat": "55.7505412", "lon": "37.6174782",
    "category": "place", "type": "city", "addresstype": "city",
    "display_name": "מוסקבה, רוסיה", "address": {"country_code": "ru"},
}


def explode(name):
    raise AssertionError(f"network was called for {name!r}")


def test_a_cached_name_makes_no_network_call():
    cache = {"לוד": {"lon": 34.8885, "lat": 31.9489, "cc": "il", "osm_id": 1381532,
                     "type": "town", "display_name": "לוד", "resolved": "2026-09-21"}}
    got = resolve("לוד", cache, fetch=explode)
    assert got["lat"] == 31.9489


def test_a_road_match_is_rejected():
    assert pick([ROAD_HIT]) is None


def test_the_first_acceptable_hit_wins():
    assert pick([ROAD_HIT, TOWN_HIT])["osm_id"] == 1381532


def test_a_fine_hit_wins_over_a_coarse_one_listed_first():
    # Moscow Oblast (state, coarse) comes back before the city itself. Its centre
    # is ~48 km from Moscow, so the fine result must win regardless of order.
    assert pick([OBLAST_HIT, CITY_HIT])["osm_id"] == 2


def test_a_coarse_only_result_still_resolves():
    assert pick([OBLAST_HIT])["osm_id"] == 1


def test_an_unresolvable_name_returns_none_and_is_not_cached():
    cache = {}
    assert resolve("מקום שאינו קיים", cache, fetch=lambda n: []) is None
    assert cache == {}


def test_a_resolved_name_is_written_into_the_cache():
    cache = {}
    got = resolve("לוד", cache, fetch=lambda n: [TOWN_HIT], today="2026-09-21")
    assert got["cc"] == "il"
    assert cache["לוד"]["osm_id"] == 1381532
    assert cache["לוד"]["resolved"] == "2026-09-21"


def test_the_cache_round_trips_through_disk(tmp_path):
    p = tmp_path / "places.json"
    save_cache({"לוד": {"lon": 1.0, "lat": 2.0}}, p)
    assert json.loads(p.read_text(encoding="utf-8"))["לוד"]["lon"] == 1.0


def test_consecutive_queries_are_spaced_by_the_rate_limit(monkeypatch):
    # The 1.2 s gap is an obligation to Nominatim, a free service. Fake the clock
    # and the socket so this proves the spacing without touching the network.
    import tools.places as places

    slept = []
    now = {"t": 1000.0}
    monkeypatch.setattr(places.time, "monotonic", lambda: now["t"])
    monkeypatch.setattr(places.time, "sleep", lambda s: slept.append(s))
    monkeypatch.setattr(places, "_last_call", 0.0)

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def read(self):
            return b"[]"

    monkeypatch.setattr(places.urllib.request, "urlopen",
                        lambda req, timeout=None: FakeResponse())

    places.nominatim("ראשון")
    assert slept == [], "the first call should not wait"

    places.nominatim("שני")
    assert len(slept) == 1, "the second call should wait"
    assert slept[0] >= 1.0, f"expected roughly 1.2 s, got {slept[0]}"
