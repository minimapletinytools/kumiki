// Rules for the viewer's own code that the unit tests can't see break, because Node and jsdom
// accept what the oldest supported webview does not, or the bug only shows after a click.
const fs = require('fs');
const path = require('path');

const webviewDir = path.join(__dirname, '..', 'webview');

/** Every match of `pattern` in the webview's modules, as file:line. */
function findings(pattern) {
    const found = [];
    for (const name of fs.readdirSync(webviewDir).filter((n) => n.endsWith('.js'))) {
        const source = fs.readFileSync(path.join(webviewDir, name), 'utf8');
        for (const match of source.matchAll(pattern)) {
            found.push(`${name}:${source.slice(0, match.index).split('\n').length} ${match[0]}`);
        }
    }
    return found;
}

test('no iterator helpers: VS Code 1.63\'s webview (Chromium 91) has none, and Node does', () => {
    // keys()/values()/entries() hand back an iterator; forEach, map and the rest on one are
    // Chromium 122. getSceneBounds threw on every load. Loop with for...of, or Array.from().
    expect(findings(/\.(keys|values|entries|bundles)\(\)\s*\.(forEach|map|filter|some|every|find|reduce|flatMap|toArray|take|drop)\(/g))
        .toEqual([]);
});

test('checkbox state is bound as a property, not an attribute', () => {
    // A checkbox stops following its attribute once clicked, so Reset in the parameters panel
    // left boxes showing the old click. Bind live state as `.checked=${...}`.
    expect(findings(/\?checked=\$\{/g)).toEqual([]);
});
