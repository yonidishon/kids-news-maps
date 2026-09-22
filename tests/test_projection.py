import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from tools.genmap import Proj, load_countries, simplify


def test_a_square_extent_maps_corners_and_centre():
    # 0-10 lon, 0-10 lat into a 100x100 box. cos(5 deg) compresses x to 99.619
    # units, so the scale is set by y: 10 units per degree, with x centred.
    p = Proj(0, 10, 0, 10, 100, 100)
    x, y = p(5, 5)
    assert round(x, 3) == 50.0
    assert round(y, 3) == 50.0
    x0, y0 = p(0, 10)
    assert round(x0, 2) == 0.19
    assert round(y0, 2) == 0.0
    x1, y1 = p(10, 0)
    assert round(x1, 2) == 99.81
    assert round(y1, 2) == 100.0


def test_latitude_increases_upward_on_screen():
    p = Proj(0, 10, 0, 10, 100, 100)
    assert p(5, 9)[1] < p(5, 1)[1]


def test_simplify_keeps_the_endpoints():
    pts = [[0, 0], [0.001, 0], [0.002, 0], [1, 1]]
    out = simplify(pts, 0.5)
    assert out[0] == [0, 0]
    assert out[-1] == [1, 1]
    assert len(out) == 2


def test_load_countries_finds_israel():
    feats = load_countries("50m")
    israel = [f for f in feats if f["n"] == "Israel"]
    assert len(israel) == 1
