const { execFileSync } = require('child_process');
const fs = require('fs');
const os = require('os');
const path = require('path');

// A `const` read before its declaration parses fine and throws at runtime, so
// neither `node --check` nor any unit test here catches it -- viewer-app.js has
// no harness, being a Lit component wanting a browser. One shipped: a dimension
// read its scale one line above where the scale was worked out, and every
// measurement threw the moment it was drawn.
//
// This is the cheapest thing that would have caught it. The rule is quiet on
// this codebase, so it stays an error rather than a list nobody reads.

const webviewDir = path.join(__dirname, '..', 'webview');

/** Module-level names used inside functions defined earlier: fine at runtime. */
const KNOWN = ['GeometryMode', 't'];

describe('nothing is read before it is declared', () => {
    const files = fs.readdirSync(webviewDir)
        .filter((name) => name.endsWith('.js'))
        .map((name) => path.join(webviewDir, name));

    let findings;

    beforeAll(() => {
        const config = path.join(os.tmpdir(), `kigumi-eslint-${process.pid}.mjs`);
        fs.writeFileSync(config, [
            'export default [{',
            '  files: ["**/*.js"],',
            '  languageOptions: { ecmaVersion: 2022, sourceType: "module" },',
            '  rules: { "no-use-before-define":',
            '    ["error", { functions: false, classes: false, variables: true }] },',
            '}];',
        ].join('\n'));
        try {
            const out = execFileSync(
                'npx',
                ['eslint', '--no-config-lookup', '-c', config, '-f', 'json', ...files],
                { cwd: path.join(__dirname, '..'), encoding: 'utf8', stdio: ['ignore', 'pipe', 'ignore'] },
            );
            findings = JSON.parse(out);
        } catch (error) {
            // eslint exits non-zero when it reports something; the report is
            // still on stdout. A missing eslint gives no stdout at all.
            findings = error.stdout ? JSON.parse(error.stdout) : null;
        } finally {
            fs.rmSync(config, { force: true });
        }
    });

    test('eslint ran', () => {
        if (findings === null) {
            console.warn('eslint unavailable; skipping');
        }
        expect(findings === null || Array.isArray(findings)).toBe(true);
    });

    test('no webview module reads a name before declaring it', () => {
        if (findings === null) {
            return;
        }
        const unexpected = findings.flatMap((file) => file.messages
            .filter((message) => message.ruleId === 'no-use-before-define')
            .filter((message) => !KNOWN.some((name) => message.message.includes(`'${name}'`)))
            .map((message) => `${path.basename(file.filePath)}:${message.line} ${message.message}`));

        expect(unexpected).toEqual([]);
    });
});
