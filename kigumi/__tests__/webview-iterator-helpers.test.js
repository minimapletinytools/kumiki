const fs = require('fs');
const path = require('path');

// keys()/values()/entries() hand back an iterator, and forEach, map and the
// rest on an iterator are recent (Chromium 122). kigumi supports VS Code 1.63,
// whose webview is Chromium 91, where getSceneBounds threw on every load. Node
// here has them, so no unit test notices. Loop with for...of, or Array.from().

const webviewDir = path.join(__dirname, '..', 'webview');
const ITERATOR_THEN_HELPER =
    /\.(keys|values|entries|bundles)\(\)\s*\.(forEach|map|filter|some|every|find|reduce|flatMap|toArray|take|drop)\(/g;

test('the webview calls no iterator helpers', () => {
    const findings = [];
    for (const name of fs.readdirSync(webviewDir).filter((n) => n.endsWith('.js'))) {
        const source = fs.readFileSync(path.join(webviewDir, name), 'utf8');
        for (const match of source.matchAll(ITERATOR_THEN_HELPER)) {
            const line = source.slice(0, match.index).split('\n').length;
            findings.push(`${name}:${line} ${match[0]}`);
        }
    }
    expect(findings).toEqual([]);
});
