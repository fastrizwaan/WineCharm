#!/usr/bin/env python3
"""Fix placeholder-mismatched translations in PO catalogs.

When msgstr placeholders don't match msgid placeholders, fallback to msgid text
for that entry to keep runtime formatting safe.
"""

from __future__ import annotations

import argparse
import ast
import collections
import json
import re
from pathlib import Path


PLACEHOLDER_RE = re.compile(
    r"%\([^)]+\)[#0\- +]?\d*(?:\.\d+)?[a-zA-Z]|"
    r"%[sdif]|"
    r"\{[^{}]*\}|"
    r"%%[A-Z_]+%%"
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Fix placeholder mismatches in PO files.")
    parser.add_argument("--lang", help="Locale code (e.g. fr)")
    parser.add_argument("--all", action="store_true", help="Process all locales from po/LINGUAS")
    return parser.parse_args()


def parse_po_string(lines: list[str], start: int, key: str) -> tuple[str, int]:
    prefix = f"{key} "
    raw = [lines[start][len(prefix):].rstrip("\n")]
    idx = start + 1
    while idx < len(lines) and lines[idx].startswith('"'):
        raw.append(lines[idx].rstrip("\n"))
        idx += 1
    return "".join(ast.literal_eval(x) for x in raw), idx


def quote_po(text: str) -> str:
    return json.dumps(text, ensure_ascii=False)


def placeholder_counter(text: str) -> collections.Counter[str]:
    return collections.Counter(PLACEHOLDER_RE.findall(text))


def fix_po(path: Path) -> int:
    lines = path.read_text(encoding="utf-8").splitlines(keepends=True)
    out: list[str] = []
    idx = 0
    changes = 0

    while idx < len(lines):
        if not lines[idx].startswith("msgid "):
            out.append(lines[idx])
            idx += 1
            continue

        msgid_start = idx
        msgid, idx = parse_po_string(lines, idx, "msgid")
        out.extend(lines[msgid_start:idx])

        msgid_plural = None
        if idx < len(lines) and lines[idx].startswith("msgid_plural "):
            plural_start = idx
            msgid_plural, idx = parse_po_string(lines, idx, "msgid_plural")
            out.extend(lines[plural_start:idx])

        if idx < len(lines) and lines[idx].startswith("msgstr "):
            msgstr, nxt = parse_po_string(lines, idx, "msgstr")
            expected = placeholder_counter(msgid)
            actual = placeholder_counter(msgstr)
            if msgid and expected != actual:
                out.append(f"msgstr {quote_po(msgid)}\n")
                changes += 1
            else:
                out.extend(lines[idx:nxt])
            idx = nxt
            continue

        if idx < len(lines) and lines[idx].startswith("msgstr["):
            while idx < len(lines) and lines[idx].startswith("msgstr["):
                key = lines[idx].split(" ", 1)[0]
                plural_index = int(key[key.find("[") + 1:key.find("]")])
                msgstrn, nxt = parse_po_string(lines, idx, key)
                source_text = msgid if plural_index == 0 else (msgid_plural or msgid)
                expected = placeholder_counter(source_text)
                actual = placeholder_counter(msgstrn)
                if source_text and expected != actual:
                    out.append(f"{key} {quote_po(source_text)}\n")
                    changes += 1
                else:
                    out.extend(lines[idx:nxt])
                idx = nxt
            continue

    if changes:
        path.write_text("".join(out), encoding="utf-8")
    return changes


def get_locales_from_linguas() -> list[str]:
    linguas = Path("po/LINGUAS")
    if not linguas.exists():
        return []
    locales: list[str] = []
    for line in linguas.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        locales.append(line)
    return locales


def main() -> int:
    args = parse_args()
    if args.all:
        locales = get_locales_from_linguas()
    elif args.lang:
        locales = [args.lang]
    else:
        print("Use --lang <locale> or --all.")
        return 2

    total_changes = 0
    for locale in locales:
        po_path = Path("po") / f"{locale}.po"
        if not po_path.exists():
            print(f"{locale}: skipped (missing {po_path})")
            continue
        changes = fix_po(po_path)
        total_changes += changes
        print(f"{locale}: fixed={changes}")

    print(f"done: fixed={total_changes}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
