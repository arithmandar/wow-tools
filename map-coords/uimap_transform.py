#!/usr/bin/env python3
"""Print Atlas transform settings from UiMap.csv and UiMapAssignment.csv.

The taxi maps are the UiMap rows with System = 1. Their UiMapAssignment row
gives the world bounds that the 512x512 taxi map image covers, which is the
exact projection the game uses for TaxiNodes positions.

Usage:
  python uimap_transform.py UiMap.csv UiMapAssignment.csv                # list taxi maps (System = 1)
  python uimap_transform.py UiMap.csv UiMapAssignment.csv --system 0     # world maps
  python uimap_transform.py UiMap.csv UiMapAssignment.csv --id 1463 --id 1464
  python uimap_transform.py ... --size 512 --anchor -6 -4
"""
import argparse
import csv


def read(path):
    with open(path, newline="", encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def num(v):
    f = float(v)
    return str(int(f)) if f.is_integer() else ("%.4f" % f).rstrip("0").rstrip(".")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("uimap")
    ap.add_argument("assignment")
    ap.add_argument("--id", type=int, action="append", help="UiMapID (repeatable)")
    ap.add_argument("--system", type=int, default=1, help="UiMap.System to list when --id is not given (1 = taxi map)")
    ap.add_argument("--size", type=int, default=512)
    ap.add_argument("--anchor", type=float, nargs=2, default=(-6, -4), metavar=("X", "Y"),
                    help="pixel shift; -6 -4 centres a 12x12 normal-map button on the node")
    ap.add_argument("--snap", type=float, default=0.5)
    a = ap.parse_args()

    maps = {int(r["ID"]): r for r in read(a.uimap)}
    assigns = {}
    for r in read(a.assignment):
        assigns.setdefault(int(r["UiMapID"]), []).append(r)

    ids = a.id or sorted(i for i, r in maps.items() if int(r.get("System") or 0) == a.system)
    for uid in ids:
        m = maps.get(uid)
        name = m["Name_lang"] if m else "?"
        rows = sorted(assigns.get(uid, []), key=lambda r: int(r["OrderIndex"]))
        print("-- UiMap %d %s (System %s, Type %s)" % (uid, name, m.get("System") if m else "?", m.get("Type") if m else "?"))
        if not rows:
            print("--   no UiMapAssignment rows\n")
            continue
        if len(rows) > 1:
            print("--   %d UiMapAssignment rows; each covers part of the map, pick the one for your nodes" % len(rows))
        for r in rows:
            region = [r["Region_0"], r["Region_1"], r["Region_3"], r["Region_4"]]
            ui = [r["UiMin_0"], r["UiMin_1"], r["UiMax_0"], r["UiMax_1"]]
            full = [float(v) for v in ui] == [0, 0, 1, 1]
            w = float(region[2]) - float(region[0])
            h = float(region[3]) - float(region[1])
            parts = ["region = { %s }" % ", ".join(num(v) for v in region)]
            if not full:
                parts.append("ui = { %s }" % ", ".join(num(v) for v in ui))
            parts.append("size = %d" % a.size)
            if a.anchor[0] or a.anchor[1]:
                parts.append("anchorX = %s, anchorY = %s" % (num(a.anchor[0]), num(a.anchor[1])))
            parts.append("snap = %s" % num(a.snap))
            print("--   OrderIndex %s, MapID %s, AreaID %s, world %.0f x %.0f yd%s" % (
                r["OrderIndex"], r["MapID"], r["AreaID"], w, h, "" if abs(w - h) < 1 else " (not square)"))
            print("\ttransform = { %s }," % ", ".join(parts))
        print()


if __name__ == "__main__":
    main()
