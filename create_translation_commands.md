Shortest checklist:

1. Mark strings

* Wrap UI text with `_()`; set i18n at startup:

  * domain: `io.github.fastrizwaan.WineCharm`
  * `LOCALE_DIR`: `winecharm/locale` (inside package)

2. Extract POT

```bash
cd ~/WineCharm
find src/winecharm -name "*.py" | xargs xgettext -k_ -kN_ -o po/winecharm.pot
```

3. Create a PO (first time per language)

```bash
msginit -i po/winecharm.pot -o po/hi.po --locale=hi_IN
```

4. Update an existing PO (when strings change)

```bash
msgmerge --update po/hi.po po/winecharm.pot
```

5. Translate `po/hi.po` (edit file)

6. Compile to `.mo` **inside package**

```bash
mkdir -p src/winecharm/locale/hi/LC_MESSAGES
msgfmt po/hi.po -o src/winecharm/locale/hi/LC_MESSAGES/io.github.fastrizwaan.WineCharm.mo
```

7. Include `.mo` in wheel (in `pyproject.toml`)

```toml
[tool.setuptools.package-data]
winecharm = ["data/**/*", "locale/*/LC_MESSAGES/*.mo"]
```

8. Build & install

```bash
rm -rf build dist src/winecharm.egg-info
python -m build
pip install --force-reinstall dist/*.whl
```

9. Test

```bash
LANG=hi_IN.UTF-8 winecharm
# (or) LANGUAGE=hi winecharm
```

