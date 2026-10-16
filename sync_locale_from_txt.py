#!/usr/bin/env python3
"""Sync WoW addon Lua locale files from an enUS reference + translation .txt dumps.

Given a "<Addon>-enUS.lua" reference file that defines an ordered
`if L then ... end` block of `L["key"] = "value"` entries (using blank
lines and `--` comments as section separators / annotations), and one or
more "<locale>.txt" translation dumps of the form:

    L = L or {}
    L["key"] = "translated value"

this script writes/updates "<Addon>-<locale>.lua" next to the reference
file. Only the body of the `if L then ... end` block is regenerated; the
structure (comments, blank lines, key order, trailing `-- ID` comments) is
copied verbatim from the enUS file, with only the string values swapped
for their translation. Keys with no matching translation keep the English
value as a fallback.

Usage:
    python sync_locale_from_txt.py <path-to-enUS.lua> [txt_file_or_dir ...]

If no txt file/dir arguments are given, the script looks for *.txt files
in the same directory as the enUS.lua file.
"""

import argparse
import os
import re
import sys

LINE_RE = re.compile(
    r'^(?P<indent>[ \t]*)L\[(?P<qkey>"(?:[^"\\]|\\.)*")\]\s*=\s*'
    r'(?P<qval>"(?:[^"\\]|\\.)*")'
    r'(?P<semi>\s*;)?'
    r'(?P<trail>\s*--.*)?\s*$'
)

TXT_LINE_RE = re.compile(
    r'^\s*L\[(?P<qkey>"(?:[^"\\]|\\.)*")\]\s*=\s*(?P<qval>"(?:[^"\\]|\\.)*")\s*;?\s*$'
)


def lua_unescape(quoted):
    return quoted[1:-1]


def parse_translations(txt_path):
    translations = {}
    with open(txt_path, "r", encoding="utf-8-sig") as f:
        for line in f:
            m = TXT_LINE_RE.match(line)
            if not m:
                continue
            translations[lua_unescape(m.group("qkey"))] = m.group("qval")
    return translations


def find_block(lines):
    """Locate the last top-level 'if L then' ... final 'end' block."""
    start_idx = None
    for i, line in enumerate(lines):
        if line.strip() == "if L then":
            start_idx = i
    if start_idx is None:
        raise ValueError("Could not find 'if L then' line.")

    end_idx = None
    for i in range(len(lines) - 1, start_idx, -1):
        if lines[i].strip() == "end":
            end_idx = i
            break
    if end_idx is None:
        raise ValueError("Could not find closing 'end' line.")

    return start_idx, end_idx


def build_body(ref_lines, start_idx, end_idx, translations):
    body = []
    for line in ref_lines[start_idx + 1:end_idx]:
        m = LINE_RE.match(line)
        if not m:
            body.append(line)
            continue
        key = lua_unescape(m.group("qkey"))
        
        if key in translations:
            # Translation exists: output standard active Lua line
            value = translations[key]
            body.append("%sL[%s] = %s%s%s\n" % (
                m.group("indent"), m.group("qkey"), value,
                m.group("semi") or "", m.group("trail") or "",
            ))
        else:
            # Missing translation: keep original English value and comment out the line
            value = m.group("qval")
            body.append("%s-- L[%s] = %s%s%s\n" % (
                m.group("indent"), m.group("qkey"), value,
                m.group("semi") or "", m.group("trail") or "",
            ))
    return body


def build_new_header(ref_lines, start_idx, locale):
    header = []
    for line in ref_lines[:start_idx + 1]:
        line = line.replace("enUS", locale)
        if "NewLocale(" in line:
            line = re.sub(r',\s*true\s*,\s*true\s*\)', ', false)', line)
        header.append(line)
    return header


def sync_locale(ref_path, ref_lines, start_idx, end_idx, txt_path, addon_name):
    locale = os.path.splitext(os.path.basename(txt_path))[0]
    target_path = os.path.join(os.path.dirname(ref_path), "%s-%s.lua" % (addon_name, locale))

    translations = parse_translations(txt_path)
    body = build_body(ref_lines, start_idx, end_idx, translations)

    if os.path.isfile(target_path):
        with open(target_path, "r", encoding="utf-8-sig", newline="") as f:
            target_lines = f.readlines()
        t_start_idx, t_end_idx = find_block(target_lines)
        header = target_lines[:t_start_idx + 1]
        footer = target_lines[t_end_idx:]
    else:
        header = build_new_header(ref_lines, start_idx, locale)
        footer = ref_lines[end_idx:end_idx + 1]

    out_lines = header + body + footer

    with open(target_path, "w", encoding="utf-8", newline="") as f:
        f.writelines(line.rstrip("\r\n") + "\r\n" for line in out_lines)

    ref_keys = [
        lua_unescape(LINE_RE.match(l).group("qkey"))
        for l in ref_lines[start_idx + 1:end_idx]
        if LINE_RE.match(l)
    ]
    missing = [k for k in ref_keys if k not in translations]
    return target_path, len(ref_keys) - len(missing), len(ref_keys), missing


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("reference", help="Path to the <Addon>-enUS.lua reference file")
    parser.add_argument("txt_paths", nargs="*", help="Translation .txt file(s) or a directory containing them")
    args = parser.parse_args()

    ref_path = args.reference
    if not os.path.isfile(ref_path):
        print("Reference file not found: %s" % ref_path)
        sys.exit(1)

    ref_dir = os.path.dirname(ref_path)
    ref_name = os.path.basename(ref_path)
    m = re.match(r'^(?P<addon>.+)-enUS\.lua$', ref_name)
    if not m:
        print("Reference file name must match '<Addon>-enUS.lua'")
        sys.exit(1)
    addon_name = m.group("addon")

    txt_files = []
    if args.txt_paths:
        for p in args.txt_paths:
            if os.path.isdir(p):
                txt_files.extend(
                    os.path.join(p, fn) for fn in sorted(os.listdir(p)) if fn.lower().endswith(".txt")
                )
            else:
                txt_files.append(p)
    else:
        txt_files = [
            os.path.join(ref_dir, fn) for fn in sorted(os.listdir(ref_dir)) if fn.lower().endswith(".txt")
        ]

    if not txt_files:
        print("No translation .txt files found.")
        sys.exit(1)

    with open(ref_path, "r", encoding="utf-8-sig", newline="") as f:
        ref_lines = f.readlines()
    start_idx, end_idx = find_block(ref_lines)

    for txt_path in txt_files:
        if not os.path.isfile(txt_path):
            print("Skipping missing file: %s" % txt_path)
            continue
        target_path, translated_count, total_count, missing = sync_locale(
            ref_path, ref_lines, start_idx, end_idx, txt_path, addon_name
        )
        print("Wrote %s (%d/%d keys translated)" % (target_path, translated_count, total_count))
        if missing:
            print("  Missing translations (kept English): %s" % ", ".join(missing))


if __name__ == "__main__":
    main()
