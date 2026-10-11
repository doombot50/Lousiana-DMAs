#!/usr/bin/env python3
"""
build_map.py — the map's geometry: every county in Louisiana's seven markets
================================================================================
Four of Louisiana's seven Nielsen markets reach past the state line:
Shreveport into East Texas and southwest Arkansas, Monroe–El Dorado into
south Arkansas, and Baton Rouge and New Orleans into Mississippi. The map
draws each market whole, with the out-of-state counties in a muted shade,
because the household counts behind every "per TV household" figure are the
whole market's too.

    python3 build_map.py

Each county (parish) is assigned to the DMA whose polygon contains its
centroid, the method data/parish_dma.json was built with; the 64 parishes
are checked against that file and the build stops on any disagreement.
Shapes are projected equirectangular (scaled by the cosine of the middle
latitude), fitted to a 940-unit-wide frame, and simplified by
Douglas–Peucker.

Inputs, downloaded once into ./.geo_cache (git-ignored):
  * Nielsen DMA polygons, simzou/nielsen-dma `nielsentopo.json` (TopoJSON);
  * U.S. county outlines (Census cartographic boundaries) as GeoJSON keyed
    by FIPS, plotly/datasets `geojson-counties-fips.json`.
Writes data/map_paths.json and data/county_dma.json. Stdlib only.
"""
import json
import math
import os
import sys
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
D = lambda *p: os.path.join(HERE, *p)
CACHE = D('.geo_cache')
SOURCES = {
    'nielsentopo.json': 'https://raw.githubusercontent.com/simzou/nielsen-dma/master/nielsentopo.json',
    'counties.json': 'https://raw.githubusercontent.com/plotly/datasets/master/geojson-counties-fips.json',
}
# Louisiana's seven markets, by Nielsen DMA code.
DMAS = {612: 'Shreveport, LA', 622: 'New Orleans, LA', 628: 'Monroe, LA-El Dorado, AR',
        642: 'Lafayette, LA', 643: 'Lake Charles, LA', 644: 'Alexandria, LA',
        716: 'Baton Rouge, LA'}
# States the seven markets can reach: Louisiana and its neighbours.
STATES = {'22': 'LA', '48': 'TX', '05': 'AR', '28': 'MS'}
WIDTH = 940.0
TOLERANCE = 1.1        # Douglas–Peucker, in output units


def fetch(name):
    os.makedirs(CACHE, exist_ok=True)
    path = os.path.join(CACHE, name)
    if not os.path.exists(path):
        req = urllib.request.Request(SOURCES[name], headers={'User-Agent': 'louisiana-airwaves/1.0'})
        with urllib.request.urlopen(req, timeout=120) as r, open(path + '.part', 'wb') as f:
            f.write(r.read())
        os.replace(path + '.part', path)
    return json.load(open(path, encoding='utf-8'))


def topo_polygons(topo):
    """DMA code -> list of rings (lon, lat) from the quantized TopoJSON."""
    sx, sy = topo['transform']['scale']
    tx, ty = topo['transform']['translate']
    arcs = []
    for arc in topo['arcs']:
        x = y = 0
        pts = []
        for dx, dy in arc:
            x += dx
            y += dy
            pts.append((x * sx + tx, y * sy + ty))
        arcs.append(pts)

    def ring(idx):
        out = []
        for i in idx:
            pts = arcs[i] if i >= 0 else arcs[~i][::-1]
            out.extend(pts if not out else pts[1:])
        return out

    polys = {}
    for g in topo['objects']['nielsen_dma']['geometries']:
        code = g['properties']['dma']
        if code not in DMAS:
            continue
        parts = [g['arcs']] if g['type'] == 'Polygon' else g['arcs']
        polys[code] = [ring(r) for part in parts for r in part]
    return polys


def inside(pt, rings):
    """Even-odd rule over all rings (holes included)."""
    x, y = pt
    hit = False
    for r in rings:
        for (x1, y1), (x2, y2) in zip(r, r[1:] + r[:1]):
            if (y1 > y) != (y2 > y) and x < (x2 - x1) * (y - y1) / (y2 - y1) + x1:
                hit = not hit
    return hit


def outer_rings(geom):
    if geom['type'] == 'Polygon':
        return [geom['coordinates'][0]]
    return [p[0] for p in geom['coordinates']]


def centroid(rings):
    """Area-weighted centroid of a feature's outer rings."""
    ax = ay = at = 0.0
    for r in rings:
        for (x1, y1), (x2, y2) in zip(r, r[1:] + r[:1]):
            c = x1 * y2 - x2 * y1
            at += c
            ax += (x1 + x2) * c
            ay += (y1 + y2) * c
    return ax / (3 * at), ay / (3 * at)


def simplify(pts, tol):
    """Douglas–Peucker on an open polyline."""
    if len(pts) < 3:
        return pts
    (x1, y1), (x2, y2) = pts[0], pts[-1]
    dx, dy = x2 - x1, y2 - y1
    norm = math.hypot(dx, dy) or 1e-12
    best, idx = 0.0, 0
    for i in range(1, len(pts) - 1):
        px, py = pts[i]
        d = abs(dy * px - dx * py + x2 * y1 - y2 * x1) / norm if (dx or dy) else math.hypot(px - x1, py - y1)
        if d > best:
            best, idx = d, i
    if best <= tol:
        return [pts[0], pts[-1]]
    return simplify(pts[:idx + 1], tol)[:-1] + simplify(pts[idx:], tol)


def main():
    topo, counties = fetch('nielsentopo.json'), fetch('counties.json')
    polys = topo_polygons(topo)

    feats = []
    for f in counties['features']:
        st = STATES.get(f['properties']['STATE'])
        if not st:
            continue
        rings = outer_rings(f['geometry'])
        c = centroid(rings)
        hits = [code for code, rs in polys.items() if inside(c, rs)]
        if not hits:
            continue
        feats.append({'fips': f['id'], 'n': f['properties']['NAME'], 'st': st,
                      'dma': DMAS[hits[0]], 'rings': rings})

    # The parishes must land where data/parish_dma.json already puts them.
    known = json.load(open(D('data', 'parish_dma.json'), encoding='utf-8'))
    mine = {f['n'].replace('St.', 'St.'): f['dma'] for f in feats if f['st'] == 'LA'}
    bad = {n: (mine.get(n), d) for n, d in known.items() if mine.get(n) != d}
    if bad:
        sys.exit(f'Parish assignments disagree with data/parish_dma.json: {bad}')

    # Equirectangular, fitted to the seven markets' full extent.
    xs = [x for f in feats for r in f['rings'] for x, _ in r]
    ys = [y for f in feats for r in f['rings'] for _, y in r]
    k = math.cos(math.radians((min(ys) + max(ys)) / 2))
    s = WIDTH / ((max(xs) - min(xs)) * k)
    proj = lambda p: ((p[0] - min(xs)) * k * s, (max(ys) - p[1]) * s)
    height = round((max(ys) - min(ys)) * s, 1)

    out = []
    for f in sorted(feats, key=lambda f: (f['st'] != 'LA', f['fips'])):
        d = ''
        for r in f['rings']:
            pts = simplify([proj(p) for p in r], TOLERANCE)
            if len(pts) < 4:
                continue
            d += 'M' + ' '.join(f'{x:.0f} {y:.0f}' for x, y in pts[:-1]) + 'Z'
        if d:
            out.append({'fips': f['fips'], 'n': f['n'], 'st': f['st'], 'dma': f['dma'], 'd': d})

    with open(D('data', 'map_paths.json'), 'w', encoding='utf-8') as fh:
        json.dump({'w': WIDTH, 'h': height, 'counties': out}, fh, separators=(',', ':'))
    with open(D('data', 'county_dma.json'), 'w', encoding='utf-8') as fh:
        json.dump({f['fips']: {'n': f['n'], 'st': f['st'], 'dma': f['dma']}
                   for f in sorted(feats, key=lambda f: f['fips'])}, fh, indent=1)
    by = {}
    for f in feats:
        by.setdefault((f['dma'], f['st']), []).append(f['n'])
    for (dma, st), ns in sorted(by.items()):
        print(f'  {dma:28} {st}  {len(ns):3}  ' + (', '.join(sorted(ns)) if st != 'LA' else ''))
    print(f'Wrote data/map_paths.json ({len(out)} shapes, {WIDTH:.0f}x{height}) and data/county_dma.json')


if __name__ == '__main__':
    main()
