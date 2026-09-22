"""Vendor Natural Earth country outlines into data/.

Run once from the repo root:  python3 tools/fetch_data.py
Re-run only to move the pinned commit.
"""
import json
import urllib.request
from pathlib import Path

COMMIT = "ca96624a56bd078437bca8184e78163e5039ad19"
BASE = f"https://raw.githubusercontent.com/nvkelso/natural-earth-vector/{COMMIT}/geojson"
LAYERS = {"110m": "ne_110m_admin_0_countries", "50m": "ne_50m_admin_0_countries"}
DATA = Path(__file__).resolve().parent.parent / "data"


def rings_of(geometry):
    polys = [geometry["coordinates"]] if geometry["type"] == "Polygon" else geometry["coordinates"]
    return [ring for poly in polys for ring in poly]


def trim(feature):
    p = feature["properties"]
    iso = p.get("ISO_A2_EH") or p.get("ISO_A2") or ""
    return {
        "n": p["NAME"],
        "iso": "" if iso == "-99" else iso,
        "rings": [[[round(x, 3), round(y, 3)] for x, y in r] for r in rings_of(feature["geometry"])],
    }


def main():
    DATA.mkdir(exist_ok=True)
    for key, layer in LAYERS.items():
        url = f"{BASE}/{layer}.geojson"
        print(f"fetching {url}")
        with urllib.request.urlopen(url, timeout=180) as r:
            src = json.load(r)
        out = {
            "source": f"nvkelso/natural-earth-vector@{COMMIT}",
            "layer": layer,
            "features": [trim(f) for f in src["features"]],
        }
        path = DATA / f"countries-{key}.json"
        path.write_text(json.dumps(out, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
        print(f"  wrote {path.name}: {path.stat().st_size:,} bytes, {len(out['features'])} features")


if __name__ == "__main__":
    main()
