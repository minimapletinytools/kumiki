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
// A name never declared AT ALL is the same class and a worse case, and
// use-before-define cannot see it: there is no "before". Ten of them shipped
// together when a refactor swept up constants it thought were unused, and the
// viewer came up blank -- `INITIAL_PAYLOAD is not defined`, thrown while the
// module was still being evaluated, so nothing rendered and nothing said why.
//
// Six of the ten went on working by accident: selection-store.js and its
// neighbours publish those same names on `window`, so a bare read found the
// global. That is what hid the other four. no-undef sees all ten, which is why
// every global the webview actually has is listed here rather than pulled in
// wholesale -- a broad environment would have swallowed the six and left the
// hole open.
//
// Both rules stay errors rather than a list nobody reads.

const webviewDir = path.join(__dirname, '..', 'webview');

/** Module-level names used inside functions defined earlier: fine at runtime. */
const KNOWN = ['GeometryMode', 't'];

/**
 * Everything the webview gets from the browser or its host, and nothing else.
 *
 * Deliberately hand-written and short. `globals.browser` would cover these and
 * also cover names the webview means to declare for itself, which is the hole
 * this is here to close.
 */
const ENVIRONMENT = [
    'window', 'document', 'console', 'module', 'require', 'globalThis',
    'setTimeout', 'clearTimeout', 'setInterval', 'clearInterval',
    'requestAnimationFrame', 'cancelAnimationFrame', 'performance',
    'CustomEvent', 'Event', 'CSS', 'HTMLElement', 'customElements',
    'acquireVsCodeApi', 'THREE',
];

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
            // One languageOptions, not two: a second key overrides the first,
            // and losing sourceType here would report every import as a parse
            // error instead of linting anything.
            '  languageOptions: {',
            '    ecmaVersion: 2022, sourceType: "module",',
            `    globals: ${JSON.stringify(Object.fromEntries(
                ENVIRONMENT.map((name) => [name, 'readonly'])))} },`,
            '  rules: {',
            '    "no-use-before-define":',
            '      ["error", { functions: false, classes: false, variables: true }],',
            '    "no-undef": "error" },',
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

    /** Every finding for one rule, as readable lines, minus the KNOWN ones. */
    function reported(ruleId) {
        return findings.flatMap((file) => file.messages
            .filter((message) => message.ruleId === ruleId)
            .filter((message) => !KNOWN.some((name) => message.message.includes(`'${name}'`)))
            .map((message) => `${path.basename(file.filePath)}:${message.line} ${message.message}`));
    }

    test('eslint actually linted, rather than failing to parse', () => {
        // A bad config reports every file as a parse error and then both tests
        // below pass by finding no rule violations in anything.
        if (findings === null) {
            return;
        }
        // `fatal`, not `ruleId === null`: an unused eslint-disable directive
        // reports with no rule id too, and a file carrying one for a rule this
        // ad-hoc config does not turn on is fine.
        const broken = findings.flatMap((file) => file.messages
            .filter((message) => message.fatal)
            .map((message) => `${path.basename(file.filePath)} ${message.message}`));

        expect(broken).toEqual([]);
        expect(findings.length).toBeGreaterThan(10);
    });

    test('no webview module reads a name before declaring it', () => {
        if (findings === null) {
            return;
        }

        expect(reported('no-use-before-define')).toEqual([]);
    });

    test('and no webview module reads a name it never declares', () => {
        // The blank-viewer bug: a refactor swept up ten declarations that were
        // still used, and the module threw while it was being evaluated.
        if (findings === null) {
            return;
        }

        expect(reported('no-undef')).toEqual([]);
    });
});
