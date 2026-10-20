# PSD Text Extract (Atlas map markers)

[psd_text_extract.jsx](./psd_text_extract.jsx) is a Photoshop script that exports the visible text layers of a PSD as a Lua table of map markers, for use with the Atlas addon in World of Warcraft.

Based on [Export All Text Layers](https://github.com/pivanov/photoshop-scripts) by pivanov.

## Output

The result is saved next to the PSD, with the same name and a `.lua` extension. For `BlackrockMountainEnt.psd`:

```lua
    BlackrockMountainEnt = {
        { "A", 10001, 271, 182 }, -- blue
        { "B", 10002, 305, 240 }, -- purple
    },
```

| Element | Meaning |
|---------|---------|
| Table name | PSD file name without extension |
| 1st | Text of the layer |
| 2nd | Sequence number, starting at `10001`, assigned after sorting |
| 3rd / 4th | X / Y in px of the text's top-left corner, from the document's top-left (layer effects such as stroke, glow and shadow are ignored, matching the Properties panel). If the canvas is 1024x1024, the values are divided by 2 to match the original 512x512 design, keeping one decimal (e.g. 241, 920 becomes 120.5, 460). |
| Comment | Approximate name of the text color (black, white, gray, red, orange, yellow, green, cyan, blue, purple, pink, brown), useful for telling apart layers with the same text. Omitted if the color can't be read (e.g. mixed styles). |

### Details

- Only **visible** text layers are exported, including those inside visible groups. Empty text is skipped.
- Sort order: letters (`A`, `B`, ...), then numbers (`1`, `2`, `1'`, `2'`), then anything else.
- Typographic quotes, primes and dashes are converted back to ASCII (`'`, `"`, `-`). Line breaks become spaces.
- The file is written as UTF-8.

## Requirements

- Adobe Photoshop (the script uses `#target photoshop`).

## Installation

Copy `psd_text_extract.jsx` to the Photoshop `Presets/Scripts` folder and restart Photoshop. It will then appear under *File* > *Scripts*.

Alternatively, run it without installing via *File* > *Scripts* > *Browse...*.

## Usage

1. Open the PSD in Photoshop.
2. Run the script.
3. If the PSD has been saved, you are asked whether to process every `.psd` in its folder:
   - **Yes**: batch mode. Each PSD is exported to its own `.lua` file, and files that were not already open are closed again without saving. A summary of the entry count per file is shown at the end.
   - **No**: only the active document is exported.
4. For a document that has never been saved, you are asked where to save the `.lua` file, and its name is used as the table name.

An alert shows the output path and number of entries when done.

## Configuration

Edit the constants at the top of the script:

- `START_ID`: first sequence number (default `10001`).
- `INDENT`: indentation used in the output (default 4 spaces).
