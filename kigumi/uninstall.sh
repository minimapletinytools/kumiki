#!/bin/bash
# Uninstall script for Kigumi local development extension

VSCODE_EXT_DIR="$HOME/.vscode/extensions/kigumi-local"
CURSOR_EXT_DIR="$HOME/.cursor/extensions/kigumi-local"

TARGETS=("$VSCODE_EXT_DIR" "$CURSOR_EXT_DIR")
EDITORS=("VSCode" "Cursor")

for i in "${!TARGETS[@]}"; do
    EXT_DIR="${TARGETS[$i]}"
    EDITOR="${EDITORS[$i]}"

    if [ -d "$EXT_DIR" ]; then
        rm -rf "$EXT_DIR"
        echo "✅ Removed $EDITOR local install: $EXT_DIR"
    else
        echo "⚠️  $EDITOR local install not found: $EXT_DIR"
    fi
done

echo ""
echo "Reload VSCode/Cursor (Cmd+Shift+P → 'Developer: Reload Window') to pick up the marketplace version."
