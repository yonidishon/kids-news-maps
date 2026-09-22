import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from tools.inject import HeadlineNotFound, inject

CACHED = {
    "ירושלים": {"lon": 35.2137, "lat": 31.7683, "cc": "il", "osm_id": 1,
                "type": "city", "display_name": "ירושלים", "resolved": "2026-09-21"},
    "באר שבע": {"lon": 34.7925, "lat": 31.2457, "cc": "il", "osm_id": 2,
                "type": "city", "display_name": "באר שבע", "resolved": "2026-09-21"},
    "צנעא": {"lon": 44.1910, "lat": 15.3547, "cc": "ye", "osm_id": 3,
             "type": "city", "display_name": "צנעא", "resolved": "2026-09-21"},
}

PAGE = """<div class="wrap" dir="rtl" lang="he">
<article class="story">
<h2>כותרת ראשונה</h2>
<div class="body"><p>גוף</p></div>
<div class="kids"><p class="tag">לילדים</p><p>סיפור</p></div>
<div class="talk"><p class="tag">לשיחה</p></div>
</article>
<article class="story">
<h2>כותרת שנייה</h2>
<div class="kids"><p class="tag">לילדים</p><p>סיפור</p></div>
<div class="talk"><p class="tag">לשיחה</p></div>
</article>
</div>"""


def explode(name):
    raise AssertionError(f"network was called for {name!r}")


def israel_spec():
    return {"title": "מפת ישראל", "size": [340, 520],
            "extent": [33.9, 36.3, 29.3, 33.5], "base": "50m",
            "highlight": ["Israel"],
            "markers": [{"place": "ירושלים"}, {"place": "באר שבע"}]}


def world_spec():
    return {"title": "מפת העולם", "size": [720, 340], "base": "world",
            "extent": [-170, 180, -56, 80], "highlight": ["Yemen"],
            "markers": [{"place": "צנעא"}]}


def test_the_figure_lands_between_kids_and_talk():
    out, _ = inject(PAGE, [{"headline": "כותרת ראשונה", "caption": "ירושלים ובאר שבע.",
                            "map": israel_spec()}], dict(CACHED), explode)
    kids = out.index('<div class="kids">')
    geo = out.index('<figure class="geo">')
    talk = out.index('<div class="talk">')
    assert kids < geo < talk
    assert "ירושלים ובאר שבע." in out


def test_stories_without_an_entry_are_untouched():
    out, _ = inject(PAGE, [{"headline": "כותרת ראשונה", "caption": "כיתוב",
                            "map": israel_spec()}], dict(CACHED), explode)
    second = out[out.index("כותרת שנייה"):]
    assert '<figure class="geo">' not in second


def test_an_unknown_headline_is_an_error():
    with pytest.raises(HeadlineNotFound):
        inject(PAGE, [{"headline": "כותרת שאינה קיימת", "caption": "כיתוב",
                       "map": israel_spec()}], dict(CACHED), explode)


def test_two_world_maps_share_one_defs():
    entries = [{"headline": "כותרת ראשונה", "caption": "א", "map": world_spec()},
               {"headline": "כותרת שנייה", "caption": "ב", "map": world_spec()}]
    out, _ = inject(PAGE, entries, dict(CACHED), explode)
    assert out.count('<svg class="mapdefs"') == 1
    assert out.count('<use class="land"') == 2
    assert out.index('class="mapdefs"') < out.index('<article')


def test_an_existing_geo_block_is_kept_without_replace():
    page = PAGE.replace('<div class="talk">',
                        '<figure class="geo">ישן</figure>\n<div class="talk">', 1)
    out, _ = inject(page, [{"headline": "כותרת ראשונה", "caption": "חדש",
                            "map": israel_spec()}], dict(CACHED), explode)
    assert "ישן" in out
    assert "חדש" not in out


def test_a_headline_inside_malformed_markup_reports_the_real_problem():
    # Story one loses its closing tag, so the non-greedy story pattern swallows
    # story two's closer and merges them. The headline is still on the page, and
    # the error has to say so rather than blaming the headline.
    broken = PAGE.replace("</article>", "", 1)
    with pytest.raises(HeadlineNotFound) as excinfo:
        inject(broken, [{"headline": "כותרת שנייה", "caption": "כיתוב",
                         "map": israel_spec()}], dict(CACHED), explode)
    assert "well-formed" in str(excinfo.value)


def test_replace_swaps_an_existing_geo_block():
    page = PAGE.replace('<div class="talk">',
                        '<figure class="geo">ישן</figure>\n<div class="talk">', 1)
    out, _ = inject(page, [{"headline": "כותרת ראשונה", "caption": "חדש",
                            "map": israel_spec()}], dict(CACHED), explode, replace=True)
    assert "ישן" not in out
    assert "חדש" in out


def test_a_failed_inject_run_still_persists_what_resolved(tmp_path, monkeypatch):
    # Identical bug class to genmap.main: a CheckFailed render must not discard
    # names Nominatim just resolved, or the next run re-queries them.
    import tools.inject as inject_mod
    import tools.places as places

    cache_file = tmp_path / "places.json"
    cache_file.write_text("{}", encoding="utf-8")
    monkeypatch.setattr(places, "CACHE", cache_file)
    # load_cache/save_cache default to path=CACHE, bound at import time, so
    # patching the module attribute above does not reach inject.main()'s
    # no-argument calls. Patch the bound defaults too.
    monkeypatch.setattr(places.load_cache, "__defaults__", (cache_file,))
    monkeypatch.setattr(places.save_cache, "__defaults__", (cache_file,))

    hit = {"osm_id": 99, "lat": "31.2457", "lon": "34.7925",
           "category": "place", "type": "city", "addresstype": "city",
           "display_name": "באר שבע", "address": {"country_code": "il"}}
    monkeypatch.setattr(places, "nominatim", lambda name: [hit])

    page_file = tmp_path / "page.html"
    page_file.write_text(PAGE, encoding="utf-8")

    entries_file = tmp_path / "entries.json"
    entries_file.write_text(json.dumps([{
        "headline": "כותרת ראשונה", "caption": "כיתוב",
        "map": {"title": "בדיקה", "size": [340, 520],
                "extent": [33.9, 36.3, 29.3, 33.5], "base": "50m",
                "highlight": ["Israel"],
                "markers": [{"place": "אלף"}, {"place": "בית"}]},
    }], ensure_ascii=False), encoding="utf-8")

    rc = inject_mod.main(["--page", str(page_file), "--entries", str(entries_file),
                          "--out", str(tmp_path / "out.html")])
    assert rc == 1, "two markers at the same point must fail the spacing check"
    assert not (tmp_path / "out.html").exists(), "no page written on a failed check"
    saved = json.loads(cache_file.read_text(encoding="utf-8"))
    assert set(saved) == {"אלף", "בית"}, "resolved names must survive the failure"


def test_an_incompatible_existing_defs_does_not_suppress_the_right_one():
    # The page already carries a world path built for a 720x340 canvas. A new
    # 480x220 map must bring its own: reusing the old one drew the coastline at
    # one scale and the markers at another, which put Madrid on Greenland.
    page = PAGE.replace(
        '<div class="wrap" dir="rtl" lang="he">',
        '<div class="wrap" dir="rtl" lang="he">\n'
        '<svg class="mapdefs"><defs><path id="wd-720x340" d="M0 0L1 1Z"/></defs></svg>',
        1)
    small = dict(world_spec(), size=[480, 220])
    out, _ = inject(page, [{"headline": "כותרת ראשונה", "caption": "כיתוב",
                            "map": small}], dict(CACHED), explode)
    assert 'id="wd-480x220"' in out, "the correctly scaled defs must be inserted"
    assert 'id="wd-720x340"' in out, "the existing one must survive"
    assert 'href="#wd-480x220"' in out
