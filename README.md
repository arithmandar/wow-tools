# WoW Data Utilities

Small standalone scripts for preparing and generating World of Warcraft map,
area-table, and addon-locale data, plus a small browser extension for
collecting links. They are not an automatically chained pipeline; run the
utility that matches the data you are processing.

## Requirements

- Python 3.9 or newer for the Python scripts.
- [Pillow](https://pypi.org/project/Pillow/) is required only by
  `join-map-tiles.py`:

  ```powershell
  python -m pip install Pillow
  ```

- `join-map-tiles.ps1` uses Windows PowerShell/.NET `System.Drawing` and has no
  Python dependency.
- The other Python scripts use only the Python standard library.

Run commands from this directory, or provide paths to the scripts and data
files. Quote paths that contain spaces.

## Tools

### Join numbered map tiles

`join-map-tiles.py` and `join-map-tiles.ps1` assemble numbered PNG tiles into a
single PNG. Both expect filenames consisting of the supplied prefix, a
contiguous zero-based number, and `.png` (for example, `tile0.png` through
`tile149.png`). Tiles are placed left-to-right, then top-to-bottom. Every tile
must have the same dimensions, and the number of tiles must equal
`columns × rows`.

Python example:

```powershell
python .\join-map-tiles.py `
  --directory ".\tiles" `
  --prefix "tile" `
  --output ".\map.png" `
  --columns 15 `
  --rows 10
```

PowerShell example:

```powershell
.\join-map-tiles.ps1 `
  -Directory ".\tiles" `
  -Prefix "tile" `
  -OutputPath ".\map.png" `
  -Columns 15 `
  -Rows 10
```

The dimensions default to 15 columns by 10 rows in both scripts. The output
must have a `.png` extension. An existing output file may be overwritten.

### Convert an AreaTable CSV to Lua

`csv_to_lua_area_table.py` reads the first column as the area ID and the third
column as the area name. It skips the header, rows without both values, and
rows with fewer than three columns, then sorts entries by numeric ID. It
writes a `MapData.AreaToID` Lua table beside the CSV, using the same filename
with a `.lua` extension. An existing output file is overwritten.

```powershell
python .\csv_to_lua_area_table.py ".\AreaTable.csv"
```

If the CSV path is omitted, the script prompts for it. The CSV is expected to
have the ID in column 1 and the localized area name in column 3.

### Generate or update locale Lua files

`sync_locale_from_txt.py` uses an addon’s `<Addon>-enUS.lua` file as the
reference structure and translation `.txt` files as input. Each translation
file should contain Lua assignments such as:

```lua
L = L or {}
L["key"] = "translated value"
```

Pass one or more translation files or directories. If omitted, the script
looks for `.txt` files beside the reference file. Each input produces or
updates a sibling `<Addon>-<locale>.lua` file, where the locale comes from the
translation filename (for example, `frFR.txt` produces `Addon-frFR.lua`).
Comments, blank lines, and key order come from the English reference. Keys
without a translation are left commented out with their English value, and
the script reports missing keys. Existing locale files retain their own
header and footer while the locale block body is regenerated.

```powershell
python .\sync_locale_from_txt.py ".\MyAddon-enUS.lua" ".\translations"
```

You can also pass individual files:

```powershell
python .\sync_locale_from_txt.py `
  ".\MyAddon-enUS.lua" `
  ".\frFR.txt" `
  ".\deDE.txt"
```

### Replace Lua table lookups with local constants

`use_local_constants.py` replaces references such as `ALC["Comma"]` with a
matching local constant declared in the Lua file, such as
`local COMMA = ALC["Comma"]`. It accepts individual files and directories
(directories are searched recursively for `.lua` files). By default it only
reports the number of replacements that would be made.

Preview changes:

```powershell
python .\use_local_constants.py ".\MyAddon"
```

Write changes in place:

```powershell
python .\use_local_constants.py ".\MyAddon" --write
```

Limit replacements to a table (repeat `--table` to select more than one):

```powershell
python .\use_local_constants.py ".\MyAddon" --table ALC --write
```

Review the dry-run output before using `--write`; this script modifies the
selected Lua files in place.

### Collect links in the browser (Link Collector)

[`link-collector/`](link-collector) is a Chrome (Manifest V3) extension, also
usable in Edge and Brave, for building a list of link texts and URLs. Load it
via `chrome://extensions` → Developer mode → **Load unpacked**. Right-click a
link and choose **Save link text + URL**; repeat for as many links as needed,
then choose **Export saved links to text file** to download `links.txt` with
one `text<TAB>URL` line per link. See
[`link-collector/README.md`](link-collector/README.md) for details.

## Notes

- These scripts are independent command-line helpers; their outputs are not
  automatically passed between tools.
- Check the output paths before running a tool if you need to preserve files
  from an earlier run.
