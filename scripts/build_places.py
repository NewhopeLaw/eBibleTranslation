#!/usr/bin/env python3
"""Biblical geography for the reader: where each place is, and a map to show it on.

    python scripts/build_places.py        # -> site/morph/places.js

Places and coordinates: the OpenBible.info geocoding data (CC BY 4.0), the
2007 tab-delimited files `geo_merged.txt` / `geo_places.txt` in
sources/openbible/ — name, the location the coordinates belong to, latitude,
longitude, the verses that mention it, and a note. (The newer dataset on
GitHub mixes in OpenStreetMap geometry under a share-alike licence and is
deliberately not used.)

Base map: Natural Earth 50m coastline, 110m lakes and 50m rivers — public
domain — clipped to the biblical world, simplified, and written as SVG paths,
so the map is drawn offline with no tiles and no map service.

Writes site/morph/places.js:
    PLACES = {name: [lat, lon, root, note]}
    VPLACES = {"Book|ch|v": [name, ...]}          places mentioned in that verse
    MAPSVG = {w, h, box: [lon0, lat0, lon1, lat1], coast: [path...], lakes: [...], rivers: [...]}
"""
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import manifest                                       # noqa: E402
from books import BOOKS   # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "sources" / "openbible"
OUT = ROOT / "site" / "morph" / "places.js"

# the biblical world: Italy/Greece to Persia, Nile to Ararat
BOX = (10.0, 18.0, 56.0, 46.0)          # lon0, lat0, lon1, lat1 — Rome to Persia, Nile to Ararat
W, H = 1000.0, 610.0
TOL = 0.02                               # simplification tolerance in degrees

ABBR = {"Gen": "Genesis", "Ex": "Exodus", "Lev": "Leviticus", "Num": "Numbers", "Deut": "Deuteronomy",
        "Josh": "Joshua", "Judg": "Judges", "Ruth": "Ruth", "1 Sam": "1 Samuel", "2 Sam": "2 Samuel",
        "1 Kgs": "1 Kings", "2 Kgs": "2 Kings", "1 Chr": "1 Chronicles", "2 Chr": "2 Chronicles",
        "Ezra": "Ezra", "Neh": "Nehemiah", "Est": "Esther", "Job": "Job", "Ps": "Psalms",
        "Prov": "Proverbs", "Eccl": "Ecclesiastes", "Sng": "Song of Songs", "Isa": "Isaiah",
        "Jer": "Jeremiah", "Lam": "Lamentations", "Ezek": "Ezekiel", "Dan": "Daniel", "Hos": "Hosea",
        "Joel": "Joel", "Amos": "Amos", "Obad": "Obadiah", "Jonah": "Jonah", "Mic": "Micah",
        "Nahum": "Nahum", "Hab": "Habakkuk", "Zeph": "Zephaniah", "Hag": "Haggai", "Zech": "Zechariah",
        "Mal": "Malachi", "Matt": "Matthew", "Mark": "Mark", "Luke": "Luke", "John": "John",
        "Acts": "Acts", "Rom": "Romans", "1 Cor": "1 Corinthians", "2 Cor": "2 Corinthians",
        "Gal": "Galatians", "Eph": "Ephesians", "Phil": "Philippians", "Col": "Colossians",
        "1 Thes": "1 Thessalonians", "2 Thes": "2 Thessalonians", "1 Tim": "1 Timothy", "2 Tim": "2 Timothy",
        "Titus": "Titus", "Phlm": "Philemon", "Heb": "Hebrews", "Jas": "James", "1 Pet": "1 Peter",
        "2 Pet": "2 Peter", "1 John": "1 John", "2 John": "2 John", "3 John": "3 John", "Jude": "Jude",
        "Rev": "Revelation"}
NAMES = {m["name"] for m in BOOKS.values()}
REF = re.compile(r"((?:[1-3]\s)?[A-Z][A-Za-z]*)\.?\s+(\d+):(\d+)(?:[-–](\d+))?")


# ------------------------------------------------------------------ places
def load_places():
    places, verses = {}, defaultdict(list)
    for line in (SRC / "geo_merged.txt").read_text(encoding="utf-8", errors="replace").splitlines():
        if line.startswith("#") or not line.strip():
            continue
        f = line.split("\t")
        if len(f) < 5:
            continue
        name, root, lat, lon, refs = f[0].strip(), f[1].strip(), f[2].strip(), f[3].strip(), f[4]
        note = f[5].strip() if len(f) > 5 else ""
        try:
            la, lo = float(lat), float(lon)
        except ValueError:
            la = lo = None
        if name and (la is not None or root):
            places[name] = [la, lo, root, note]
        for m in REF.finditer(refs):
            book = ABBR.get(m.group(1).strip())
            if book not in NAMES:
                continue
            ch, v0 = int(m.group(2)), int(m.group(3))
            v1 = int(m.group(4)) if m.group(4) else v0
            for v in range(v0, min(v1, v0 + 30) + 1):
                key = f"{book}|{ch}|{v}"
                if name not in verses[key]:
                    verses[key].append(name)
    # resolve "root" chains so every place shown has coordinates
    for name, p in places.items():
        seen = set()
        while p[0] is None and p[2] and p[2] not in seen:
            seen.add(p[2])
            r = places.get(p[2].lstrip("<>~"))
            if not r:
                break
            p[0], p[1] = r[0], r[1]
    return {k: v for k, v in places.items() if v[0] is not None}, verses


# ------------------------------------------------------------------ base map
def project(lon, lat):
    x = (lon - BOX[0]) / (BOX[2] - BOX[0]) * W
    y = (BOX[3] - lat) / (BOX[3] - BOX[1]) * H
    return x, y


def clip_line(coords):
    """Split a line into the runs that fall inside the box (with a small margin)."""
    m = 2.0
    runs, cur = [], []
    for lon, lat in coords:
        inside = BOX[0] - m <= lon <= BOX[2] + m and BOX[1] - m <= lat <= BOX[3] + m
        if inside:
            cur.append((lon, lat))
        elif cur:
            cur.append((lon, lat))
            runs.append(cur)
            cur = []
    if cur:
        runs.append(cur)
    keep = []
    for r in runs:
        if len(r) < 2:
            continue
        xs, ys = [p[0] for p in r], [p[1] for p in r]
        if max(xs) - min(xs) > 0.05 or max(ys) - min(ys) > 0.05:      # drop the degenerate stubs clipping leaves behind
            keep.append(r)
    return keep


def simplify(pts, tol):
    if len(pts) < 3:
        return pts
    if pts[0] == pts[-1] and len(pts) > 3:        # a closed ring has no chord to measure against: halve it first
        mid = len(pts) // 2
        return simplify(pts[:mid + 1], tol)[:-1] + simplify(pts[mid:], tol)
    a, b = pts[0], pts[-1]
    dx, dy = b[0] - a[0], b[1] - a[1]
    den = (dx * dx + dy * dy) ** 0.5 or 1e-9
    worst, idx = 0.0, 0
    for i in range(1, len(pts) - 1):
        p = pts[i]
        d = abs(dy * p[0] - dx * p[1] + b[0] * a[1] - b[1] * a[0]) / den
        if d > worst:
            worst, idx = d, i
    if worst <= tol:
        return [a, b]
    return simplify(pts[:idx + 1], tol)[:-1] + simplify(pts[idx:], tol)


def geo_paths(path, kinds, tol, want=None):
    if not path.exists():
        return []
    data = json.loads(path.read_text(encoding="utf-8"))
    out = []
    for feat in data["features"]:
        props = feat.get("properties") or {}
        if want and not any(str(props.get(k, "")).lower() in want for k in ("name", "name_en", "featurecla")):
            continue
        geom = feat.get("geometry") or {}
        polys = []
        if geom.get("type") == "LineString":
            polys = [geom["coordinates"]]
        elif geom.get("type") in ("MultiLineString", "Polygon"):
            polys = geom["coordinates"]
        elif geom.get("type") == "MultiPolygon":
            polys = [ring for poly in geom["coordinates"] for ring in poly]
        for coords in polys:
            for run in clip_line([(c[0], c[1]) for c in coords if len(c) >= 2]):
                pts = simplify(run, tol)
                if len(pts) < 2:
                    continue
                xy = [project(lo, la) for lo, la in pts]
                if max(p[0] for p in xy) - min(p[0] for p in xy) < 2 and max(p[1] for p in xy) - min(p[1] for p in xy) < 2:
                    continue                                          # nothing visible at this size
                d = "M" + " L".join(f"{x:.1f},{y:.1f}" for x, y in xy)
                if geom.get("type") in ("Polygon", "MultiPolygon") and len(pts) > 3:
                    d += "Z"
                out.append(d)
    return out


def main():
    places, verses = load_places()
    coast = geo_paths(SRC / "ne50_coast.json", None, TOL)
    lakes = geo_paths(SRC / "ne_lakes.json", None, TOL)
    rivers = geo_paths(SRC / "ne_rivers.json", None, TOL * 1.5)
    mapsvg = {"w": W, "h": H, "box": list(BOX), "coast": coast, "lakes": lakes, "rivers": rivers}
    body = ("PLACES=" + json.dumps(places, ensure_ascii=False, separators=(",", ":")) + ";\n"
            + "VPLACES=" + json.dumps(verses, ensure_ascii=False, separators=(",", ":")) + ";\n"
            + "MAPSVG=" + json.dumps(mapsvg, separators=(",", ":")) + ";\n")
    OUT.write_text(body, encoding="utf-8")
    manifest.record("places", len(places), "places", "the map and the places tab", "build_places.py")
    print(f"places: {len(places)} located, {len(verses)} verses with a place; "
          f"map {len(coast)} coast + {len(lakes)} lake + {len(rivers)} river paths; "
          f"{OUT.stat().st_size / 1e6:.2f} MB -> {OUT}")


if __name__ == "__main__":
    sys.setrecursionlimit(10000)
    main()
