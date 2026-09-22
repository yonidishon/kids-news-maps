import json
import math
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from tools.genmap import CheckFailed, SpecError, render

CACHED = {
    "ירושלים": {"lon": 35.2137, "lat": 31.7683, "cc": "il", "osm_id": 1,
                "type": "city", "display_name": "ירושלים", "resolved": "2026-09-21"},
    "באר שבע": {"lon": 34.7925, "lat": 31.2457, "cc": "il", "osm_id": 2,
                "type": "city", "display_name": "באר שבע", "resolved": "2026-09-21"},
    "צנעא": {"lon": 44.1910, "lat": 15.3547, "cc": "ye", "osm_id": 3,
             "type": "city", "display_name": "צנעא", "resolved": "2026-09-21"},
}


def explode(name):
    raise AssertionError(f"network was called for {name!r}")


def spec(**over):
    base = {
        "title": "מפת ישראל",
        "size": [340, 520],
        "extent": [33.9, 36.3, 29.3, 33.5],
        "base": "50m",
        "highlight": ["Israel"],
        "markers": [{"place": "ירושלים"}, {"place": "באר שבע"}],
    }
    base.update(over)
    return base


def test_a_valid_spec_renders_both_markers():
    svg, defs, warnings = render(spec(), dict(CACHED), fetch=explode)
    assert svg.startswith("<svg")
    assert 'class="map portrait"' in svg  # taller than wide
    assert "ירושלים" in svg and "באר שבע" in svg
    assert defs is None
    assert warnings == []


def test_a_marker_outside_the_extent_fails_the_render():
    s = spec(markers=[{"place": "ירושלים"}, {"place": "צנעא"}])
    with pytest.raises(CheckFailed) as e:
        render(s, dict(CACHED), fetch=explode)
    assert any("frame" in line for line in e.value.failures)


def test_raw_coordinates_without_provenance_are_refused():
    s = spec(markers=[{"lon": 35.0, "lat": 31.5, "label": "מקום"}])
    with pytest.raises(SpecError):
        render(s, dict(CACHED), fetch=explode)


def test_raw_coordinates_with_provenance_render_and_warn():
    s = spec(markers=[{"lon": 35.0, "lat": 31.5, "label": "גבעה",
                       "unverified": "checked by hand 2026-09-21"}])
    svg, _defs, warnings = render(s, dict(CACHED), fetch=explode)
    assert "גבעה" in svg
    assert len(warnings) == 1
    assert "checked by hand" in warnings[0]


def test_an_unresolvable_marker_is_dropped_with_a_warning():
    s = spec(markers=[{"place": "ירושלים"}, {"place": "מקום שאינו קיים"}])
    svg, _defs, warnings = render(s, dict(CACHED), fetch=lambda n: [])
    assert "ירושלים" in svg
    assert any("מקום שאינו קיים" in w for w in warnings)


def test_a_world_map_uses_the_shared_defs():
    s = spec(base="world", size=[720, 340], title="מפת העולם",
             highlight=["Yemen"], markers=[{"place": "צנעא"}])
    svg, defs, _warnings = render(s, dict(CACHED), fetch=explode)
    assert '<use class="land" href="#wd-720x340"' in svg
    assert 'xlink:href="#wd-720x340"' in svg
    assert defs is not None and 'id="wd-720x340"' in defs


def test_a_marker_resolved_without_a_country_warns_untested():
    # Nominatim returns no country_code for open-water features, which the
    # allowlist admits (e.g. "sea"). Containment can't test it, so render must
    # say so instead of rendering clean with zero warnings.
    def fetch(name):
        return [{"osm_id": 42, "lat": "32.0", "lon": "34.5",
                 "category": "natural", "type": "sea", "addresstype": "sea",
                 "display_name": "מקום ימי", "address": {}}]

    s = spec(markers=[{"place": "ירושלים"}, {"place": "ים פתוח"}])
    svg, _defs, warnings = render(s, dict(CACHED), fetch=fetch)
    assert "ים פתוח" in svg
    assert any("UNTESTED" in w and "ים פתוח" in w for w in warnings)


def test_a_world_map_marking_a_small_state_renders():
    # Singapore is absent from the 110m dataset a world map draws from, so
    # containment must check it against 50m instead, or this fails for lack of
    # a boundary to test against, not for being wrong.
    def fetch(name):
        return [{"osm_id": 7, "lat": "1.3521", "lon": "103.8198",
                 "category": "place", "type": "city", "addresstype": "city",
                 "display_name": "סינגפור", "address": {"country_code": "sg"}}]

    s = spec(base="world", size=[720, 340], title="מפת העולם",
             highlight=["Singapore"], markers=[{"place": "סינגפור"}])
    svg, _defs, _warnings = render(s, dict(CACHED), fetch=fetch)
    assert "סינגפור" in svg


def test_a_coarse_only_hit_resolves_and_warns():
    # No city-scale hit exists for this fetch, only an oblast, so pick() falls
    # back to it - and render must warn that its centre can be far off.
    def fetch(name):
        return [{"osm_id": 1, "lat": "55.7522", "lon": "37.6156",
                 "category": "boundary", "type": "administrative",
                 "addresstype": "state", "display_name": "Moscow Oblast, רוסיה",
                 "address": {"country_code": "ru"}}]

    s = spec(extent=[35.0, 40.0, 54.0, 57.0], highlight=["Russia"],
              markers=[{"place": "מוסקבה"}])
    svg, _defs, warnings = render(s, dict(CACHED), fetch=fetch)
    assert "מוסקבה" in svg
    assert any(w.startswith("COARSE:") and "מוסקבה" in w for w in warnings)


def test_a_label_and_title_with_a_literal_quote_produce_well_formed_xml():
    # Hebrew acronyms carry a literal double quote (ארה"ב, צה"ל, בי"ס). Raw
    # interpolation into an attribute or text node breaks the markup.
    import xml.etree.ElementTree as ET

    s = spec(title='מפת ארה"ב', markers=[{"place": "ירושלים", "label": 'ארה"ב'}])
    svg, _defs, _warnings = render(s, dict(CACHED), fetch=explode)
    root = ET.fromstring(svg)  # raises if the XML is malformed
    assert root.attrib["aria-label"] == 'מפת ארה"ב'
    texts = [el.text for el in root.iter() if el.tag.endswith("}text")]
    assert 'ארה"ב' in texts


def test_a_failed_check_still_persists_what_resolved(tmp_path, monkeypatch):
    # Resolution is valid even when the map is rejected; re-querying Nominatim
    # on every failing run would break the cache's one-query-per-name promise.
    import tools.genmap as genmap
    import tools.places as places

    cache_file = tmp_path / "places.json"
    cache_file.write_text("{}", encoding="utf-8")
    monkeypatch.setattr(places, "CACHE", cache_file)
    # load_cache/save_cache default to path=CACHE, bound at import time, so
    # patching the module attribute above does not reach genmap.main()'s
    # no-argument calls. Patch the bound defaults too, or this test silently
    # reads/writes the real committed data/places.json instead of cache_file.
    monkeypatch.setattr(places.load_cache, "__defaults__", (cache_file,))
    monkeypatch.setattr(places.save_cache, "__defaults__", (cache_file,))

    hit = {"osm_id": 99, "lat": "31.2457", "lon": "34.7925",
           "category": "place", "type": "city", "addresstype": "city",
           "display_name": "באר שבע", "address": {"country_code": "il"}}
    monkeypatch.setattr(places, "nominatim", lambda name: [hit])

    spec_file = tmp_path / "spec.json"
    spec_file.write_text(json.dumps({
        "title": "בדיקה", "size": [340, 520], "extent": [33.9, 36.3, 29.3, 33.5],
        "base": "50m", "highlight": ["Israel"],
        "markers": [{"place": "אלף"}, {"place": "בית"}],
    }, ensure_ascii=False), encoding="utf-8")

    rc = genmap.main([str(spec_file), "--out", str(tmp_path / "out.svg")])
    assert rc == 1, "two markers at the same point must fail the spacing check"
    assert not (tmp_path / "out.svg").exists(), "no SVG on a failed check"
    saved = json.loads(cache_file.read_text(encoding="utf-8"))
    assert set(saved) == {"אלף", "בית"}, "resolved names must survive the failure"


def test_a_label_may_not_sit_on_its_own_marker():
    # Hebrew is RTL, where text-anchor start/end flip and run the label back
    # over its dot; the label's halo then erases the dot. תל אביב lost its
    # marker this way on the 19 September map.
    s = spec(markers=[{"place": "ירושלים", "dx": 8, "dy": 4}])
    with pytest.raises(CheckFailed) as excinfo:
        render(s, dict(CACHED), fetch=explode)
    assert any("erase the dot" in line for line in excinfo.value.failures)


def test_an_anchor_in_a_spec_is_refused():
    s = spec(markers=[{"place": "ירושלים", "anchor": "start"}])
    with pytest.raises(SpecError):
        render(s, dict(CACHED), fetch=explode)


def test_labels_are_always_centred():
    svg, _defs, _w = render(spec(), dict(CACHED), fetch=explode)
    assert 'text-anchor="middle"' in svg
    assert 'text-anchor="start"' not in svg and 'text-anchor="end"' not in svg


def test_the_world_defs_id_carries_its_viewbox():
    # A <use> must only ever reach a path projected for its own canvas.
    s = spec(base="world", size=[480, 220], title="מפת העולם",
             highlight=["Yemen"], markers=[{"place": "צנעא"}])
    svg, defs, _w = render(s, dict(CACHED), fetch=explode)
    assert 'id="wd-480x220"' in defs
    assert 'href="#wd-480x220"' in svg


def test_auto_extent_frames_the_markers_and_israel():
    from tools.genmap import auto_extent, load_countries
    countries = load_countries("50m")
    # Madrid alone, on a wide canvas: the window must still contain Israel.
    lo0, lo1, la0, la1 = auto_extent([(-3.7038, 40.4168)], 480, 220, countries)
    assert lo0 <= -3.7038 <= lo1 and la0 <= 40.4168 <= la1
    assert lo0 <= 34.8 <= lo1 and la0 <= 31.5 <= la1, "Israel must stay in frame"
    # and the window is shaped to the canvas, so the map is not letterboxed
    k = math.cos(math.radians((la0 + la1) / 2))
    assert abs(((lo1 - lo0) * k) / (la1 - la0) - 480 / 220) < 0.01
