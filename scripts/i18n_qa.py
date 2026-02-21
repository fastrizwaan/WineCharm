#!/usr/bin/env python3
"""Run translation QA checks for PO files.

Checks:
- msgfmt syntax/format validation
- placeholder consistency against source strings
"""

from __future__ import annotations

import argparse
import ast
import collections
import re
import subprocess
import sys
from pathlib import Path


PLACEHOLDER_RE = re.compile(
    r"%\([^)]+\)[#0\- +]?\d*(?:\.\d+)?[a-zA-Z]|"
    r"%[sdif]|"
    r"\{[^{}]*\}|"
    r"%%[A-Z_]+%%"
)


def parse_args():
    parser = argparse.ArgumentParser(description="Validate PO files.")
    parser.add_argument("--lang", help="Locale code, e.g. fr or pt_BR.")
    parser.add_argument("--all", action="store_true", help="Process all locales from po/LINGUAS.")
    return parser.parse_args()


def parse_po_string(lines, start, key):
    prefix = key + " "
    raw = [lines[start][len(prefix):].rstrip("\n")]
    idx = start + 1
    while idx < len(lines) and lines[idx].startswith('"'):
        raw.append(lines[idx].rstrip("\n"))
        idx += 1
    return "".join(ast.literal_eval(x) for x in raw), idx


def placeholder_counter(text):
    return collections.Counter(PLACEHOLDER_RE.findall(text))


def run_msgfmt_check(po_path):
    cmd = ["msgfmt", "--check", "--check-format", "-o", "/dev/null", str(po_path)]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode == 0:
        return []
    output = (proc.stdout or "") + (proc.stderr or "")
    return [line for line in output.splitlines() if line.strip()]


def check_placeholders(po_path):
    lines = po_path.read_text(encoding="utf-8").splitlines(keepends=True)
    idx = 0
    issues = []

    while idx < len(lines):
        if not lines[idx].startswith("msgid "):
            idx += 1
            continue

        block_line = idx + 1
        msgid, idx = parse_po_string(lines, idx, "msgid")
        if msgid == "":
            continue

        msgid_plural = None
        if idx < len(lines) and lines[idx].startswith("msgid_plural "):
            msgid_plural, idx = parse_po_string(lines, idx, "msgid_plural")

        if idx < len(lines) and lines[idx].startswith("msgstr "):
            msgstr, idx = parse_po_string(lines, idx, "msgstr")
            if msgstr.strip():
                expected = placeholder_counter(msgid)
                actual = placeholder_counter(msgstr)
                if expected != actual:
                    issues.append(
                        "{}:{} placeholder mismatch msgstr expected={} actual={} msgid={!r}".format(
                            po_path, block_line, dict(expected), dict(actual), msgid
                        )
                    )
            continue

        if idx < len(lines) and lines[idx].startswith("msgstr["):
            while idx < len(lines) and lines[idx].startswith("msgstr["):
                key = lines[idx].split(" ", 1)[0]
                plural_index = int(key[key.find("[") + 1:key.find("]")])
                msgstrn, idx = parse_po_string(lines, idx, key)
                if not msgstrn.strip():
                    continue
                source_text = msgid if plural_index == 0 else (msgid_plural or msgid)
                expected = placeholder_counter(source_text)
                actual = placeholder_counter(msgstrn)
                if expected != actual:
                    issues.append(
                        "{}:{} placeholder mismatch {} expected={} actual={} msgid={!r}".format(
                            po_path, block_line, key, dict(expected), dict(actual), source_text
                        )
                    )
            continue

    return issues


def get_locales_from_linguas():
    linguas = Path("po/LINGUAS")
    if not linguas.exists():
        return []
    locales = []
    for line in linguas.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        locales.append(line)
    return locales


def main():
    args = parse_args()
    if args.all:
        locales = get_locales_from_linguas()
    elif args.lang:
        locales = [args.lang]
    else:
        print("Use --lang <locale> or --all.", file=sys.stderr)
        return 2

    if not locales:
        print("No locales selected.", file=sys.stderr)
        return 2

    failures = 0
    for locale in locales:
        po_path = Path("po") / (locale + ".po")
        if not po_path.exists():
            print("{}: skipped (missing {})".format(locale, po_path))
            continue

        msgfmt_issues = run_msgfmt_check(po_path)
        ph_issues = check_placeholders(po_path)
        issue_count = len(msgfmt_issues) + len(ph_issues)
        if issue_count == 0:
            print("{}: OK".format(locale))
            continue

        failures += issue_count
        print("{}: {} issue(s)".format(locale, issue_count))
        for issue in msgfmt_issues:
            print("  {}".format(issue))
        for issue in ph_issues:
            print("  {}".format(issue))

    if failures:
        print("qa: FAIL ({} issue(s))".format(failures))
        return 1
    print("qa: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
