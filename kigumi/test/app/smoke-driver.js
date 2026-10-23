/**
 * Runs inside the standalone app (see run-app-tests.js), with this repo as the workspace: each
 * scenario in scenarios/, from a known layout (helpers.js, reset), then a look at the log for errors.
 *
 * A scenario that throws fails on its own and the others still run. KIGUMI_TEST_SCENARIO names
 * the ones to run (comma-separated), e.g. KIGUMI_TEST_SCENARIO=sidebar,mcp.
 */

const fs = require('fs');
const path = require('path');
const { createContext } = require('./helpers');

// In order; each starts from the reset layout, so none depends on another.
const SCENARIOS = [
    'explorer', 'viewer', 'sidebar', 'drawings', 'mcp', 'parameters', 'quick-pick',
    'tabs-and-editors', 'go-to-file', 'layout', 'settings', 'crash-recovery',
].map((name) => require(`./scenarios/${name}`));

module.exports = async function smoke(app) {
    const results = [];
    let scenario = null;
    const check = (name, ok, detail) => {
        results.push({ scenario, name, ok: !!ok, detail });
        console.log(`${ok ? 'PASS' : 'FAIL'} [${scenario}] ${name}${detail ? ` -- ${detail}` : ''}`);
    };
    const ctx = createContext(app, check);
    const only = (process.env.KIGUMI_TEST_SCENARIO || '').split(',').map((name) => name.trim()).filter(Boolean);
    const chosen = SCENARIOS.filter((one) => only.length === 0 || only.includes(one.name));

    for (const one of chosen) {
        scenario = one.name;
        try {
            await ctx.reset();
            await one.run(ctx);
        } catch (error) {
            check('ran to the end', false, error.stack || String(error));
        }
    }
    scenario = 'log';
    await ctx.reset().catch(() => null);
    const errors = app.logLines().filter((line) => /traceback|uncaught|\[error\]/i.test(line));
    check('no errors in the log', errors.length === 0, errors.slice(0, 3).join(' / '));

    if (ctx.ARTIFACTS) {
        fs.mkdirSync(ctx.ARTIFACTS, { recursive: true });
        fs.writeFileSync(path.join(ctx.ARTIFACTS, 'app.log'), app.logLines().join('\n'));
    }
    const failed = results.filter((result) => !result.ok);
    const byScenario = [...new Set(results.map((result) => result.scenario))].map((name) => {
        const own = results.filter((result) => result.scenario === name);
        return `${name} ${own.filter((result) => result.ok).length}/${own.length}`;
    });
    console.log(`${results.length - failed.length} passed, ${failed.length} failed (${byScenario.join(', ')})`);
    return failed.length === 0;
};
