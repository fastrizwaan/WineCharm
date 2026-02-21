#!/usr/bin/env python3
"""Machine-translate untranslated PO entries.

This fills entries where msgstr is empty or still identical to msgid.
It is intentionally a draft generator; run i18n_qa.py and human review after.
"""

from __future__ import annotations

import argparse
import ast
import json
import re
import sys
import time
from pathlib import Path

import requests

try:
    from deep_translator import GoogleTranslator
except ImportError as exc:
    print(
        "Missing dependency: deep-translator. Install with:\n"
        "  pip3 install deep-translator",
        file=sys.stderr,
    )
    raise SystemExit(2) from exc


LOCALE_TARGETS = {
    "fr": "fr",
    "pt_BR": "pt",
    "es": "es",
    "ru": "ru",
    "zh_CN": "zh-CN",
    "ar": "ar",
    "de": "de",
    "ja": "ja",
    "ko": "ko",
    "it": "it",
    "tr": "tr",
    "id": "id",
    "pl": "pl",
}

PLACEHOLDER_RE = re.compile(
    r"%\([^)]+\)[#0\- +]?\d*(?:\.\d+)?[a-zA-Z]|"
    r"%[sdif]|"
    r"\{[^{}]*\}|"
    r"%%[A-Z_]+%%"
)

# Deep-translator uses requests without timeout; force one to avoid hanging.
_orig_get = requests.get


def _timed_get(*args, **kwargs):
    kwargs.setdefault("timeout", 15)
    return _orig_get(*args, **kwargs)


requests.get = _timed_get


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Fill PO files with MT draft strings.")
    parser.add_argument("--lang", help="Locale code, e.g. fr or pt_BR.")
    parser.add_argument("--all", action="store_true", help="Process all known locales.")
    return parser.parse_args()


def parse_po_string(lines, start, key):
    prefix = key + " "
    raw = [lines[start][len(prefix):].rstrip("\n")]
    idx = start + 1
    while idx < len(lines) and lines[idx].startswith('"'):
        raw.append(lines[idx].rstrip("\n"))
        idx += 1
    return "".join(ast.literal_eval(x) for x in raw), idx


def quote_po(text):
    return json.dumps(text, ensure_ascii=False)


def protect_placeholders(text):
    placeholders = []

    def repl(match):
        token = "ZXQPH{}ZXQ".format(len(placeholders))
        placeholders.append(match.group(0))
        return token

    return PLACEHOLDER_RE.sub(repl, text), placeholders


def restore_placeholders(text, placeholders):
    out = text
    for idx, placeholder in enumerate(placeholders):
        out = out.replace("ZXQPH{}ZXQ".format(idx), placeholder)
    return out


def translate_text(translator, text, cache):
    if text in cache:
        return cache[text]
    if not text.strip():
        cache[text] = text
        return text

    protected, placeholders = protect_placeholders(text)
    result = translator.translate(protected)
    if result is None:
        result = text
    result = restore_placeholders(result, placeholders)
    cache[text] = result
    time.sleep(0.02)
    return result


def should_translate(msgid, msgstr):
    if not msgid:
        return False
    if msgstr == "":
        return True
    return msgstr == msgid


def fill_locale(locale, target):
    po_path = Path("po") / (locale + ".po")
    if not po_path.exists():
        print("{}: skipped (missing po/{})".format(locale, po_path.name))
        return 0, 0

    lines = po_path.read_text(encoding="utf-8").splitlines(keepends=True)
    out = []
    translator = GoogleTranslator(source="en", target=target)
    cache = {}

    idx = 0
    changed = 0
    failures = 0
    processed = 0

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
            if should_translate(msgid, msgstr):
                try:
                    translated = translate_text(translator, msgid, cache)
                    out.append("msgstr {}\n".format(quote_po(translated)))
                    changed += 1
                    processed += 1
                except Exception:
                    out.extend(lines[idx:nxt])
                    failures += 1
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
                if should_translate(source_text, msgstrn):
                    try:
                        translated = translate_text(translator, source_text, cache)
                        out.append("{} {}\n".format(key, quote_po(translated)))
                        changed += 1
                        processed += 1
                    except Exception:
                        out.extend(lines[idx:nxt])
                        failures += 1
                else:
                    out.extend(lines[idx:nxt])
                idx = nxt
            continue

    if changed:
        po_path.write_text("".join(out), encoding="utf-8")
    print("{}: translated={} failures={}".format(locale, changed, failures))
    return changed, failures


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
        locales = get_locales_from_linguas() or sorted(LOCALE_TARGETS.keys())
    elif args.lang:
        locales = [args.lang]
    else:
        print("Use --lang <locale> or --all.", file=sys.stderr)
        return 2

    unknown = [loc for loc in locales if loc not in LOCALE_TARGETS]
    if unknown:
        print(
            "Unsupported locale(s): {}. Add mappings in LOCALE_TARGETS.".format(
                ", ".join(unknown)
            ),
            file=sys.stderr,
        )
        return 2

    total_changed = 0
    total_failures = 0
    for locale in locales:
        changed, failures = fill_locale(locale, LOCALE_TARGETS[locale])
        total_changed += changed
        total_failures += failures

    print("done: translated={} failures={}".format(total_changed, total_failures))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
