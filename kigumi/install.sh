#!/bin/bash
# Installation script for Kigumi extension
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

# Rotate the animal emoji in the sidebar view name so you can always tell
# whether a fresh install took effect vs. a cached/stale extension version.
ANIMALS=("🐴" "🦒" "🐘" "🦊" "🐺" "🦝" "🐻" "🦁" "🐯" "🐸" "🦓" "🐮" "🐷" "🦅" "🐧" "🦋" "🐢" "🦀" "🐙" "🦈")
NEXT_ANIMAL=$(python3 - "$SCRIPT_DIR/package.json" "${ANIMALS[@]}" <<'PYEOF'
import sys, json, re

pkg_path = sys.argv[1]
animals = sys.argv[2:]

with open(pkg_path) as f:
    pkg = json.load(f)

views = pkg.get("contributes", {}).get("views", {}).get("kigumi", [])
current = next((v["name"] for v in views if v.get("id") == "kigumi.explorer"), "")

# Extract current emoji (last non-space token after "Explorer")
m = re.search(r'Explorer\s+(\S+)$', current)
current_emoji = m.group(1) if m else ""

try:
    idx = animals.index(current_emoji)
    next_emoji = animals[(idx + 1) % len(animals)]
except ValueError:
    next_emoji = animals[0]

for v in views:
    if v.get("id") == "kigumi.explorer":
        base = re.sub(r'\s+\S+$', '', v["name"]) if re.search(r'\s+\S+$', v["name"]) else v["name"]
        v["name"] = f"{base} {next_emoji}"

with open(pkg_path, "w") as f:
    json.dump(pkg, f, indent=2, ensure_ascii=False)
    f.write("\n")

print(next_emoji)
PYEOF
)

echo "${NEXT_ANIMAL} Installing Kigumi extension..."

if [ ! -x "$SCRIPT_DIR/node_modules/.bin/vsce" ]; then
    echo "❌ @vscode/vsce not found in node_modules. Run 'npm install' in $SCRIPT_DIR first."
    exit 1
fi

EXT_IDENTIFIER=$(python3 - "$SCRIPT_DIR/package.json" <<'PYEOF'
import json
import sys

with open(sys.argv[1]) as f:
    pkg = json.load(f)

name = pkg.get("name", "").strip()
publisher = pkg.get("publisher", "").strip()
if not name or not publisher:
    raise SystemExit("package.json is missing required fields: publisher/name")

print(f"{publisher}.{name}")
PYEOF
)

PINNED_VERSION="999.0.0"
VSCODE_EXT_DIR="$HOME/.vscode/extensions/${EXT_IDENTIFIER}-${PINNED_VERSION}"
CURSOR_EXT_DIR="$HOME/.cursor/extensions/${EXT_IDENTIFIER}-${PINNED_VERSION}"
LEGACY_VSCODE_EXT_DIR="$HOME/.vscode/extensions/kigumi-local"
LEGACY_CURSOR_EXT_DIR="$HOME/.cursor/extensions/kigumi-local"

# Remove legacy non-standard folder names so extension discovery is unambiguous.
rm -rf "$LEGACY_VSCODE_EXT_DIR" "$LEGACY_CURSOR_EXT_DIR"

# Pin to a high version so this local build always wins over any marketplace
# version, then package a real VSIX and let `--install-extension` register it
# properly (extensions.json, .vsixmanifest, etc.) instead of hand-copying files
# into the extensions folder, which VS Code's scanner may silently reject/mark
# obsolete without any visible error.
WORK_DIR="$(mktemp -d)"
# Snapshot package.json *after* the emoji rotation above so cleanup restores the
# real version while keeping the rotated emoji (a plain `git checkout` here would
# also discard the emoji change, since both edits land in the same tracked file).
cp "$SCRIPT_DIR/package.json" "$WORK_DIR/package.json.orig"
cleanup() {
    cp "$WORK_DIR/package.json.orig" "$SCRIPT_DIR/package.json"
    rm -rf "$WORK_DIR"
}
trap cleanup EXIT

python3 -c "
import json
path = '$SCRIPT_DIR/package.json'
with open(path) as f: p = json.load(f)
p['version'] = '$PINNED_VERSION'
with open(path, 'w') as f: json.dump(p, f, indent=2, ensure_ascii=False); f.write('\n')
"

VSIX_PATH="$WORK_DIR/kigumi-local.vsix"
echo "Packaging extension..."
(cd "$SCRIPT_DIR" && ./node_modules/.bin/vsce package -o "$VSIX_PATH")

INSTALLED_ANY=false
for EDITOR_CLI in code cursor; do
    if ! command -v "$EDITOR_CLI" >/dev/null 2>&1; then
        echo "⚠️  '$EDITOR_CLI' CLI not found on PATH, skipping (install it via the editor's command palette: 'Shell Command: Install ''$EDITOR_CLI'' command in PATH')"
        continue
    fi

    echo "Installing to $EDITOR_CLI..."
    "$EDITOR_CLI" --install-extension "$VSIX_PATH" --force
    INSTALLED_ANY=true

    if [ "$EDITOR_CLI" = "code" ]; then
        EXT_DIR="$VSCODE_EXT_DIR"
    else
        EXT_DIR="$CURSOR_EXT_DIR"
    fi
    if [ -d "$REPO_ROOT/docs" ] && [ -d "$EXT_DIR" ]; then
        mkdir -p "$EXT_DIR/.kigumi/docs"
        rsync -a --delete "$REPO_ROOT/docs/" "$EXT_DIR/.kigumi/docs/"
    fi
done

if [ "$INSTALLED_ANY" = false ]; then
    echo "❌ Neither 'code' nor 'cursor' CLI is on PATH. Install one from the editor's command palette and re-run this script, or drag-install the VSIX manually: $VSIX_PATH"
    exit 1
fi

echo "✅ Kigumi installed successfully!"
echo ""
echo "Next steps:"
echo "1. Reload VSCode and Cursor: Cmd+Shift+P → 'Developer: Reload Window'"
echo "2. Open a Python file with a build_frame() function"
echo "3. Run command: 'Render Kigumi'"
echo ""
echo "Test file available at: $SCRIPT_DIR/test-frame.py"
