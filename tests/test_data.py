import json
from pathlib import Path

DATA = Path(__file__).resolve().parent.parent / "data"


def test_israel_is_present_with_its_iso_code_and_geometry():
    d = json.loads((DATA / "countries-50m.json").read_text(encoding="utf-8"))
    israel = [f for f in d["features"] if f["n"] == "Israel"]
    assert len(israel) == 1
    assert israel[0]["iso"] == "IL"
    assert len(israel[0]["rings"][0]) > 10


def test_iso_placeholder_is_replaced_by_the_real_code():
    # Natural Earth stores ISO_A2 as "-99" for France; ISO_A2_EH has "FR".
    d = json.loads((DATA / "countries-110m.json").read_text(encoding="utf-8"))
    france = [f for f in d["features"] if f["n"] == "France"][0]
    assert france["iso"] == "FR"


def test_palestine_is_present_at_50m():
    d = json.loads((DATA / "countries-50m.json").read_text(encoding="utf-8"))
    assert any(f["n"] == "Palestine" and f["iso"] == "PS" for f in d["features"])


def test_the_pinned_source_commit_is_recorded():
    d = json.loads((DATA / "countries-110m.json").read_text(encoding="utf-8"))
    assert d["source"].endswith("@ca96624a56bd078437bca8184e78163e5039ad19")


def test_interior_rings_are_kept():
    # South Africa's Lesotho enclave is a hole in its exterior ring. Dropping it
    # would make a point in Lesotho test as inside South Africa.
    d = json.loads((DATA / "countries-110m.json").read_text(encoding="utf-8"))
    za = [f for f in d["features"] if f["n"] == "South Africa"][0]
    assert len(za["rings"]) >= 2
