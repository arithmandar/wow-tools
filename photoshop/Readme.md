# Photoshop tools for Atlas map markers

Scripts for moving map-marker positions between Photoshop and the Atlas addon for World of Warcraft.

| File | Direction | Purpose |
|------|-----------|---------|
| [psd_text_extract.jsx](./psd_text_extract.jsx) | PSD → Lua | Export the visible text layers of a PSD as a Lua marker table. |
| [psd_text_import.jsx](./psd_text_import.jsx) | Lua → PSD | Create text layers in a PSD from a Lua marker table. |
| [atlas_coords_dump.py](./atlas_coords_dump.py) | Atlas → Lua | Dump the coords an Atlas module builds at load time (e.g. from TaxiNodes positions) into per-map Lua files. |

All three use the same file format and the same position convention, so the files can be passed from one to another.

## Marker file format

One Lua table per map, named after the map / PSD:

```lua
    BlackrockMountainEnt = {
        { "A", 10001, 271, 182 }, -- blue
        { "B", 10002, 305, 240 }, -- purple
    },
```

| Element | Meaning |
|---------|---------|
| Table name | Map name, the same as the PSD file name without extension |
| 1st | Text of the marker (`"A"`, `"1"`, ...) |
| 2nd | Button ID |
| 3rd / 4th | X / Y in px of the text's top-left corner, from the top-left of the 512x512 map. Layer effects such as stroke, glow and shadow are ignored, matching the Properties panel. |
| Comment | Colour of the marker. `psd_text_extract.jsx` writes an approximate colour name (`blue`); `atlas_coords_dump.py` writes the Atlas marker tag (`Alliance`, `Orange`). |

The file is UTF-8. The `.lua` file next to a PSD with the same name is where the export writes and where the import reads by default.

## Typical workflows

Hand-drawn markers (instance maps):

1. Place the text layers in Photoshop.
2. Run `psd_text_extract.jsx` and copy the table into the Atlas coords data.

Generated markers (e.g. Atlas Transportation maps built from TaxiNodes):

1. Run `atlas_coords_dump.py` with `--out` pointing at the PSD folder.
2. Open the PSD and run `psd_text_import.jsx`. The nodes appear as text layers in their own group.
3. Draw routes and other artwork against those layers.
4. Hide or delete the generated group before saving the final map image, and before running `psd_text_extract.jsx`.

## psd_text_extract.jsx

Based on [Export All Text Layers](https://github.com/pivanov/photoshop-scripts) by pivanov.

### Usage

1. Open the PSD in Photoshop.
2. Run the script.
3. If the PSD has been saved, you are asked whether to process every `.psd` in its folder:
   - **Yes**: batch mode. Each PSD is exported to its own `.lua` file, and files that were not already open are closed again without saving. A summary of the entry count per file is shown at the end.
   - **No**: only the active document is exported.
4. For a document that has never been saved, you are asked where to save the `.lua` file, and its name is used as the table name.

An alert shows the output path and number of entries when done.

### Details

- Only **visible** text layers are exported, including those inside visible groups. Empty text is skipped.
- IDs start at `10001` and are assigned after sorting.
- Sort order: letters (`A`, `B`, ...), then numbers (`1`, `2`, `1'`, `2'`), then anything else.
- If the canvas is 1024x1024, the values are divided by 2 to match the original 512x512 design, keeping one decimal (e.g. 241, 920 becomes 120.5, 460).
- The colour comment is one of black, white, gray, red, orange, yellow, green, cyan, blue, purple, pink, brown. It is omitted if the colour can't be read (e.g. mixed styles).
- Typographic quotes, primes and dashes are converted back to ASCII (`'`, `"`, `-`). Line breaks become spaces.

### Configuration

Constants at the top of the script:

- `START_ID`: first ID (default `10001`).
- `INDENT`: indentation used in the output (default 4 spaces).

## psd_text_import.jsx

### Usage

1. Open the PSD in Photoshop.
2. Run the script.
3. The `.lua` file next to the PSD with the same name is used. If there is none, you are asked to pick one.
4. The table named like the PSD is used; if there is no such table, the first one in the file.

An alert shows how many layers were created.

### Details

- Each entry becomes a point text layer named `<text> (<ID>)`, for example `1 (10001)`.
- The layer is moved so that its bounds without effects start exactly at X / Y, the same convention the export uses. Exporting again gives the same numbers.
- The colour comes from the marker tag: a 7th string field (`{ "A", 10017, 17, 362, 226, 463, "Blue" }`) or the trailing comment (`-- Alliance`, `-- yellow`). The first letter of a comment is capitalised, so `-- yellow` matches `Yellow`. Colours follow the `ATLAS_FONT_COLORS` values from Atlas (`White`, `Yellow`, `Green`, `Red`, `Orange`, `Purple`, `Blue`, `Alliance`, `Horde`, `Neutral`). Other tags, including the export's `black`, `gray`, `cyan`, `pink` and `brown`, and plain comments such as `-- Ironforge`, use `DEFAULT_COLOR`.
- All layers go into the group `Atlas markers (generated)`. Running the script again replaces that group.
- The whole import is a single history step, so one undo removes it.
- Coordinates are placed as is, which fits a 512x512 canvas.

### Configuration

Constants at the top of the script:

- `GROUP_NAME`: name of the generated group.
- `FONT`: PostScript font name, e.g. `ArialMT`, `Arial-BoldMT`.
- `FONT_SIZE`: text size in px (default `12`).
- `DEFAULT_COLOR`: RGB used when the tag is unknown.
- `COLORS`: tag → RGB table.

## atlas_coords_dump.py

Maps whose coords are generated in Lua, for example by `BuildTransportMap()` / `BuildTaxiCoords()` in Atlas Transportation, have no hand-written table to copy. This script runs the module's `Core/Constants.lua`, `Core/TaxiCoords.lua` and the data files listed in `Data/Data.xml` in a stubbed WoW environment, then writes the resulting coords.

### Requirements

- Python 3.9 or newer
- [lupa](https://pypi.org/project/lupa/) (embedded Lua runtime):

  ```powershell
  python -m pip install lupa
  ```

### Usage

```powershell
# every map of a client into .\out
python .\atlas_coords_dump.py "C:\Work\GitRepos\Atlas\Atlas-Transportation" --client forever --out .\out

# one map, straight into the PSD folder for psd_text_import.jsx
python .\atlas_coords_dump.py "C:\Work\GitRepos\Atlas\Atlas-Transportation" `
  --client forever `
  --map TransAllianceEast_Forever `
  --out "C:\Work\GitRepos\Atlas\Atlas-Transportation\Images\PSD"
```

| Option | Meaning |
|--------|---------|
| `module_dir` | Addon folder, e.g. `Atlas-Transportation` |
| `--client` | `retail`, `era`, `tbc`, `anniversary`, `progression` or `forever` (default `forever`) |
| `--map` | Only this map; repeat for more than one. Default: every map of the client. |
| `--out` | Output folder (default: current folder) |

Each map is written to `<map name>.lua` with CRLF line endings, including both faction tables (`alliance` / `horde`) and shared ones.

### Notes

- WoW API calls and localisation are stubbed: locale lookups return their key, colour escapes are empty. Only the coords are meant to be used.
- Writing into the PSD folder overwrites a `.lua` file of the same name written earlier by `psd_text_extract.jsx`, and the other way round.

## Installing the Photoshop scripts

Copy the `.jsx` files to the Photoshop `Presets/Scripts` folder and restart Photoshop. They will then appear under *File* > *Scripts*.

Alternatively, run them without installing via *File* > *Scripts* > *Browse...*.
