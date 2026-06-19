#!/bin/bash
# Installation script for Kigumi extension

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

echo "Preparing bundled agent instructions..."
if command -v node >/dev/null 2>&1; then
    node "$SCRIPT_DIR/scripts/prepare-bundled-instructions.js"
else
    echo "❌ Node.js is required to prepare bundled instructions."
    exit 1
fi

VSCODE_EXT_DIR="$HOME/.vscode/extensions/kigumi"
CURSOR_EXT_DIR="$HOME/.cursor/extensions/kigumi"

TARGETS=("$VSCODE_EXT_DIR" "$CURSOR_EXT_DIR")
EDITORS=("VSCode" "Cursor")
#TARGETS=("$VSCODE_EXT_DIR")
#EDITORS=("VSCode")
#TARGETS=("$CURSOR_EXT_DIR")
#EDITORS=("Cursor")


for i in "${!TARGETS[@]}"; do
    EXT_DIR="${TARGETS[$i]}"
    EDITOR="${EDITORS[$i]}"

    echo "Installing to $EDITOR: $EXT_DIR"
    mkdir -p "$EXT_DIR"

    rsync -a --delete --delete-excluded \
        --exclude node_modules \
        --exclude .vscode-test \
        --exclude .vscode \
        --exclude .artifacts \
        --exclude __pycache__ \
        --exclude __tests__ \
        --exclude test \
        --exclude test-fixtures \
        --exclude install.sh \
        --exclude install \
        --exclude test-frame.py \
        --exclude jest.config.js \
        --exclude package-lock.json \
        --exclude check-extension.md \
        --exclude .vscodeignore \
        --exclude CURSOR-INSTALL.md \
        --exclude INSTALL.md \
        --exclude .git \
        "$SCRIPT_DIR/" "$EXT_DIR/"

    if [ -d "$REPO_ROOT/docs" ]; then
        mkdir -p "$EXT_DIR/.kigumi/docs"
        rsync -a --delete "$REPO_ROOT/docs/" "$EXT_DIR/.kigumi/docs/"
    fi
done

echo "✅ Kigumi installed successfully in VSCode and Cursor!"
echo ""
echo "Next steps:"
echo "1. Reload VSCode and Cursor: Cmd+Shift+P → 'Developer: Reload Window'"
echo "2. Open a Python file with a build_frame() function"
echo "3. Run command: 'Render Kigumi'"
echo ""
echo "Test file available at: $SCRIPT_DIR/test-frame.py"
