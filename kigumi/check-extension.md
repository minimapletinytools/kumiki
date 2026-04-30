# Verify Extension is Loaded

After reloading Cursor, check if the extension is loaded:

## Method 1: Check Running Extensions
1. Press `Cmd+Shift+P`
2. Type "show running extensions"
3. Select **"Developer: Show Running Extensions"**
4. Look for **"Kigumi"** in the list

## Method 2: Check Extension Host Log
1. Go to **View → Output** (or `Cmd+Shift+U`)
2. In the dropdown, select **"Extension Host"**
3. Look for any errors related to "kigumi"

## Method 3: Check Logs
1. Press `Cmd+Shift+P`
2. Type "developer tools"
3. Select **"Developer: Toggle Developer Tools"**
4. Go to the **Console** tab
5. Look for any extension-related errors

## Common Issues

### Command Not Showing Up
- Make sure you **reloaded Cursor** after installing
- Check that files exist: `ls ~/.cursor/extensions/kigumi/`
- Verify package.json is valid: `cat ~/.cursor/extensions/kigumi/package.json`

### Extension Not Loading
- Check the Extension Host output for errors
- Make sure there's no syntax error in extension.js
- Try restarting Cursor completely (quit and reopen)

## Test Without Extension

You can always test the Python runner directly:
```bash
cd /Users/peter.lu/kitchen/faucet/kumiki-proto
venv/bin/python kigumi/runner.py kigumi/test-frame.py
```

This will output the JSON data that would appear in the webview.
