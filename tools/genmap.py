"""Render one map spec to one SVG.

Usage:  python3 tools/genmap.py spec.json --out map.svg [--defs defs.svg]
"""
import argparse
import html
import json
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tools import places

DATA = Path(__file__).resolve().parent.parent / "data"
WORLD_EXTENT = (-170, 180, -56, 80)


def load_countries(base):
    """base is "110m" or "50m"."""
    d = json.loads((DATA / f"countries-{base}.json").read_text(encoding="utf-8"))
    return d["features"]


def simplify(pts, tol):
    """Drop points closer than tol degrees to the previous kept point."""
    if not pts:
        return pts
    out = [pts[0]]
    for p in pts[1:-1]:
        if abs(p[0] - out[-1][0]) + abs(p[1] - out[-1][1]) >= tol:
            out.append(p)
    out.append(pts[-1])
    return out


class Proj:
    """Equirectangular, with x compressed by cos(mean latitude)."""

    def __init__(self, lon0, lon1, lat0, lat1, w, h):
        self.lon0, self.lon1, self.lat0, self.lat1 = lon0, lon1, lat0, lat1
        self.w, self.h = w, h
        self.k = math.cos(math.radians((lat0 + lat1) / 2))
        spanx = (lon1 - lon0) * self.k
        spany = lat1 - lat0
        self.s = min(w / spanx, h / spany)
        self.ox = (w - spanx * self.s) / 2
        self.oy = (h - spany * self.s) / 2

    def __call__(self, lon, lat):
        x = self.ox + (lon - self.lon0) * self.k * self.s
        y = self.oy + (self.lat1 - lat) * self.s
        return x, y


def path_for(features, proj, tol, bbox=None):
    d = []
    for f in features:
        for ring in f["rings"]:
            if bbox:
                lo0, lo1, la0, la1 = bbox
                if not any(lo0 - 8 <= p[0] <= lo1 + 8 and la0 - 8 <= p[1] <= la1 + 8 for p in ring):
                    continue
            r = simplify(ring, tol)
            if len(r) < 3:
                continue
            pts = [proj(p[0], p[1]) for p in r]
            d.append("M" + "L".join(f"{x:.1f} {y:.1f}" for x, y in pts) + "Z")
    return "".join(d)


def marker_svg(x, y, label, dx=0, dy=-13):
    """A dot with its label offset from it, by default above.

    text-anchor is always "middle" and never configurable. The page is RTL, and
    under RTL "start" and "end" flip: a Hebrew label anchored "start" runs
    leftward from its x, back over its own marker. The labels carry a halo in
    the sea colour, so such a label erases the dot it belongs to - which is
    exactly what happened to תל אביב on the 19 September map.
    """
    return (
        f'<g class="mk"><circle cx="{x:.1f}" cy="{y:.1f}" r="4.2"/>'
        f'<text x="{x + dx:.1f}" y="{y + dy:.1f}" text-anchor="middle">'
        f'{html.escape(label)}</text></g>'
    )


def point_in_rings(rings, lon, lat):
    """Ray casting. True when the point falls inside an odd number of rings."""
    inside = False
    for ring in rings:
        for i in range(len(ring)):
            x1, y1 = ring[i]
            x2, y2 = ring[i - 1]
            if (y1 > lat) != (y2 > lat):
                xint = (x2 - x1) * (lat - y1) / (y2 - y1) + x1
                if lon < xint:
                    inside = not inside
    return inside


CONTAINMENT_TOLERANCE_KM = 5.0


def _segment_distance_km(lon, lat, a, b):
    """Point-to-segment distance in km, on a local equirectangular plane."""
    k = math.cos(math.radians(lat))
    px, py = lon * k, lat
    ax, ay = a[0] * k, a[1]
    bx, by = b[0] * k, b[1]
    dx, dy = bx - ax, by - ay
    if dx == 0 and dy == 0:
        t = 0.0
    else:
        t = max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / (dx * dx + dy * dy)))
    return math.hypot(px - (ax + t * dx), py - (ay + t * dy)) * 111.32


def distance_to_rings(rings, lon, lat):
    """Km from a point to the nearest edge of any ring. 0.0 if inside."""
    if point_in_rings(rings, lon, lat):
        return 0.0
    best = float("inf")
    for ring in rings:
        for i in range(len(ring) - 1):
            best = min(best, _segment_distance_km(lon, lat, ring[i], ring[i + 1]))
    return best


def check_containment(placed, countries):
    """Each resolved marker must fall inside the country its resolver named."""
    by_iso = {f["iso"].lower(): f for f in countries if f["iso"]}
    fails = []
    for m in placed:
        if m.get("unverified") or not m.get("cc"):
            continue
        country = by_iso.get(m["cc"].lower())
        if country is None:
            fails.append(f'containment: {m["label"]} claims country {m["cc"]!r}, '
                         f"which is not in the boundary data")
            continue
        # Coastline generalisation puts real cities just outside their own country:
        # Haifa is 0.30 km outside the 50m Israel outline, Eilat 0.69 km outside the
        # 110m one. A wrong-country blunder misses by hundreds of km, so a 5 km
        # tolerance separates the two without weakening the check.
        d = distance_to_rings(country["rings"], m["lon"], m["lat"])
        if d > CONTAINMENT_TOLERANCE_KM:
            fails.append(f'containment: {m["label"]} at {m["lon"]:.4f},{m["lat"]:.4f} '
                         f'is {d:,.0f} km outside {country["n"]}')
    return fails


def check_frame(placed, w, h, margin=6):
    fails = []
    for m in placed:
        points = (("marker", m["x"], m["y"]),
                  ("label", m["x"] + m.get("dx", 0), m["y"] + m.get("dy", 0)))
        for what, x, y in points:
            if not (margin <= x <= w - margin and margin <= y <= h - margin):
                fails.append(f'frame: {m["label"]} {what} projects to '
                             f'{x:.1f},{y:.1f}, outside the {w}x{h} viewBox')
    return fails


LABEL_CLEAR_UNITS = 11


def check_label_clear(placed, min_units=LABEL_CLEAR_UNITS):
    """A label must not sit on top of the marker it names.

    Labels are drawn with a halo in the sea colour, so one printed over its own
    dot rubs the dot out. The reader then sees a place name floating with
    nothing marking the place.
    """
    fails = []
    for m in placed:
        d = math.hypot(m.get("dx", 0), m.get("dy", 0))
        if d < min_units:
            fails.append(f'label: {m["label"]} sits {d:.1f} units from its own '
                         f"marker, close enough for its halo to erase the dot; "
                         f"minimum is {min_units}")
    return fails


def check_spacing(placed, min_units=40):
    fails = []
    for i, a in enumerate(placed):
        for b in placed[i + 1:]:
            # The labels collide, not the dots, so measure where the text sits.
            ax, ay = a["x"] + a.get("dx", 0), a["y"] + a.get("dy", 0)
            bx, by = b["x"] + b.get("dx", 0), b["y"] + b.get("dy", 0)
            d = math.hypot(ax - bx, ay - by)
            if d < min_units:
                fails.append(f'spacing: {a["label"]} and {b["label"]} are '
                             f"{d:.1f} units apart, minimum is {min_units}")
    return fails


class CheckFailed(Exception):
    def __init__(self, failures):
        super().__init__("; ".join(failures))
        self.failures = failures


class SpecError(Exception):
    pass


TOL = {"50m": 0.035, "110m": 0.30, "world": 1.6}


def auto_extent(points, w, h, countries, pad=0.18, min_span=1.2):
    """The smallest window holding every point and Israel, shaped to the canvas.

    Israel is always in frame because the reader is a child in Israel: a dot in
    Madrid means little on its own, and a great deal next to home. The window is
    then widened or heightened to the canvas aspect so the map fills its frame
    rather than sitting in a letterbox.
    """
    pts = list(points)
    israel = [f for f in countries if f["n"] == "Israel"]
    if israel:
        pts += [(p[0], p[1]) for r in israel[0]["rings"] for p in r]
    lons, lats = [p[0] for p in pts], [p[1] for p in pts]
    lo0, lo1, la0, la1 = min(lons), max(lons), min(lats), max(lats)

    dlon, dlat = max(lo1 - lo0, min_span), max(la1 - la0, min_span)
    lo0, lo1 = lo0 - dlon * pad, lo1 + dlon * pad
    la0, la1 = la0 - dlat * pad, la1 + dlat * pad

    k = math.cos(math.radians((la0 + la1) / 2)) or 1e-6
    spanx, spany = (lo1 - lo0) * k, la1 - la0
    if spanx / spany < w / h:
        need = spany * (w / h) / k
        mid = (lo0 + lo1) / 2
        lo0, lo1 = mid - need / 2, mid + need / 2
    else:
        need = spanx / (w / h)
        mid = (la0 + la1) / 2
        la0, la1 = mid - need / 2, mid + need / 2

    return (max(lo0, -180.0), min(lo1, 180.0), max(la0, -85.0), min(la1, 85.0))


def _resolve_markers(spec, cache, fetch):
    """Resolve every marker to a coordinate. Returns (resolved, warnings)."""
    resolved, warnings = [], []
    for m in spec["markers"]:
        if "anchor" in m:
            raise SpecError(
                f'marker {m.get("label") or m.get("place")!r} sets "anchor". '
                f"Labels are always centred: under RTL, start and end flip and "
                f"the label lands on its own marker. Use dx and dy instead."
            )
        if "place" in m:
            hit = places.resolve(m["place"], cache, fetch=fetch)
            if hit is None:
                warnings.append(f'dropped: {m["place"]} did not resolve to anything usable')
                continue
            if hit["type"] in places.COARSE:
                warnings.append(
                    f'COARSE: {m["place"]} resolved to a {hit["type"]} '
                    f'({hit["display_name"]}), whose centre can be far from the '
                    f'place itself - check it')
            lon, lat, cc, unverified = hit["lon"], hit["lat"], hit["cc"], ""
            label = m.get("label", m["place"])
        else:
            if not m.get("unverified"):
                raise SpecError(
                    f'marker {m.get("label")!r} gives raw coordinates without an '
                    f'"unverified" provenance string'
                )
            lon, lat, cc, unverified = m["lon"], m["lat"], "", m["unverified"]
            label = m["label"]
            warnings.append(f"UNVERIFIED: {label} at {lon},{lat} - {unverified}")
        resolved.append({"label": label, "lon": lon, "lat": lat,
                         "cc": cc, "unverified": unverified,
                         "dx": m.get("dx", 0), "dy": m.get("dy", -13)})
    return resolved, warnings


def render(spec, cache, fetch=None):
    fetch = places.nominatim if fetch is None else fetch
    base = spec.get("base", "50m")
    if base not in TOL:
        raise SpecError(f"unknown base {base!r}, expected one of {sorted(TOL)}")
    w, h = spec["size"]
    resolved, warnings = _resolve_markers(spec, cache, fetch)
    if not resolved:
        raise CheckFailed(["no marker resolved; nothing worth drawing"])

    countries = load_countries("110m" if base in ("110m", "world") else "50m")
    if base == "world":
        extent = WORLD_EXTENT
    elif spec.get("extent", "auto") == "auto":
        extent = auto_extent([(r["lon"], r["lat"]) for r in resolved], w, h,
                             load_countries("50m"))
    else:
        extent = tuple(spec["extent"])

    proj = Proj(*extent, w, h)
    placed = []
    for r in resolved:
        x, y = proj(r["lon"], r["lat"])
        placed.append(dict(r, x=x, y=y))
    # The 110m dataset drops small states entirely - Singapore, Hong Kong, Macao,
    # Malta, Bahrain, Monaco, the Vatican, Liechtenstein, Andorra, San Marino -
    # so a world map marking one would fail containment for lack of a boundary to
    # test against, not for being wrong. Draw from the base's own dataset, but
    # always check against the finer one.
    check_countries = countries if base == "50m" else load_countries("50m")
    failures = (check_containment(placed, check_countries)
                + check_frame(placed, w, h)
                + check_label_clear(placed)
                + check_spacing(placed))
    if failures:
        raise CheckFailed(failures)

    for m in placed:
        if not m["unverified"] and not m["cc"]:
            warnings.append(f'UNTESTED: {m["label"]} resolved without a country, '
                            f'so the containment check could not test it')

    defs = None
    if base == "world":
        # The id carries the viewBox it was projected for. A <use> only ever
        # reaches a path built at its own scale: reusing one across sizes draws
        # the coastline at one projection and the markers at another, which is
        # how Madrid came to sit on Greenland on 21 September.
        wid = f"wd-{w}x{h}"
        land = [f for f in countries if f["n"] != "Antarctica"]
        defs = ('<svg class="mapdefs" aria-hidden="true" width="0" height="0" '
                f'xmlns="http://www.w3.org/2000/svg"><defs><path id="{wid}" '
                'd="%s"/></defs></svg>') % path_for(land, proj, TOL["world"])
        body = f'<use class="land" href="#{wid}" xlink:href="#{wid}"/>'
    else:
        near = [f for f in countries
                if any(extent[0] - 4 <= p[0] <= extent[1] + 4 and extent[2] - 4 <= p[1] <= extent[3] + 4
                       for r in f["rings"] for p in r)]
        body = f'<path class="land faint" d="{path_for(near, proj, TOL[base], extent)}"/>'

    hi = [f for f in countries if f["n"] in spec.get("highlight", [])]
    if hi:
        body += f'<path class="hi" d="{path_for(hi, proj, TOL[base])}"/>'
    for m in placed:
        body += marker_svg(m["x"], m["y"], m["label"], m["dx"], m["dy"])

    cls = "map portrait" if h > w else "map"
    xlink = ' xmlns:xlink="http://www.w3.org/1999/xlink"' if base == "world" else ""
    svg = (f'<svg class="{cls}" viewBox="0 0 {w} {h}" role="img" '
           f'aria-label="{html.escape(spec["title"])}"{xlink} '
           f'xmlns="http://www.w3.org/2000/svg">'
           f'<rect class="sea" x="0" y="0" width="{w}" height="{h}"/>{body}</svg>')
    return svg, defs, warnings


def main(argv=None):
    ap = argparse.ArgumentParser(description="Render one map spec to one SVG.")
    ap.add_argument("spec")
    ap.add_argument("--out", required=True)
    ap.add_argument("--defs", help="where to write the shared world <defs>")
    a = ap.parse_args(argv)

    spec = json.loads(Path(a.spec).read_text(encoding="utf-8"))
    cache = places.load_cache()
    try:
        svg, defs, warnings = render(spec, cache)
    except SpecError as e:
        print(f"spec error: {e}", file=sys.stderr)
        return 1
    except CheckFailed as e:
        for line in e.failures:
            print(line, file=sys.stderr)
        return 2 if "no marker resolved" in e.failures[0] else 1
    finally:
        # A resolved coordinate stays valid even when a check rejects the map.
        # Persisting here keeps the promise that a name is queried at most once.
        places.save_cache(cache)
    Path(a.out).write_text(svg, encoding="utf-8")
    if defs and a.defs:
        Path(a.defs).write_text(defs, encoding="utf-8")
    for line in warnings:
        print(line, file=sys.stderr)
    print(f"wrote {a.out} ({len(svg):,} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
