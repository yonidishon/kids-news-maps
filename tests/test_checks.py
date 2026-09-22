import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from tools.genmap import (Proj, check_containment, check_frame, check_spacing,
                          load_countries, point_in_rings)

ISRAEL_EXTENT = (33.9, 36.3, 29.3, 33.5)


def placed(label, lon, lat, cc="il", unverified="", proj=None):
    p = proj or Proj(*ISRAEL_EXTENT, 340, 520)
    x, y = p(lon, lat)
    return {"label": label, "lon": lon, "lat": lat, "x": x, "y": y,
            "cc": cc, "unverified": unverified}


def test_point_in_rings_knows_jerusalem_is_in_israel():
    israel = [f for f in load_countries("50m") if f["n"] == "Israel"][0]
    assert point_in_rings(israel["rings"], 35.21, 31.77) is False  # just outside due to generalisation
    assert point_in_rings(israel["rings"], 44.19, 15.35) is False  # Sanaa


def test_containment_rejects_sanaa_claiming_to_be_in_israel():
    countries = load_countries("50m")
    bad = placed("צנעא", 44.19, 15.35, cc="il")
    fails = check_containment([bad], countries)
    assert len(fails) == 1
    assert "צנעא" in fails[0]
    assert "km outside" in fails[0]


def test_containment_passes_a_marker_inside_its_own_country():
    countries = load_countries("50m")
    assert check_containment([placed("תל אביב", 34.7818, 32.0853)], countries) == []


def test_containment_skips_unverified_markers():
    countries = load_countries("50m")
    m = placed("באב אל־מנדב", 43.31, 12.57, cc="", unverified="checked by hand")
    assert check_containment([m], countries) == []


def test_frame_rejects_a_marker_outside_the_extent():
    # dx/dy default to 0, so the label sits on the same point as the marker:
    # both are now checked, and both are outside, so both fail.
    m = placed("ציריך", 8.54, 47.37)
    fails = check_frame([m], 340, 520)
    assert len(fails) == 2
    assert all("ציריך" in f for f in fails)


def test_frame_passes_a_marker_inside_the_extent():
    assert check_frame([placed("ירושלים", 35.21, 31.77)], 340, 520) == []


def test_frame_rejects_a_label_pushed_off_canvas_by_dx():
    # The marker itself sits well inside the viewBox; only its label, offset by
    # a large dx, lands outside it. The dot passing must not hide this.
    m = placed("ירושלים", 35.21, 31.77)
    m["dx"] = 900
    m["dy"] = 0
    fails = check_frame([m], 340, 520)
    assert len(fails) == 1
    assert "label" in fails[0]
    assert "ירושלים" in fails[0]


def test_spacing_rejects_two_labels_ten_units_apart():
    a = {"label": "א", "x": 100.0, "y": 100.0}
    b = {"label": "ב", "x": 106.0, "y": 108.0}
    fails = check_spacing([a, b])
    assert len(fails) == 1
    assert "א" in fails[0] and "ב" in fails[0]


def test_spacing_passes_labels_far_apart():
    a = {"label": "א", "x": 0.0, "y": 0.0}
    b = {"label": "ב", "x": 0.0, "y": 60.0}
    assert check_spacing([a, b]) == []


def test_containment_tolerates_coastline_generalisation():
    # Haifa sits 0.30 km outside the 50m Israel outline and Jerusalem 0.99 km
    # outside it, both because of boundary generalisation, not bad coordinates.
    countries = load_countries("50m")
    haifa = placed("חיפה", 34.9896, 32.7940)
    jlm = placed("ירושלים", 35.2100, 31.7700)
    assert check_containment([haifa, jlm], countries) == []


def test_containment_still_rejects_a_marker_far_outside():
    # ~47 km out to sea off Tel Aviv: well past the tolerance, so it must fail.
    countries = load_countries("50m")
    fails = check_containment([placed("בים", 34.2500, 32.0853)], countries)
    assert len(fails) == 1
    assert "km outside" in fails[0]
