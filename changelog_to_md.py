#!/usr/bin/env python3
"""Convert the Atlas ChangeLog.txt into Markdown."""
import re
import argparse

CODE = re.compile(r"\b[A-Za-z_][\w.:]*\([^()]*\)")


def inline(text):
    out, pos = [], 0
    for m in CODE.finditer(text):
        name = m.group(0).split("(")[0]
        if not re.search(r"[A-Z_.:]", name[1:]):   # plain words such as "mapA(" are left alone
            continue
        out.append(escape(text[pos:m.start()]))
        out.append("`" + m.group(0) + "`")
        pos = m.end()
    out.append(escape(text[pos:]))
    return "".join(out)


def escape(s):
    return re.sub(r"([<>*\\])", r"\\\1", s)


def convert(lines):
    md = []
    items = []          # (depth, text) of the list being collected
    i = 0
    n = len(lines)

    def flush():
        for depth, text in items:
            md.append("  " * depth + "- " + inline(text))
        if items:
            md.append("")
        items.clear()

    # header: everything before the first ===== line
    header = []
    while i < n and not re.fullmatch(r"=+", lines[i].strip()):
        if lines[i].strip():
            header.append(lines[i].strip())
        i += 1
    if header:
        md.append("# " + escape(header[0]))
        md.append("")
        for h in header[1:]:
            md.append("- " + escape(h))
        md.append("")

    while i < n:
        raw = lines[i].rstrip()
        s = raw.strip()
        nxt = lines[i + 1].strip() if i + 1 < n else ""

        # ===== / Title / ===== banners
        if re.fullmatch(r"=+", s):
            i += 1
            continue
        if i + 1 < n and re.fullmatch(r"=+", nxt) and s and i > 0 and re.fullmatch(r"=+", lines[i - 1].strip()):
            flush()
            md.append("## " + escape(s.strip("= ").rstrip(":")))
            md.append("")
            i += 2
            continue

        # version line followed by a dashed underline
        if s and re.fullmatch(r"-{3,}", nxt):
            flush()
            md.append("### " + escape(s))
            md.append("")
            i += 2
            continue

        if not s:
            flush()
            i += 1
            continue

        indent = len(raw) - len(raw.lstrip(" "))
        if s.startswith("- ") or s == "-":
            depth = indent // 2
            prev = items[-1][0] if items else -1
            depth = min(depth, prev + 1)
            items.append((depth, s[2:].strip()))
        elif items:
            d, t = items[-1]
            items[-1] = (d, (t + " " + s).strip())
        else:
            md.append(inline(s))
            md.append("")
        i += 1

    flush()
    while md and md[-1] == "":
        md.pop()
    return "\n".join(md) + "\n"


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Convert the Atlas ChangeLog.txt into Markdown."
    )
    parser.add_argument("src", help="source changelog text file")
    parser.add_argument("dst", help="destination Markdown file")
    args = parser.parse_args()

    src, dst = args.src, args.dst
    with open(src, encoding="utf-8-sig") as f:
        text = f.read().replace("\r\n", "\n").replace("\r", "\n")
    with open(dst, "w", encoding="utf-8", newline="\n") as f:
        f.write(convert(text.split("\n")))
