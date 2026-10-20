#!/usr/bin/env python3
"""Compare hand-placed marker coords with the TaxiNodes projection.

Reads a marker table in the psd_text_extract.jsx format, where the trailing
comment is the node name:

    { "7", 10007, 247, 251 }, -- Ironforge

matches each name against TaxiNodes.csv (Name_lang before the first ", "),
projects the world position with the UiMapAssignment region and prints the
difference. When a name matches several TaxiNodes rows, the nearest one is used
and the others are listed. When another TaxiNodes row is closer than the
matched one, or nothing matches, the nearest node is shown as a hint.

Usage:
  python compare_coords.py TaxiNodes.csv markers.lua --region -15980 -11880 5817 9917
  python compare_coords.py TaxiNodes.csv markers.lua --region ... --continent 0 --anchor -6 -4
"""
import argparse
import csv
import math
import re

ROW = re.compile(r'^\s*\{\s*("(?:[^"\\]|\\.)*"|\d+)\s*,\s*(\d+)\s*,\s*(-?[\d.]+)\s*,\s*(-?[\d.]+)[^}]*\}\s*,?\s*--\s*(.+?)\s*$')


def norm(s):
    return re.sub(r"[^a-z0-9]", "", s.lower())


def project(p0, p1, region, size, anchor):
    min_x, min_y, max_x, max_y = region
    x = size * (max_y - p1) / (max_y - min_y) + anchor[0]
    y = size * (max_x - p0) / (max_x - min_x) + anchor[1]
    return x, y


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("taxinodes")
    ap.add_argument("markers")
    ap.add_argument("--region", type=float, nargs=4, required=True,
                    metavar=("MIN_X", "MIN_Y", "MAX_X", "MAX_Y"),
                    help="UiMapAssignment Region_0 Region_1 Region_3 Region_4")
    ap.add_argument("--size", type=float, default=512)
    ap.add_argument("--anchor", type=float, nargs=2, default=(0, 0), metavar=("X", "Y"))
    ap.add_argument("--continent", type=int, help="only TaxiNodes with this ContinentID")
    a = ap.parse_args()

    by_name = {}
    all_nodes = []
    with open(a.taxinodes, newline="", encoding="utf-8-sig") as f:
        for r in csv.DictReader(f):
            if a.continent is not None and int(r["ContinentID"]) != a.continent:
                continue
            name = r["Name_lang"].partition(", ")[0]
            by_name.setdefault(norm(name), []).append(r)
            px, py = project(float(r["Pos_0"]), float(r["Pos_1"]), a.region, a.size, a.anchor)
            all_nodes.append((px, py, r["ID"], r["Name_lang"]))

    def nearest(mx, my):
        best = None
        for px, py, tid, full in all_nodes:
            d = math.hypot(mx - px, my - py)
            if best is None or d < best[0]:
                best = (d, tid, full)
        return best

    rows = []
    with open(a.markers, encoding="utf-8-sig") as f:
        for line in f:
            m = ROW.match(line)
            if m:
                rows.append((m.group(1).strip('"'), int(m.group(2)), float(m.group(3)), float(m.group(4)), m.group(5)))

    diffs = []
    print("%-5s %-24s %16s %16s %14s %6s  %s" % ("label", "name", "manual", "projected", "dx, dy", "dist", "TaxiNodes"))
    for label, bid, mx, my, name in rows:
        cands = by_name.get(norm(name), [])
        near = nearest(mx, my)
        if not cands:
            hint = "  nearest: %s %s, %.1f px" % (near[1], near[2], near[0]) if near else ""
            print("%-5s %-24s %16s   no TaxiNodes match%s" % (label, name[:24], "%.1f, %.1f" % (mx, my), hint))
            continue
        scored = []
        for r in cands:
            px, py = project(float(r["Pos_0"]), float(r["Pos_1"]), a.region, a.size, a.anchor)
            scored.append((math.hypot(mx - px, my - py), px, py, r["ID"]))
        scored.sort()
        d, px, py, tid = scored[0]
        others = "" if len(scored) == 1 else "  (also: " + ", ".join("%s %.1f px" % (s[3], s[0]) for s in scored[1:]) + ")"
        if near and near[1] != tid and near[0] < d:
            others += "  nearest: %s %s, %.1f px" % (near[1], near[2], near[0])
        diffs.append((mx - px, my - py))
        print("%-5s %-24s %16s %16s %14s %6.1f  %s%s" % (
            label, name[:24], "%.1f, %.1f" % (mx, my), "%.1f, %.1f" % (px, py),
            "%+.1f, %+.1f" % (mx - px, my - py), d, tid, others))

    if diffs:
        n = len(diffs)
        mean = (sum(d[0] for d in diffs) / n, sum(d[1] for d in diffs) / n)
        rms = math.sqrt(sum(math.hypot(d[0], d[1]) ** 2 for d in diffs) / n)
        rms_c = math.sqrt(sum(math.hypot(d[0] - mean[0], d[1] - mean[1]) ** 2 for d in diffs) / n)
        print()
        print("matched %d, mean shift %+.1f, %+.1f px, rms %.1f px, rms after removing the mean shift %.1f px" % (
            n, mean[0], mean[1], rms, rms_c))


if __name__ == "__main__":
    main()
