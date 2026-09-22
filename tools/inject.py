"""Put rendered maps back into a digest page, so they can be read in context.

Usage:
  python3 tools/inject.py --page in.html --entries entries.json --out out.html [--replace]

entries.json is a list of {"headline", "caption", "map"}, where "map" is a genmap spec.
This never publishes. It writes a file.
"""
import argparse
import html
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from tools import places
from tools.genmap import CheckFailed, SpecError, render

STORY_RE = re.compile(r'<article class="story">.*?</article>', re.S)
H2_RE = re.compile(r"<h2>(.*?)</h2>", re.S)
GEO_RE = re.compile(r'<figure class="geo">.*?</figure>\s*', re.S)
DEFS_ID_RE = re.compile(r'<path id="([^"]+)"')


class HeadlineNotFound(Exception):
    pass


def _figure(svg, caption):
    return ('<figure class="geo">\n<p class="tag">איפה זה קרה</p>\n'
            f"{svg}\n<figcaption>{html.escape(caption)}</figcaption>\n</figure>\n")


def inject(page, entries, cache, fetch=None, replace=False):
    """Returns (page, warnings). Raises HeadlineNotFound for an unknown headline."""
    fetch = places.nominatim if fetch is None else fetch
    warnings = []
    defs_blocks = {}
    for entry in entries:
        headline = entry["headline"]
        match = None
        for m in STORY_RE.finditer(page):
            h2 = H2_RE.search(m.group(0))
            if h2 and h2.group(1).strip() == headline:
                match = m
                break
        if match is None:
            if headline in page:
                raise HeadlineNotFound(
                    f'{headline} is on the page but not inside a well-formed '
                    f'<article class="story"> ... </article> block - check for '
                    f'unclosed markup rather than a wrong headline')
            raise HeadlineNotFound(headline)

        story = match.group(0)
        if GEO_RE.search(story) and not replace:
            warnings.append(f"kept existing map on {headline!r}; pass --replace to swap it")
            continue

        svg, defs, w = render(entry["map"], cache, fetch=fetch)
        warnings.extend(f"{headline}: {line}" for line in w)
        if defs:
            defs_blocks[DEFS_ID_RE.search(defs).group(1)] = defs

        story_out = GEO_RE.sub("", story) if replace else story
        if '<div class="talk">' not in story_out:
            raise HeadlineNotFound(f"{headline} has no .talk block to insert before")
        story_out = story_out.replace('<div class="talk">',
                                      _figure(svg, entry["caption"]) + '<div class="talk">', 1)
        page = page[:match.start()] + story_out + page[match.end():]

    # Insert the defs for each distinct projection the page is missing. Testing
    # for "any mapdefs block" was the bug that put Madrid on Greenland: the page
    # already carried a 720x340 world path, so the 480x220 one was dropped and
    # every new world map drew its coastline at the wrong scale.
    missing = [d for wid, d in sorted(defs_blocks.items())
               if f'id="{wid}"' not in page]
    if missing:
        anchor = page.index("<article")
        page = page[:anchor] + "\n".join(missing) + "\n" + page[anchor:]
    return page, warnings


def main(argv=None):
    ap = argparse.ArgumentParser(description="Inject maps into a digest page.")
    ap.add_argument("--page", required=True)
    ap.add_argument("--entries", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--replace", action="store_true")
    a = ap.parse_args(argv)

    page = Path(a.page).read_text(encoding="utf-8")
    entries = json.loads(Path(a.entries).read_text(encoding="utf-8"))
    cache = places.load_cache()
    try:
        out, warnings = inject(page, entries, cache, replace=a.replace)
    except (HeadlineNotFound, SpecError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
    except CheckFailed as e:
        for line in e.failures:
            print(line, file=sys.stderr)
        return 1
    finally:
        # A resolved coordinate stays valid even when a later entry raises;
        # persisting here keeps the promise that a name is queried at most once.
        places.save_cache(cache)
    Path(a.out).write_text(out, encoding="utf-8")
    for line in warnings:
        print(line, file=sys.stderr)
    print(f"wrote {a.out} ({len(out):,} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
