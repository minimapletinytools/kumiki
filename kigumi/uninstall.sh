#!/bin/bash
# Uninstall script for Kigumi local development extension

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

EXT_IDENTIFIER=$(python3 - "$SCRIPT_DIR/package.json" <<'PYEOF'
import json
import sys

with open(sys.argv[1]) as f:
    pkg = json.load(f)

print(f"{pkg['publisher']}.{pkg['name']}")
PYEOF
)

for EDITOR_CLI in code cursor; do
    if ! command -v "$EDITOR_CLI" >/dev/null 2>&1; then
        echo "⚠️  '$EDITOR_CLI' CLI not found on PATH, skipping"
        continue
    fi
    if "$EDITOR_CLI" --uninstall-extension "$EXT_IDENTIFIER" 2>&1; then
        echo "✅ Removed from $EDITOR_CLI"
    else
        echo "⚠️  $EDITOR_CLI: not installed or uninstall failed"
    fi
done

# Clean up any leftover legacy folder names from older install.sh versions.
rm -rf "$HOME/.vscode/extensions/kigumi-local" "$HOME/.cursor/extensions/kigumi-local"

echo ""
echo "Reload VSCode/Cursor (Cmd+Shift+P → 'Developer: Reload Window') to pick up the marketplace version."
