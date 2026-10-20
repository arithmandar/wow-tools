# TaxiNodes and map position tools

Scripts for turning World of Warcraft TaxiNodes world positions into Atlas map coordinates, using the same projection as the game.

| File | Purpose |
|------|---------|
| [taxinodes_to_lua.py](./taxinodes_to_lua.py) | Convert `TaxiNodes.csv` rows into node entries for `BuildTransportMap()`. |
| [uimap_transform.py](./uimap_transform.py) | Read `UiMap.csv` and `UiMapAssignment.csv` and print the `transform` for each taxi map. |
| [compare_coords.py](./compare_coords.py) | Compare hand-placed marker coords with the projected TaxiNodes positions. |

All scripts use only the Python standard library (Python 3.9 or newer). The CSV files are the client DB2 tables exported as CSV, for example from [wago.tools](https://wago.tools/db2).

## How the projection works

`UiMap` rows with `System = 1` are the taxi (flight) maps, for example:

| UiMapID | Name |
|---------|------|
| 1463 | Eastern Kingdoms |
| 1464 | Kalimdor |

Each one has a `UiMapAssignment` row with the world bounds the map image covers:

- `Region_0`, `Region_1`: minimum world X, Y
- `Region_3`, `Region_4`: maximum world X, Y
- `UiMin_0`, `UiMin_1`, `UiMax_0`, `UiMax_1`: the part of the map those bounds fill, usually `0, 0, 1, 1`

World X grows to the north and world Y to the west. A TaxiNodes position (`Pos_0`, `Pos_1`) maps to pixels on a map of `size` pixels as follows:

```
u = UiMin_0 + (UiMax_0 - UiMin_0) * (maxY - Pos_1) / (maxY - minY)
v = UiMin_1 + (UiMax_1 - UiMin_1) * (maxX - Pos_0) / (maxX - minX)
x = size * u + anchorX
y = size * v + anchorY
```

This is implemented in `WorldToMap()` in `Atlas-Transportation/Core/TaxiCoords.lua`, which takes the values directly:

```lua
transform = { region = { -15980, -11880, 5817, 9917 }, size = 512, anchorX = -6, anchorY = -4, snap = 0.5 },
```

`region` is `{ Region_0, Region_1, Region_3, Region_4 }`. `ui` is optional and only needed when it is not `0, 0, 1, 1`.

### Anchor

Atlas places a normal-map button by its top-left corner, and the button is 12x12. Buttons are also anchored 2 px higher than the map texture, so the centre of a button at `(x, y)` is at `(x + 6, y + 4)` on the map image. `anchorX = -6, anchorY = -4` therefore puts the centre of the marker on the node itself.

## taxinodes_to_lua.py

Converts rows of `TaxiNodes.csv` into node entries:

```lua
		{ label = "1", id = 10001, kind = "Alliance", name = "Light's Hope Chapel", zone = "Eastern Plaguelands", pos = { 2271.09, -5340.8 } }, -- 67
```

`Name_lang` is split at the first `, ` into `name` and `zone`. The trailing comment is the TaxiNodes ID.

### Usage

```powershell
# the given TaxiNodes IDs, in legend order
python .\taxinodes_to_lua.py TaxiNodes.csv 67 66 43 14 16 7 6 8 74

# every node on a continent (ContinentID 0 = Eastern Kingdoms, 1 = Kalimdor)
python .\taxinodes_to_lua.py TaxiNodes.csv --continent 1 --kind Horde
```

| Option | Meaning |
|--------|---------|
| `--continent` | Use every node with this `ContinentID` instead of a list of IDs |
| `--kind` | `kind` written to every entry (default `Alliance`) |
| `--start` | First label number (default `1`) |
| `--button-base` | Button ID = button base + label number (default `10000`) |

## uimap_transform.py

Lists the taxi maps and prints a ready-to-paste `transform` for each `UiMapAssignment` row:

```
-- UiMap 1463 Eastern Kingdoms (System 1, Type 2)
--   OrderIndex 0, MapID 0, AreaID 0, world 21797 x 21797 yd
	transform = { region = { -15980, -11880, 5817, 9917 }, size = 512, anchorX = -6, anchorY = -4, snap = 0.5 },
```

### Usage

```powershell
python .\uimap_transform.py UiMap.csv UiMapAssignment.csv
python .\uimap_transform.py UiMap.csv UiMapAssignment.csv --id 1463 --id 1464
python .\uimap_transform.py UiMap.csv UiMapAssignment.csv --system 0 --size 1024 --anchor 0 0
```

| Option | Meaning |
|--------|---------|
| `--id` | Only these UiMapIDs (repeatable) |
| `--system` | `UiMap.System` to list when `--id` is not given (default `1`, taxi maps) |
| `--size` | Map size in pixels (default `512`) |
| `--anchor X Y` | Pixel shift (default `-6 -4`) |
| `--snap` | Rounding step (default `0.5`) |

### Notes

- If a map has more than one `UiMapAssignment` row, each row covers part of the map. Use the one for the area your nodes are in.
- `(not square)` means the world bounds are not square, so the map image is probably not square either. `WorldToMap()` uses a single `size` for both axes, so check the image before using it.

## compare_coords.py

Checks hand-placed coords against the projection. The input is a marker table in the `psd_text_extract.jsx` format, with the node name as the trailing comment:

```lua
        { "7", 10007, 247, 251 }, -- Ironforge
```

Each name is matched against `Name_lang` (the part before `, `), and the world position is projected with the given region:

```
label name                               manual        projected         dx, dy   dist  TaxiNodes
2     Nighthaven                   281.0, 106.0      275.3, 94.4    +5.7, +11.6   12.9  62  nearest: 49 Moonglade, 6.0 px
13    Feathermoon                  158.0, 351.0     154.5, 350.3     +3.5, +0.7    3.5  41
8     Forest Song                  293.0, 188.0   no TaxiNodes match  nearest: 49 Moonglade, 88.0 px

matched 2, mean shift ..., rms ..., rms after removing the mean shift ...
```

- When a name matches several TaxiNodes rows (e.g. the two Booty Bay rows), the nearest one is used and the others are listed.
- `nearest:` is shown when another node is closer than the matched one, or when nothing matches. This helps find markers that were paired with the wrong node.
- A constant `mean shift` usually means the manual coords use a different anchor, e.g. the top-left of the text rather than the node. The rms after removing it is the actual placement error.

### Usage

```powershell
python .\compare_coords.py TaxiNodes.csv TransAllianceWest_Forever.lua --region -11870 -13370 12470 10970 --continent 1
python .\compare_coords.py TaxiNodes.csv TransAllianceEast_Forever.lua --region -15980 -11880 5817 9917 --anchor -6 -4
```

| Option | Meaning |
|--------|---------|
| `--region` | `Region_0 Region_1 Region_3 Region_4` from `UiMapAssignment` (required) |
| `--size` | Map size in pixels (default `512`) |
| `--anchor X Y` | Pixel shift added to the projection (default `0 0`) |
| `--continent` | Only TaxiNodes with this `ContinentID` |

## Related

- [`../photoshop/atlas_coords_dump.py`](../photoshop/atlas_coords_dump.py) dumps the coords Atlas builds at load time, for importing into a PSD with `psd_text_import.jsx`.
