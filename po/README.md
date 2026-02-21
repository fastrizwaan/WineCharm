# WineCharm Translation Guide

WineCharm uses GNU gettext.

## Files

- `po/winecharm.pot`: template with source strings
- `po/<lang>.po`: per-language translations (for example `po/fr.po`)
- `src/winecharm/locale/<lang>/LC_MESSAGES/io.github.fastrizwaan.WineCharm.mo`: compiled translations used at runtime
- `po/LINGUAS`: list of maintained translation languages

## Quick Workflow

1. Regenerate template:
   ```sh
   ./scripts/i18n.sh extract
   ```
2. Add a new language (example: `de`):
   ```sh
   ./scripts/i18n.sh init de
   ```
3. Update existing language:
   ```sh
   ./scripts/i18n.sh update de
   ```
4. Optional MT draft fill:
   ```sh
   ./scripts/i18n.sh mt-fill de
   # or all locales
   ./scripts/i18n.sh mt-fill-all
   ```
5. Run QA checks:
   ```sh
   ./scripts/i18n.sh qa de
   # or all locales
   ./scripts/i18n.sh qa-all
   ```
6. Compile:
   ```sh
   ./scripts/i18n.sh compile de
   ```
7. Test:
   ```sh
   LANGUAGE=de winecharm
   ```

## Contribution Checklist

- Keep placeholders intact (`%s`, `%(name)s`, `%d`, etc.).
- Keep markup/symbols intact when present.
- Machine translation is a draft only; final review should be done by native speakers.
- Run `./scripts/i18n.sh extract` before opening a PR if source strings changed.
- Include both updated `po/<lang>.po` and compiled `.mo` output.
