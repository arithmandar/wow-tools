"""Replace inline lookups like ALC["Comma"] with the local constant (COMMA)
declared in the file header as:  local COMMA = ALC["Comma"]

Usage:
    python use_local_constants.py FILE_OR_DIR [...] [--table ALC] [--write]

Without --write it only reports what would change (dry run).
"""
import argparse
import re
import sys
from pathlib import Path

DECL = re.compile(r'^\s*local\s+([A-Za-z_]\w*)\s*=\s*(\w+)\["([^"\n]+)"\]\s*(?:--.*)?$')


def process(text, tables):
    lines = text.split("\n")
    consts = {}  # (table, key) -> name
    decl_lines = set()
    for i, line in enumerate(lines):
        m = DECL.match(line.rstrip("\r"))
        if m and (not tables or m.group(2) in tables):
            consts.setdefault((m.group(2), m.group(3)), m.group(1))
            decl_lines.add(i)
    if not consts:
        return text, 0

    pattern = re.compile(
        r'\b(%s)\["(%s)"\]'
        % ("|".join(map(re.escape, {t for t, _ in consts})),
           "|".join(map(re.escape, {k for _, k in consts})))
    )
    count = 0

    def sub(m):
        nonlocal count
        name = consts.get((m.group(1), m.group(2)))
        if not name:
            return m.group(0)
        count += 1
        return name

    for i, line in enumerate(lines):
        if i not in decl_lines:
            lines[i] = pattern.sub(sub, line)
    return "\n".join(lines), count


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("paths", nargs="+")
    ap.add_argument("--table", action="append", help="only handle this table (repeatable); default: all")
    ap.add_argument("--write", action="store_true")
    args = ap.parse_args()

    files = []
    for p in map(Path, args.paths):
        files += sorted(p.rglob("*.lua")) if p.is_dir() else [p]

    total = 0
    for f in files:
        raw = f.read_bytes().decode("utf-8")
        new, n = process(raw, set(args.table or []))
        if n:
            total += n
            print(f"{f}: {n} replacement(s)")
            if args.write:
                f.write_bytes(new.encode("utf-8"))
    print(f"Total: {total} ({'written' if args.write else 'dry run'})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
