"""
Import this module FIRST (before anything that imports `pyrogram`).

Supported libraries (all Pyrogram forks with the same API):
  * Pyrofork   -> installs the package `pyrogram`      (default, requirements.txt)
  * Hydrogram  -> installs the package `hydrogram`     (requirements-hydrogram.txt)
  * wzgram     -> optional

If `pyrogram` is not importable, every `pyrogram.*` import is transparently redirected
to the first installed alternative, so the bot code never has to change.
"""
import sys
import importlib
import importlib.abc
import importlib.util

ALTERNATIVES = ("hydrogram", "wzgram")


class _AliasFinder(importlib.abc.MetaPathFinder, importlib.abc.Loader):
    SRC = "pyrogram"

    def __init__(self, dst: str):
        self.DST = dst

    def find_spec(self, name, path=None, target=None):
        if name == self.SRC or name.startswith(self.SRC + "."):
            return importlib.util.spec_from_loader(name, self)
        return None

    def create_module(self, spec):
        return importlib.import_module(self.DST + spec.name[len(self.SRC):])

    def exec_module(self, module):  # already fully initialised
        return None


def install() -> str:
    try:
        import pyrogram  # noqa: F401
        return "pyrogram (Pyrofork)"
    except ModuleNotFoundError:
        pass
    for alt in ALTERNATIVES:
        try:
            importlib.import_module(alt)
        except ModuleNotFoundError:
            continue
        sys.meta_path.insert(0, _AliasFinder(alt))
        return alt
    raise SystemExit("No Telegram library installed. Run: pip install -r requirements.txt")


BACKEND = install()
