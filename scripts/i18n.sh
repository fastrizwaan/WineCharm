#!/usr/bin/env sh
set -eu

DOMAIN="io.github.fastrizwaan.WineCharm"
POT="po/winecharm.pot"
SRC_DIR="src/winecharm"
LOCALE_BASE="src/winecharm/locale"

usage() {
    cat <<EOF
Usage:
  $0 extract
  $0 init <lang>
  $0 update <lang>
  $0 update-all
  $0 compile <lang>
  $0 compile-all
EOF
}

require_cmd() {
    command -v "$1" >/dev/null 2>&1 || {
        echo "Missing required command: $1" >&2
        exit 1
    }
}

extract() {
    require_cmd xgettext
    mkdir -p po
    find "$SRC_DIR" -name "*.py" -print0 | xargs -0 xgettext -k_ -kngettext:1,2 -o "$POT"
    echo "Updated $POT"
}

init_lang() {
    require_cmd msginit
    lang="$1"
    [ -f "$POT" ] || extract
    [ -f "po/$lang.po" ] && {
        echo "po/$lang.po already exists" >&2
        exit 1
    }
    msginit --no-translator -l "$lang" -i "$POT" -o "po/$lang.po"
    if ! grep -qx "$lang" po/LINGUAS 2>/dev/null; then
        printf '%s\n' "$lang" >> po/LINGUAS
    fi
    echo "Created po/$lang.po"
}

update_lang() {
    require_cmd msgmerge
    lang="$1"
    [ -f "$POT" ] || extract
    [ -f "po/$lang.po" ] || {
        echo "po/$lang.po not found" >&2
        exit 1
    }
    msgmerge --update --backup=none "po/$lang.po" "$POT"
    echo "Updated po/$lang.po"
}

update_all() {
    [ -f po/LINGUAS ] || {
        echo "po/LINGUAS not found" >&2
        exit 1
    }
    extract
    for lang in $(cat po/LINGUAS); do
        update_lang "$lang"
    done
}

compile_lang() {
    require_cmd msgfmt
    lang="$1"
    [ -f "po/$lang.po" ] || {
        echo "po/$lang.po not found" >&2
        exit 1
    }
    out_dir="$LOCALE_BASE/$lang/LC_MESSAGES"
    mkdir -p "$out_dir"
    msgfmt "po/$lang.po" -o "$out_dir/$DOMAIN.mo"
    echo "Compiled $out_dir/$DOMAIN.mo"
}

compile_all() {
    [ -f po/LINGUAS ] || {
        echo "po/LINGUAS not found" >&2
        exit 1
    }
    for lang in $(cat po/LINGUAS); do
        compile_lang "$lang"
    done
}

cmd="${1:-}"
case "$cmd" in
    extract)
        extract
        ;;
    init)
        [ $# -eq 2 ] || { usage; exit 1; }
        init_lang "$2"
        ;;
    update)
        [ $# -eq 2 ] || { usage; exit 1; }
        update_lang "$2"
        ;;
    update-all)
        update_all
        ;;
    compile)
        [ $# -eq 2 ] || { usage; exit 1; }
        compile_lang "$2"
        ;;
    compile-all)
        compile_all
        ;;
    *)
        usage
        exit 1
        ;;
esac
