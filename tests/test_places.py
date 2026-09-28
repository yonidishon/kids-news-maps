import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from tools.places import (country_for, default_gazetteer, index_gazetteer, pick, resolve,
                          save_cache)

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
    got = resolve("לוד", cache, fetch=lambda n: [TOWN_HIT], today="2026-09-21",
                  gazetteer={})
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


GAZ_ROWS = [
    [294117, "Lod", 34.8953, 31.9467, "il", 77223, ["לוד"]],
    [1848377, "Kobe", 135.183, 34.6913, "jp", 1525152, ["קובה"]],
    [2643743, "London", -0.1257, 51.5085, "gb", 8961989, ["לונדון"]],
    [6058560, "London", -81.2331, 42.9834, "ca", 422324, ["לונדון"]],
]


def test_a_cache_miss_found_in_the_gazetteer_makes_no_network_call():
    gaz = index_gazetteer(GAZ_ROWS)
    got = resolve("לוד", {}, fetch=explode, gazetteer=gaz)
    assert (got["lon"], got["lat"], got["cc"]) == (34.8953, 31.9467, "il")
    assert got["source"] == "geonames"
    assert got["type"] == "city"


def test_a_gazetteer_hit_is_not_written_into_the_curated_cache():
    cache = {}
    resolve("לוד", cache, fetch=explode, gazetteer=index_gazetteer(GAZ_ROWS))
    assert cache == {}


def test_the_cache_wins_over_the_gazetteer():
    cache = {"לוד": {"lon": 1.0, "lat": 2.0, "cc": "il", "type": "town"}}
    assert resolve("לוד", cache, fetch=explode,
                   gazetteer=index_gazetteer(GAZ_ROWS))["lon"] == 1.0


def test_a_shared_name_goes_to_the_most_populous_place():
    got = index_gazetteer(GAZ_ROWS)["לונדון"]
    assert got["cc"] == "gb"


def test_an_unreachable_nominatim_is_a_miss_not_a_crash():
    import urllib.error

    def offline(name):
        raise urllib.error.URLError("no network in the sandbox")

    cache = {}
    assert resolve("גבעות גומר", cache, fetch=offline, gazetteer={}) is None
    assert cache == {}


def test_the_vendored_gazetteer_resolves_the_names_that_broke_a_run():
    gaz = default_gazetteer()
    for name, cc in [("מגדל העמק", "il"), ("לוד", "il"), ("קרית שמונה", "il"),
                     ("עזה", "ps"), ("ניו יורק", "us"), ("מוסקבה", "ru"),
                     ("פאלו אלטו", "us"), ("האג", "nl")]:
        assert gaz[name]["cc"] == cc, name


def test_a_country_name_is_recognised():
    assert country_for("סוריה", gazetteer={}) == "Syria"


def test_a_city_state_is_not_treated_as_a_country():
    gaz = {"סינגפור": {"cc": "sg"}}
    assert country_for("סינגפור", gazetteer=gaz) is None


def test_a_city_is_not_a_country():
    assert country_for("לוד", gazetteer={}) is None


def test_the_contested_natural_earth_name_is_not_a_lookup_key():
    # Natural Earth gives Palestine's Hebrew name as ארץ ישראל. It is not used.
    assert country_for("ארץ ישראל", gazetteer={}) is None
