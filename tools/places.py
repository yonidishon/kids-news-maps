"""Turn a Hebrew place name into a coordinate.

The committed cache at data/places.json is the source of truth. A name that is
already in it never causes a network call. A miss goes to Nominatim once, and an
accepted result is written back so it arrives in a reviewable diff.
"""
import json
import time
import urllib.parse
import urllib.request
from datetime import date
from pathlib import Path

CACHE = Path(__file__).resolve().parent.parent / "data" / "places.json"
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

_last_call = 0.0


def load_cache(path=CACHE):
    if not Path(path).exists():
        return {}
    return json.loads(Path(path).read_text(encoding="utf-8"))


def save_cache(cache, path=CACHE):
    text = json.dumps(cache, ensure_ascii=False, indent=1, sort_keys=True)
    Path(path).write_text(text + "\n", encoding="utf-8")


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


def resolve(name, cache, fetch=nominatim, today=None):
    """Cache first, one query on a miss. Returns None rather than guessing."""
    if name in cache:
        return cache[name]
    hit = pick(fetch(name))
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
