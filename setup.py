from setuptools import setup
from setuptools.command.build_py import build_py as _build_py
import pathlib, polib

DOMAIN = "io.github.fastrizwaan.WineCharm"  # .mo filename
PO_DIR = pathlib.Path("po")
LOCALE_BASE = pathlib.Path("src/winecharm/locale")

class build_py(_build_py):
    def run(self):
        self.compile_translations()
        super().run()

    def compile_translations(self):
        if not PO_DIR.exists():
            return
        for po_path in PO_DIR.glob("*.po"):
            lang = po_path.stem
            mo_dir = LOCALE_BASE / lang / "LC_MESSAGES"
            mo_dir.mkdir(parents=True, exist_ok=True)
            mo_path = mo_dir / f"{DOMAIN}.mo"
            po = polib.pofile(str(po_path))
            po.save_as_mofile(str(mo_path))
            self.announce(f"compiled {po_path} -> {mo_path}", level=3)

setup(cmdclass={"build_py": build_py})

