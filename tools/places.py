"""Turn a Hebrew place name into a coordinate.

The committed cache at data/places.json is the source of truth. A name that is
already in it never causes a network call. A miss goes to the vendored GeoNames
gazetteer next, which covers settlements only and needs no network. A miss there
goes to Nominatim once, and an accepted result is written back so it arrives in a
reviewable diff. Nominatim being unreachable, as in the cloud sandbox, is a miss.
"""
import json
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import date
from functools import lru_cache
from pathlib import Path

DATA = Path(__file__).resolve().parent.parent / "data"
CACHE = DATA / "places.json"
GAZETTEER = DATA / "cities15000-he.json"
COUNTRY_NAMES = DATA / "countries-he.json"
UA = "kids-news-map-tool/0.1 (contact yonidishon@gmail.com)"
ENDPOINT = "https://nominatim.openstreetmap.org/search"
MIN_INTERVAL = 1.2

# Nominatim's addresstype for a result we are willing to put a marker on. This is
# what rejects חווארה resolving to עוקף חווארה, a trunk road with addresstype "road".
# Place-scale results: the marker lands on the thing itself.
FINE = {
    "city", "town", "village", "hamlet", "suburb", "quarter", "neighbourhood",
    "municipality", "protected_area", "nature_reserve", "national_park",
    "strait", "bay", "cape", "peninsula", "island", "archipelago",
}
# Administrative areas, whose centre can be far from the place a reader means:
# מוסקבה matches Moscow Oblast before Moscow, about 48 km out.
COARSE = {"county", "state", "province", "region", "country", "sea"}
ALLOWED = FINE | COARSE
# Water, which no country outline contains: the containment check skips these.
WATER = {"strait", "bay", "sea"}

_last_call = 0.0


def load_cache(path=CACHE):
    if not Path(path).exists():
        return {}
    return json.loads(Path(path).read_text(encoding="utf-8"))


def save_cache(cache, path=CACHE):
    text = json.dumps(cache, ensure_ascii=False, indent=1, sort_keys=True)
    Path(path).write_text(text + "\n", encoding="utf-8")


def index_gazetteer(rows):
    """Hebrew name -> entry. A name shared across places goes to the most populous:
    לונדון is London, England, not London, Ontario."""
    index = {}
    for gid, name, lon, lat, cc, pop, he_names in sorted(rows, key=lambda r: r[5]):
        entry = {"lon": lon, "lat": lat, "cc": cc, "geonames_id": gid, "type": "city",
                 "display_name": f"{name}, {cc}", "source": "geonames"}
        for he in he_names:
            index[he] = entry
    return index


@lru_cache(maxsize=None)
def default_gazetteer():
    if not GAZETTEER.exists():
        return {}
    return index_gazetteer(json.loads(GAZETTEER.read_text(encoding="utf-8"))["places"])


@lru_cache(maxsize=None)
def country_names():
    if not COUNTRY_NAMES.exists():
        return {}
    return json.loads(COUNTRY_NAMES.read_text(encoding="utf-8"))["names"]


def country_for(name, gazetteer=None):
    """The Natural Earth English name if `name` is a country, else None.

    A country is an area, not a point, so it is shaded rather than dotted. The
    city gazetteer would otherwise put סוריה on Soria, Spain. A city-state, whose
    gazetteer city lies in the country of the same name - סינגפור - stays a dot.
    """
    c = country_names().get(name)
    if c is None:
        return None
    gazetteer = default_gazetteer() if gazetteer is None else gazetteer
    city = gazetteer.get(name)
    if city and c["iso"] and city["cc"] == c["iso"].lower():
        return None
    return c["n"]


def nominatim(name):
    """One rate-limited query. Returns the raw hit list."""
    global _last_call
    wait = MIN_INTERVAL - (time.monotonic() - _last_call)
    if wait > 0:
        time.sleep(wait)
    url = ENDPOINT + "?" + urllib.parse.urlencode(
        {"q": name, "format": "jsonv2", "limit": 5,
         "accept-language": "he", "addressdetails": 1}
    )
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=30) as r:
        hits = json.load(r)
    _last_call = time.monotonic()
    return hits


def pick(hits):
    """Prefer a place-scale hit; fall back to a coarse one only if nothing finer."""
    coarse = None
    for h in hits:
        t = h.get("addresstype") or h.get("type")
        if t in FINE:
            return h
        if t in COARSE and coarse is None:
            coarse = h
    return coarse


def resolve(name, cache, fetch=nominatim, today=None, gazetteer=None):
    """Cache, then gazetteer, then one query. Returns None rather than guessing."""
    if name in cache:
        return cache[name]
    gazetteer = default_gazetteer() if gazetteer is None else gazetteer
    if name in gazetteer:
        return gazetteer[name]
    try:
        hits = fetch(name)
    except (urllib.error.URLError, OSError):
        return None
    hit = pick(hits)
    if hit is None:
        return None
    entry = {
        "lon": float(hit["lon"]),
        "lat": float(hit["lat"]),
        "cc": (hit.get("address") or {}).get("country_code", ""),
        "osm_id": hit["osm_id"],
        "type": hit.get("addresstype") or hit.get("type"),
        "display_name": hit["display_name"],
        "resolved": today or date.today().isoformat(),
    }
    cache[name] = entry
    return entry
