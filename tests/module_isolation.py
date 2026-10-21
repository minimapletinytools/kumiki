"""Undoing the module purge kigumi's runner does when it loads a slot."""

import sys
from pathlib import Path


def restore_modules(saved_modules):
    """Restore `sys.modules` to `saved_modules` after loading kigumi's runner, which purges and
    re-imports this checkout's modules.

    Modules from this checkout imported since are dropped; others (third-party, e.g. trimesh's native
    boolean backend) are kept, since a native extension can't be imported twice in one process.
    """
    repo = Path(__file__).resolve().parent.parent
    for name, module in list(sys.modules.items()):
        if name in saved_modules:
            continue
        origin = getattr(module, "__file__", None) or ""
        if name.startswith("kigumi_runner") or (origin.startswith(str(repo)) and "/.venv/" not in origin):
            del sys.modules[name]
    sys.modules.update(saved_modules)
