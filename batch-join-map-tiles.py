#!/usr/bin/env python3
"""Scan an adventuremap folder and run join-map-tiles.py for every tile set."""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from collections import defaultdict
from pathlib import Path

TILE_RE = re.compile(r"^(.*?)(\d+)\.png$", re.IGNORECASE)
SCRIPT = Path(__file__).with_name("join-map-tiles.py")


def find_jobs(root: Path) -> list[tuple[Path, str, Path]]:
    jobs = []
    for folder in sorted(p for p in root.iterdir() if p.is_dir()):
        prefixes = defaultdict(int)
        for file in folder.iterdir():
            match = TILE_RE.match(file.name)
            if file.is_file() and match:
                prefixes[match.group(1)] += 1
        for prefix in sorted(prefixes):
            # Prefixes such as "am_" are shared by several folders, so fall
            # back to the folder name for the output file in that case.
            name = prefix.rstrip("_")
            if not name or name in ("am",):
                name = f"{folder.name}_{name}".rstrip("_")
            jobs.append((folder, prefix, root / f"{name}.png"))
    return jobs


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--root",
        type=Path,
        default=Path(r"C:\Games\_Data\z_WoW.Tools\interface\adventuremap"),
    )
    parser.add_argument("--dry-run", action="store_true", help="Only print commands")
    args = parser.parse_args()

    failures = 0
    for folder, prefix, output in find_jobs(args.root):
        command = [
            sys.executable, str(SCRIPT),
            "--directory", str(folder),
            "--prefix", prefix,
            "--output", str(output),
        ]
        print(" ".join(f'"{c}"' if " " in c else c for c in command))
        if not args.dry_run and subprocess.run(command).returncode != 0:
            failures += 1
    print(f"Done. {failures} failure(s).")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
