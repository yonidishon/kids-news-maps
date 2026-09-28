"""Vendor Natural Earth country outlines and names, and the GeoNames gazetteer, into data/.

Run once from the repo root:  python3 tools/fetch_data.py
Re-run only to move the pinned commit.
"""
import io
import json
import re
import urllib.request
import zipfile
from pathlib import Path

COMMIT = "ca96624a56bd078437bca8184e78163e5039ad19"
BASE = f"https://raw.githubusercontent.com/nvkelso/natural-earth-vector/{COMMIT}/geojson"
LAYERS = {"110m": "ne_110m_admin_0_countries", "50m": "ne_50m_admin_0_countries"}
GEONAMES = "https://download.geonames.org/export/dump/cities15000.zip"
HEBREW = re.compile("[\u0590-\u05ff]")
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


# Natural Earth's Hebrew name for Palestine. Never a lookup key: a marker using it
# would shade a territory under a name that takes a side.
CONTESTED_HE = {"ארץ ישראל"}


def fetch_country_names():
    """Hebrew country name -> Natural Earth English name, for lookup only.
    The Hebrew names are never rendered."""
    url = f"{BASE}/{LAYERS['50m']}.geojson"
    print(f"fetching {url}")
    with urllib.request.urlopen(url, timeout=180) as r:
        src = json.load(r)
    names = {}
    for f in src["features"]:
        p = f["properties"]
        he = p.get("NAME_HE")
        if he and he not in CONTESTED_HE:
            iso = p.get("ISO_A2_EH") or p.get("ISO_A2") or ""
            names[he] = {"n": p["NAME"], "iso": "" if iso == "-99" else iso}
    out = {"source": f"nvkelso/natural-earth-vector@{COMMIT}", "names": names}
    path = DATA / "countries-he.json"
    path.write_text(json.dumps(out, ensure_ascii=False, indent=0, sort_keys=True), encoding="utf-8")
    print(f"  wrote {path.name}: {path.stat().st_size:,} bytes, {len(names)} names")


def fetch_gazetteer():
    """Keep only places with a Hebrew name: the resolver looks up nothing else."""
    print(f"fetching {GEONAMES}")
    with urllib.request.urlopen(GEONAMES, timeout=180) as r:
        text = zipfile.ZipFile(io.BytesIO(r.read())).read("cities15000.txt").decode("utf-8")
    rows = []
    for line in text.splitlines():
        f = line.split("\t")
        he = [a for a in f[3].split(",") if HEBREW.search(a)]
        if he:
            rows.append([int(f[0]), f[1], round(float(f[5]), 4), round(float(f[4]), 4),
                         f[8].lower(), int(f[14] or 0), he])
    out = {"source": "GeoNames cities15000, CC BY 4.0, geonames.org", "places": rows}
    path = DATA / "cities15000-he.json"
    path.write_text(json.dumps(out, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"  wrote {path.name}: {path.stat().st_size:,} bytes, {len(rows)} places")


def main():
    DATA.mkdir(exist_ok=True)
    fetch_country_names()
    fetch_gazetteer()
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
