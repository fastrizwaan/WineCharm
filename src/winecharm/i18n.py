# winecharm/i18n.py
import locale, gettext, os, sys, builtins
from pathlib import Path
import importlib.resources as r

APP_ID = "io.github.fastrizwaan.WineCharm"

# Prefer package-local locale dir
try:
    LOCALE_DIR = str(r.files("winecharm") / "locale")
except Exception:
    LOCALE_DIR = str(Path(__file__).parent / "locale")

def best_lang(env_lang: str | None) -> str:
    if not env_lang:
        return "C"
    lang = env_lang.split(".")[0]  # drop encoding
    cand = Path(LOCALE_DIR) / lang / "LC_MESSAGES" / f"{APP_ID}.mo"
    if cand.exists():
        return lang
    if "_" in lang:
        base = lang.split("_")[0]
        cand = Path(LOCALE_DIR) / base / "LC_MESSAGES" / f"{APP_ID}.mo"
        if cand.exists():
            return base
    return "C"

# Pick LANGUAGE first, then LANG
raw_env_lang = os.environ.get("LANGUAGE") or os.environ.get("LANG")
lang_to_use = best_lang(raw_env_lang)

try:
    locale.setlocale(locale.LC_ALL, raw_env_lang or "")
except locale.Error:
    sys.stderr.write(
        f"[WineCharm] Warning: Locale '{raw_env_lang}' not supported by C library, "
        "falling back to 'C'.\n"
    )
    locale.setlocale(locale.LC_ALL, "C")

gettext.bindtextdomain(APP_ID, LOCALE_DIR)
gettext.textdomain(APP_ID)

# Standard gettext bindings
_ = gettext.gettext
ngettext = gettext.ngettext

# Inject into builtins (global, no per-file imports needed)
builtins._ = _
builtins.ngettext = ngettext

sys.stderr.write(
    f"[WineCharm] Using translations from '{lang_to_use}' (domain: {APP_ID}).\n"
)
