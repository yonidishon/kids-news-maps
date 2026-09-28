# kids-news-maps

Locator maps for a Hebrew children's news digest. Every coordinate on a map
built here is resolved from OpenStreetMap and recorded in `data/places.json`,
where it can be read as a diff before anyone sees it. None are typed from
memory - an earlier version of this tooling did that and placed a marker
7.4 km from the place it named, with nothing to catch it.

## What is here

| Path | |
|---|---|
| `tools/places.py` | Hebrew place name to coordinate: cache, then the offline gazetteer, then Nominatim where reachable |
| `tools/genmap.py` | one map spec to one SVG, refusing to write when a check fails |
| `tools/inject.py` | puts rendered maps into a digest page |
| `tools/fetch_data.py` | one-off, vendors the data files below |
| `data/countries-110m.json`, `data/countries-50m.json` | Natural Earth country outlines, trimmed |
| `data/countries-he.json` | Hebrew country names to Natural Earth English names, for lookup only |
| `data/cities15000-he.json` | GeoNames `cities15000`, the 3,414 places with a Hebrew name |
| `data/places.json` | resolved coordinates, one reviewable entry per place |

Standard library only. No install step. `python3 tools/genmap.py spec.json --out map.svg`.

## Resolving a place

A marker naming a country is shaded as a highlight, never dotted: the city
gazetteer would put `סוריה` on Soria, Spain. A city-state such as `סינגפור`
stays a dot. Anything else resolves from the committed cache, then the offline
gazetteer (settlements only), then Nominatim. The cloud sandbox cannot reach
Nominatim, so there a place in neither file is dropped from the map and
reported. Nature reserves, straits and other non-settlements reach the map only
through a reviewed entry in `data/places.json`.

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

Settlement coordinates in `data/cities15000-he.json` are from GeoNames:
**GeoNames, CC BY 4.0, https://www.geonames.org**. Anything published from
them must carry that attribution.

Country outlines and names in `data/countries-*.json` are from Natural Earth
(`nvkelso/natural-earth-vector`, public domain), trimmed by `tools/fetch_data.py`
at commit `ca96624a56bd078437bca8184e78163e5039ad19`.

The code itself carries no licence yet - the owner has not chosen one.
