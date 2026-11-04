#!/usr/bin/env python3
"""Stitch exported WMO minimap tiles into one PNG per WMO group.

Exported WMO minimap tiles (world/minimaps/wmo/...) are named

    <wmo>_<group>_<a>_<b>.png      e.g. 9mal_maldraxxus_citadel01_001_01_00.png

where <group> is a three-digit WMO group index and <a>/<b> are two-digit tile
indices inside that group. This script groups the files by <wmo>_<group>,
places each tile on a grid, and writes:

  * <output>/<wmo>/<wmo>_<group>.png   one stitched image per group
  * <output>/<wmo>/_overview.png      every group of that WMO side by side,
                                      labelled, for quick visual inspection

This is "stage 1" only: groups are NOT positioned relative to each other.
Combining groups into a full floor plan needs WMO group bounding boxes.

Tile axis convention is not verified for every build, so it is configurable:
by default <a> is the column (x) and <b> is the row (y), and row 0 is drawn at
the top. Check one known group and use --swap-axes / --flip-x / --flip-y if the
result looks transposed or mirrored; the same options then apply to all groups.
"""

from __future__ import annotations

import argparse
import re
import sys
from collections import defaultdict
from pathlib import Path

try:
    from PIL import Image, ImageDraw
except ImportError:  # pragma: no cover
    sys.exit("Pillow is required: python -m pip install Pillow")

TILE_RE = re.compile(r"^(?P<wmo>.+)_(?P<group>\d{3})_(?P<a>\d{2})_(?P<b>\d{2})\.png$", re.IGNORECASE)


def collect(directory: Path, recursive: bool) -> dict[str, dict[str, dict[tuple[int, int], Path]]]:
    """Return {wmo: {group: {(a, b): path}}}."""
    found: dict[str, dict[str, dict[tuple[int, int], Path]]] = defaultdict(lambda: defaultdict(dict))
    files = directory.rglob("*.png") if recursive else directory.glob("*.png")
    for path in sorted(files):
        m = TILE_RE.match(path.name)
        if m:
            found[m["wmo"].lower()][m["group"]][(int(m["a"]), int(m["b"]))] = path
    return found


def stitch(tiles: dict[tuple[int, int], Path], args: argparse.Namespace) -> Image.Image:
    placed: dict[tuple[int, int], Image.Image] = {}
    for (a, b), path in tiles.items():
        col, row = (b, a) if args.swap_axes else (a, b)
        placed[(col, row)] = Image.open(path).convert("RGBA")

    cols = max(c for c, _ in placed) + 1
    rows = max(r for _, r in placed) + 1
    # Allow uneven tile sizes: each column/row takes its widest/tallest tile.
    default_w, default_h = next(iter(placed.values())).size
    col_w = [default_w] * cols
    row_h = [default_h] * rows
    for (c, r), img in placed.items():
        col_w[c] = max(col_w[c], img.width)
        row_h[r] = max(row_h[r], img.height)

    order_c = list(range(cols))[::-1] if args.flip_x else list(range(cols))
    order_r = list(range(rows))[::-1] if args.flip_y else list(range(rows))
    x_at = {}
    x = 0
    for c in order_c:
        x_at[c] = x
        x += col_w[c]
    y_at = {}
    y = 0
    for r in order_r:
        y_at[r] = y
        y += row_h[r]

    canvas = Image.new("RGBA", (x, y), (0, 0, 0, 0))
    for (c, r), img in placed.items():
        canvas.paste(img, (x_at[c], y_at[r]))
    return canvas


def overview(images: list[tuple[str, Image.Image]], max_width: int) -> Image.Image:
    pad, label_h = 16, 22
    rows: list[list[tuple[str, Image.Image]]] = [[]]
    width = pad
    for item in images:
        w = item[1].width + pad
        if rows[-1] and width + w > max_width:
            rows.append([])
            width = pad
        rows[-1].append(item)
        width += w
    total_w = max(pad + sum(i.width + pad for _, i in row) for row in rows)
    total_h = pad + sum(max(i.height for _, i in row) + label_h + pad for row in rows)
    sheet = Image.new("RGBA", (total_w, total_h), (40, 40, 40, 255))
    draw = ImageDraw.Draw(sheet)
    y = pad
    for row in rows:
        x = pad
        for name, img in row:
            draw.text((x, y), name, fill=(255, 255, 255, 255))
            draw.rectangle([x - 1, y + label_h - 1, x + img.width, y + label_h + img.height], outline=(255, 200, 0, 255))
            sheet.alpha_composite(img, (x, y + label_h))
            x += img.width + pad
        y += max(i.height for _, i in row) + label_h + pad
    return sheet


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("directory", type=Path, help="folder with exported WMO minimap PNG tiles")
    p.add_argument("-o", "--output", type=Path, help="output folder (default: <directory>/_stitched)")
    p.add_argument("-r", "--recursive", action="store_true", help="also scan subfolders")
    p.add_argument("--filter", help="only process WMO names containing this text, e.g. tunnels")
    p.add_argument("--swap-axes", action="store_true", help="treat the first tile index as the row")
    p.add_argument("--flip-x", action="store_true", help="mirror the column order")
    p.add_argument("--flip-y", action="store_true", help="mirror the row order")
    p.add_argument("--no-overview", action="store_true", help="skip the per-WMO overview sheet")
    p.add_argument("--overview-width", type=int, default=4096, help="max overview sheet width in pixels")
    args = p.parse_args()

    if not args.directory.is_dir():
        p.error(f"not a folder: {args.directory}")
    out_root = args.output or args.directory / "_stitched"

    found = collect(args.directory, args.recursive)
    if args.filter:
        found = {k: v for k, v in found.items() if args.filter.lower() in k}
    if not found:
        print("No tiles matching <wmo>_<group>_<a>_<b>.png were found.")
        return 1

    for wmo, groups in sorted(found.items()):
        folder = out_root / wmo
        folder.mkdir(parents=True, exist_ok=True)
        results = []
        for group, tiles in sorted(groups.items()):
            img = stitch(tiles, args)
            name = f"{wmo}_{group}"
            img.save(folder / f"{name}.png")
            results.append((group, img))
            print(f"{name}: {len(tiles)} tile(s) -> {img.width}x{img.height}")
        if not args.no_overview and len(results) > 1:
            overview(results, args.overview_width).save(folder / "_overview.png")
    print(f"Done. Output: {out_root}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
