#!/usr/bin/env python3
"""Join sequentially numbered PNG tiles into a row-major map image."""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

try:
    from PIL import Image
except ModuleNotFoundError as error:
    if error.name != "PIL":
        raise
    raise SystemExit(
        "This script requires Pillow. Install it with: python -m pip install Pillow"
    ) from None


def join_tiles(
    directory: Path,
    prefix: str,
    output_path: Path,
    columns: int,
    rows: int,
) -> tuple[int, int]:
    if columns <= 0 or rows <= 0:
        raise ValueError("Columns and rows must be greater than zero.")
    if output_path.suffix.lower() != ".png":
        raise ValueError("Output path must have a .png extension.")

    tile_pattern = re.compile(rf"^{re.escape(prefix)}(\d+)\.png$", re.IGNORECASE)
    tiles: list[tuple[int, Path]] = []
    for path in directory.iterdir():
        if path.is_file():
            match = tile_pattern.fullmatch(path.name)
            if match:
                tiles.append((int(match.group(1)), path))
    tiles.sort(key=lambda item: item[0])

    expected_count = columns * rows
    if len(tiles) != expected_count:
        raise ValueError(
            f"Expected {expected_count} tiles ({columns} columns x {rows} rows), "
            f"found {len(tiles)}."
        )

    for expected_index, (tile_index, tile_path) in enumerate(tiles):
        if tile_index != expected_index:
            raise ValueError(
                f"Missing tile index {expected_index}; filenames must be "
                "numbered contiguously from 0."
            )
        if tile_path.resolve() == output_path.resolve():
            raise ValueError("Output path must not overwrite an input tile.")

    with Image.open(tiles[0][1]) as first_tile:
        tile_width, tile_height = first_tile.size

    canvas = Image.new(
        "RGBA",
        (tile_width * columns, tile_height * rows),
        (0, 0, 0, 0),
    )
    try:
        for index, (_, tile_path) in enumerate(tiles):
            with Image.open(tile_path) as source:
                if source.size != (tile_width, tile_height):
                    raise ValueError(
                        f"Tile '{tile_path}' has dimensions "
                        f"{source.width}x{source.height}; expected "
                        f"{tile_width}x{tile_height}."
                    )
                with source.convert("RGBA") as tile:
                    x = (index % columns) * tile_width
                    y = (index // columns) * tile_height
                    canvas.paste(tile, (x, y))

        canvas.save(output_path, format="PNG")
    finally:
        canvas.close()

    return tile_width * columns, tile_height * rows


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Join numbered PNG map tiles in row-major order."
    )
    parser.add_argument("--directory", type=Path, required=True, help="Tile folder")
    parser.add_argument("--prefix", required=True, help="Filename prefix before tile number")
    parser.add_argument("--output", type=Path, required=True, help="Output PNG path")
    parser.add_argument("--columns", type=int, default=15, help="Tiles per row (default: 15)")
    parser.add_argument("--rows", type=int, default=10, help="Number of rows (default: 10)")
    args = parser.parse_args()

    if not args.directory.is_dir():
        parser.error(f"tile directory does not exist or is not a directory: {args.directory}")

    output_path = args.output.resolve()
    try:
        width, height = join_tiles(
            args.directory,
            args.prefix,
            output_path,
            args.columns,
            args.rows,
        )
    except (OSError, ValueError) as error:
        parser.error(str(error))

    print(f"Created {output_path} ({width}x{height}).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
