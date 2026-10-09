const fs = require('fs');
const path = require('path');

// `?checked=${...}` sets the attribute, which a checkbox stops reflecting once it
// has been clicked: after that only the `checked` property moves it. So state the
// code changes behind the user's back -- Reset in the parameters panel -- left the
// box showing the old click. Bind live state as a property: `.checked=${...}`.

const webviewDir = path.join(__dirname, '..', 'webview');

test('the webview binds checkbox state as a property, not an attribute', () => {
    const findings = [];
    for (const name of fs.readdirSync(webviewDir).filter((n) => n.endsWith('.js'))) {
        const source = fs.readFileSync(path.join(webviewDir, name), 'utf8');
        for (const match of source.matchAll(/\?checked=\$\{/g)) {
            const line = source.slice(0, match.index).split('\n').length;
            findings.push(`${name}:${line}`);
        }
    }
    expect(findings).toEqual([]);
});
