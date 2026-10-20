#!/usr/bin/env python3
"""Dump the map coords that an Atlas module builds at load time.

Runs the module's Lua data files in a stubbed WoW environment (via lupa) and
writes one .lua file per map, in the same format as psd_text_extract.jsx:

    TransAllianceEast_Forever = {
        { "A", 20001, 13, 93 }, -- Orange
        ...
    },

The trailing comment is the marker tag (field 7), used by psd_text_import.jsx
to colour the generated text layers.

Requires: pip install lupa

Usage:
  python atlas_coords_dump.py C:\\Work\\GitRepos\\Atlas\\Atlas-Transportation --client forever --out out
  python atlas_coords_dump.py <module folder> --client forever --map TransAllianceEast_Forever
"""
import argparse
import os
import re
import sys

try:
    import lupa
except ImportError:
    sys.exit("lupa is required: pip install lupa")

CLIENT_FLAGS = {
    "retail": ["isRetail"],
    "era": ["isClassicEra", "isAnyClassic"],
    "tbc": ["isTBCClassic", "isAnyClassic"],
    "anniversary": ["isAnniversaryTBC", "isAnyClassic"],
    "progression": ["isProgressionClassic", "isAnyClassic"],
    "forever": ["isForever"],
}

STUBS = r"""
unpack = unpack or table.unpack
getfenv = function() return _G end

-- Any unknown global (FACTION_ALLIANCE, WORLD, ...) resolves to its own name.
setmetatable(_G, { __index = function(_, k) return k end })

local echo = setmetatable({}, { __index = function(_, k) return k end })
local escapes = setmetatable({}, { __index = function(_, k) return "" end })
local Client = {}
for _, flag in ipairs(CLIENT_FLAGS) do Client[flag] = true end

local Atlas = { Client = Client, constants = { colors = { labels = escapes, classes = escapes } } }
setmetatable(Atlas, { __index = function() return function() return "" end end })

LibStub = setmetatable({}, { __call = function(_, name)
	if name == "AceAddon-3.0" then
		return { GetAddon = function() return Atlas end, NewAddon = function() return {} end }
	end
	return { GetLocale = function() return echo end, New = function() return {} end }
end })
Atlas_GetLocaleLibBabble = function() return echo end

ATLAS_FONT_COLORS = {
	White = true, Yellow = true, Green = true, Red = true, Orange = true, Purple = true, Blue = true,
	Alliance = true, Horde = true, Neutral = true,
}
RAID_CLASS_COLORS = {}
UnitFactionGroup = function() return "Alliance", "Alliance" end
Atlas_GetClassName = function(name) return name end
C_QuestLog = { IsQuestFlaggedCompleted = function() return false end }
PRIVATE = {}
"""


def data_files(module_dir):
    xml = os.path.join(module_dir, "Data", "Data.xml")
    with open(xml, encoding="utf-8-sig") as f:
        names = re.findall(r'<Script\s+file="([^"]+)"', f.read())
    return [os.path.join(module_dir, "Data", n.replace("\\", os.sep)) for n in names]


def lua_string(s):
    return '"' + str(s).replace("\\", "\\\\").replace('"', '\\"') + '"'


def fmt_num(v):
    v = float(v)
    return str(int(v)) if v.is_integer() else ("%g" % v)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("module_dir", help="addon folder, e.g. Atlas-Transportation")
    ap.add_argument("--client", default="forever", choices=sorted(CLIENT_FLAGS))
    ap.add_argument("--out", default=".", help="output folder")
    ap.add_argument("--map", action="append", help="only these maps (repeatable)")
    a = ap.parse_args()

    L = lupa.LuaRuntime(unpack_returned_tuples=True)
    L.globals().CLIENT_FLAGS = L.table(*CLIENT_FLAGS[a.client])
    L.execute(STUBS)
    run = L.eval("function(src, name) local f, e = load(src, '@' .. name); if not f then error(e) end; f('addon', PRIVATE) end")

    files = [os.path.join(a.module_dir, "Core", "Constants.lua")]
    taxi = os.path.join(a.module_dir, "Core", "TaxiCoords.lua")
    if os.path.exists(taxi):
        files.append(taxi)
    files += data_files(a.module_dir)
    for path in files:
        with open(path, encoding="utf-8-sig") as f:
            run(f.read(), os.path.basename(path))

    private = L.globals().PRIVATE
    maps = {}
    for group in ("data", "alliance", "horde"):
        g = private[group]
        if g is not None and g.coords is not None:
            for name, rows in g.coords.items():
                maps[str(name)] = rows

    os.makedirs(a.out, exist_ok=True)
    wanted = set(a.map or maps.keys())
    count = 0
    for name in sorted(wanted):
        rows = maps.get(name)
        if rows is None:
            print("not found:", name)
            continue
        lines = ["    %s = {" % name]
        for i in range(1, len(rows) + 1):
            r = rows[i]
            if r is None:
                continue
            line = "        { %s, %s, %s, %s }," % (lua_string(r[1]), r[2], fmt_num(r[3]), fmt_num(r[4]))
            if r[7] is not None:
                line += " -- " + str(r[7])
            lines.append(line)
        lines.append("    },")
        out = os.path.join(a.out, name + ".lua")
        with open(out, "w", encoding="utf-8", newline="\r\n") as f:
            f.write("\n".join(lines) + "\n")
        count += 1
    print("wrote %d map(s) to %s" % (count, os.path.abspath(a.out)))


if __name__ == "__main__":
    main()
