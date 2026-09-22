# kids-news-maps

Locator maps for a Hebrew children's news digest. Every coordinate on a map
built here is resolved from OpenStreetMap and recorded in `data/places.json`,
where it can be read as a diff before anyone sees it. None are typed from
memory - an earlier version of this tooling did that and placed a marker
7.4 km from the place it named, with nothing to catch it.

## What is here

| Path | |
|---|---|
| `tools/places.py` | Hebrew place name to coordinate, cache first, Nominatim on a miss |
| `tools/genmap.py` | one map spec to one SVG, refusing to write when a check fails |
| `tools/inject.py` | puts rendered maps into a digest page |
| `tools/fetch_data.py` | one-off, vendors the boundary data below |
| `data/countries-*.json` | Natural Earth country outlines, trimmed |
| `data/places.json` | resolved coordinates, one reviewable entry per place |

Standard library only. No install step. `python3 tools/genmap.py spec.json --out map.svg`.

## The three checks

A map is not written unless every marker falls inside the country the resolver
named (within 5 km, which absorbs coastline generalisation), lands inside the
viewBox with its label, sits at least 11 units clear of its own label, and is
40 units clear of every other label. A failure prints what failed and writes
nothing.

## Data licences

Place coordinates in `data/places.json` are derived from OpenStreetMap:
**Data (c) OpenStreetMap contributors, ODbL 1.0, https://www.openstreetmap.org/copyright**.
Anything published from them must carry that attribution.

Country outlines in `data/countries-*.json` are from Natural Earth
(`nvkelso/natural-earth-vector`, public domain), trimmed by `tools/fetch_data.py`
at commit `ca96624a56bd078437bca8184e78163e5039ad19`.

The code itself carries no licence yet - the owner has not chosen one.
