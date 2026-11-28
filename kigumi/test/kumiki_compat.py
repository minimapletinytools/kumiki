"""Check kigumi's runner against a kumiki as users install it: only kumiki and its own dependencies.

Run it in a clean environment holding one kumiki, e.g.
    uv run --isolated --no-project --python 3.13 --with kumiki==0.9.10 python kigumi/test/kumiki_compat.py
It opens every pattern file that kumiki ships through kigumi/runner.py and fails on anything the runner
reports as an error.

`kumiki_compat.py versions` prints, as JSON, the published kumikis this kigumi accepts.
"""

import json
import subprocess
import sys
import urllib.request
from pathlib import Path

KIGUMI = Path(__file__).resolve().parent.parent
REQUESTS = ["get_geometry", "get_layers_tree", "get_drawings", "list_available_patterns", "shutdown"]
# A file of bare CSG examples (CSG_debug_patterns.py) has no frame for the viewer to open.
NOT_A_FRAME = "No patterns produced a renderable Frame"


def _parse(version):
    return tuple(int(part) for part in version.split("."))


def accepted_versions():
    """Every published kumiki from package.json's kumikiMinimum up, in kigumi's major.minor."""
    package = json.loads((KIGUMI / "package.json").read_text(encoding="utf-8"))
    major, minor = _parse(package["version"])[:2]
    least = _parse(package.get("kumikiMinimum") or f"{major}.{minor}.0")
    with urllib.request.urlopen("https://pypi.org/pypi/kumiki/json", timeout=30) as response:
        releases = json.load(response)["releases"]
    found = []
    for version, files in releases.items():
        try:
            parsed = _parse(version)
        except ValueError:
            continue  # a pre-release
        if files and parsed[:2] == (major, minor) and parsed >= least:
            found.append(version)
    return sorted(found, key=_parse)


def check_pattern(path):
    """Return the problems the runner reports opening `path`, or None if it holds no frame."""
    lines = "".join(json.dumps({"id": i, "command": c}) + "\n" for i, c in enumerate(REQUESTS))
    done = subprocess.run([sys.executable, str(KIGUMI / "runner.py"), str(path)], input=lines,
                          capture_output=True, text=True, timeout=900)
    problems = [line for line in done.stderr.splitlines() if line.startswith("[error]")]
    for line in done.stdout.splitlines():
        try:
            message = json.loads(line)
        except ValueError:
            continue
        if NOT_A_FRAME in json.dumps(message.get("error")):
            return None
        if message.get("type") == "fatal_error" or message.get("ok") is False or message.get("error"):
            problems.append(json.dumps(message.get("error"))[:2000])
    if done.returncode != 0 and not problems:
        problems.append(f"runner exited {done.returncode}: {done.stderr[-2000:]}")
    return problems


def main():
    if sys.argv[1:] == ["versions"]:
        print(json.dumps(accepted_versions()))
        return
    import kumiki
    patterns = Path(kumiki.__file__).parent / "patterns"
    files = sorted(p for p in patterns.rglob("*.py") if not p.name.startswith("_"))
    print(f"kumiki {kumiki.__version__}: {len(files)} pattern files", flush=True)
    failed = 0
    for path in files:
        problems = check_pattern(path)
        print(f"{'skip' if problems is None else 'FAIL' if problems else 'ok  '} {path.relative_to(patterns)}",
              flush=True)
        for problem in problems or ():
            print(f"     {problem}")
        failed += bool(problems)
    if failed:
        sys.exit(f"{failed} of {len(files)} pattern files failed with kumiki {kumiki.__version__}")


if __name__ == "__main__":
    main()
