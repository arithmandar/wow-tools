#!/usr/bin/env python3
"""Convert rows of TaxiNodes.csv into Atlas Transportation node entries.

Usage:
  python taxinodes_to_lua.py TaxiNodes.csv 67 66 43 ...        # TaxiNodes IDs, in legend order
  python taxinodes_to_lua.py TaxiNodes.csv --continent 0       # every node on a continent

Options:
  --kind Alliance      kind written to every entry (default Alliance)
  --start 1            first label number (default 1)
  --button-base 10000  button id = button-base + label number (default 10000)
"""
import argparse, csv, sys

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("csv")
    ap.add_argument("ids", nargs="*", type=int)
    ap.add_argument("--continent", type=int)
    ap.add_argument("--kind", default="Alliance")
    ap.add_argument("--start", type=int, default=1)
    ap.add_argument("--button-base", type=int, default=10000)
    a = ap.parse_args()

    with open(a.csv, newline="", encoding="utf-8-sig") as f:
        rows = {int(r["ID"]): r for r in csv.DictReader(f)}

    if a.ids:
        ids = a.ids
    elif a.continent is not None:
        ids = sorted(i for i, r in rows.items() if int(r["ContinentID"]) == a.continent)
    else:
        sys.exit("give TaxiNodes IDs or --continent")

    for n, tid in enumerate(ids, a.start):
        r = rows.get(tid)
        if not r:
            print(f"\t-- TaxiNodes {tid} not found")
            continue
        name, _, zone = r["Name_lang"].partition(", ")
        zone_part = f'zone = "{zone}", ' if zone else ""
        name = name.replace('"', '\\"')
        print(f'\t\t{{ label = "{n}", id = {a.button_base + n}, kind = "{a.kind}", '
              f'name = "{name}", {zone_part}pos = {{ {r["Pos_0"]}, {r["Pos_1"]} }} }}, -- {tid}')

if __name__ == "__main__":
    main()
