#!/usr/bin/env python3
"""Convert an AreaTable CSV export into a Lua MapData.AreaToID table.

Reads the 1st column (ID) and 3rd column (AreaName_lang) of the input CSV
and writes a Lua table in the form:

    MapData.AreaToID = {
        ["Dun Morogh"] = 1,
        ...
    }

Usage:
    python csv_to_lua_area_table.py [path\\to\\AreaTable.csv]

If no path is given as a command-line argument, the script will prompt
for it. The output .lua file is written next to the input file, with
the same base name and a .lua extension.
"""

import csv
import os
import sys


def escape_lua_string(value):
    return value.replace("\\", "\\\\").replace('"', '\\"')


def convert(input_path):
    output_path = os.path.splitext(input_path)[0] + ".lua"

    rows = []
    with open(input_path, "r", encoding="utf-8-sig", newline="") as csv_file:
        reader = csv.reader(csv_file)
        header = next(reader, None)
        for row in reader:
            if len(row) < 3:
                continue
            area_id = row[0].strip()
            area_name = row[2].strip()
            if not area_id or not area_name:
                continue
            rows.append((area_name, area_id))

    rows.sort(key=lambda row: int(row[1]))

    with open(output_path, "w", encoding="utf-8", newline="\r\n") as lua_file:
        lua_file.write("MapData.AreaToID = {\n")
        for area_name, area_id in rows:
            lua_file.write('\t["%s"] = %s,\n' % (escape_lua_string(area_name), area_id))
        lua_file.write("}\n")

    return output_path


def main():
    if len(sys.argv) > 1:
        input_path = sys.argv[1]
    else:
        input_path = input("Enter path to the input CSV file: ").strip().strip('"')

    if not input_path:
        print("No input file path provided.")
        sys.exit(1)

    if not os.path.isfile(input_path):
        print("Input file not found: %s" % input_path)
        sys.exit(1)

    output_path = convert(input_path)
    print("Wrote: %s" % output_path)


if __name__ == "__main__":
    main()
