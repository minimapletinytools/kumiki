#!/bin/bash
# Installation script for Kumiki Viewer extension

echo "🐴 Installing Kumiki Viewer extension..."

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

VSCODE_EXT_DIR="$HOME/.vscode/extensions/kumiki-viewer"
CURSOR_EXT_DIR="$HOME/.cursor/extensions/kumiki-viewer"

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
done

echo "✅ Kumiki Viewer installed successfully in VSCode and Cursor!"
echo ""
echo "Next steps:"
echo "1. Reload VSCode and Cursor: Cmd+Shift+P → 'Developer: Reload Window'"
echo "2. Open a Python file with a build_frame() function"
echo "3. Run command: 'Render Kumiki'"
echo ""
echo "Test file available at: $SCRIPT_DIR/test-frame.py"
