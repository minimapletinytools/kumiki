// The list of integration suites (test/integration.js) names every one there is, and only those.
const fs = require('fs');
const path = require('path');
const { SUITES, choose } = require('../test/integration');
const { FILES } = require('../test/suite/suites');

const KIGUMI = path.join(__dirname, '..');
const driver = fs.readFileSync(path.join(KIGUMI, 'test', 'app', 'smoke-driver.js'), 'utf8');
const scenarios = fs.readdirSync(path.join(KIGUMI, 'test', 'app', 'scenarios')).map((name) => name.replace(/\.js$/, ''));
const webTests = fs.readdirSync(path.join(KIGUMI, 'hosts', 'pyodide', 'test'))
    .filter((name) => name.endsWith('-smoke.cjs')).map((name) => name.replace('-smoke.cjs', ''));

test('every app scenario, extension test file and browser test is listed, and nothing else', () => {
    const listed = SUITES.map((suite) => suite.name).sort();
    const real = [
        ...scenarios.map((name) => `app:${name}`),
        ...Object.keys(FILES).map((name) => `vscode:${name}`),
        ...webTests.map((name) => `web:${name}`),
    ].sort();
    expect(listed).toEqual(real);
    // The app's driver runs each scenario there is.
    for (const name of scenarios) expect(driver).toContain(`'${name}'`);
    for (const file of Object.values(FILES)) expect(fs.existsSync(path.join(KIGUMI, 'test', 'suite', file))).toBe(true);
});

test('core has a suite on the app and in VS Code; what needs another checkout runs only when named', () => {
    const core = choose(['core']).map((suite) => suite.name);
    expect(core.some((name) => name.startsWith('app:'))).toBe(true);
    expect(core.some((name) => name.startsWith('vscode:'))).toBe(true);
    expect(choose(['all']).map((suite) => suite.name)).not.toContain('web:mcp');
    expect(choose(['web']).map((suite) => suite.name)).toEqual(['web:browser', 'web:phone']);
    expect(choose(['web:mcp']).map((suite) => suite.name)).toEqual(['web:mcp']);
    expect(() => choose(['nope'])).toThrow(/No integration suite/);
});
