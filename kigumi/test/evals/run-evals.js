#!/usr/bin/env node
/**
 * Agent evals: each task (tasks.js) run by each model, in a project of its own, through the agent's
 * own loop, prompt and file tools, with frames built by Python (build_frame.py) rather than a view.
 * Scored on the task's checks, with steps, cost and time. Costs real money, on the OpenRouter key in
 * KIGUMI_EVAL_OPENROUTER_KEY.
 *
 *   node test/evals/run-evals.js [--models a,b] [--tasks a,b] [--repeat n] [--max-steps n] [--out results.json] [--keep]
 *
 * --max-steps is the most steps in a turn (the app's 40 by default). --keep leaves each run's project
 * folder, to see what the agent wrote.
 */

const fs = require('fs');
const os = require('os');
const path = require('path');
const { execFile } = require('child_process');

const { runTurn, languageModelFor, MAX_STEPS } = require('../../agent/agent-loop');
const { MODELS, findModel, routeModel } = require('../../agent/models');
const { loadSystemPrompt } = require('../../agent/system-prompt');
const { createProjectFiles } = require('../../agent/project-files');
const { createFileTools } = require('../../agent/file-tools');
const { todoTool } = require('../../agent/session-tools');
const { TASKS } = require('./tasks');

const REPO = path.resolve(__dirname, '..', '..', '..');
const PYTHON = path.join(REPO, '.venv', 'bin', 'python');
const DOCS = ['agent_usage_instructions.md', 'concepts.md', 'patternbook.md'];

function option(name, fallback) {
    const at = process.argv.indexOf(`--${name}`);
    return at >= 0 && process.argv[at + 1] ? process.argv[at + 1] : fallback;
}

/** build_frame.py's report on `file`. */
function buildFrame(file) {
    return new Promise((resolve) => {
        // The checkout's kumiki, whatever the venv has installed.
        execFile(PYTHON, [path.join(__dirname, 'build_frame.py'), file], { env: { ...process.env, PYTHONPATH: REPO }, timeout: 120000,
            maxBuffer: 16 * 1024 * 1024 }, (error, stdout) => {
            try {
                resolve(JSON.parse(stdout.trim().split('\n').pop()));
            } catch (_parseError) {
                resolve({ ok: false, error: (error && error.message) || 'no report' });
            }
        });
    });
}

/** A report as the agent sees an edit's or check_frame's, as in the app (session-tools.js describeBuild). */
function describeReport(report) {
    if (!report.ok) return `The file failed to build:\nerror: ${report.error}\n${(report.traceback || '').slice(-2000)}`;
    return `The file built without errors.${report.warnings.length ? `\n${report.warnings.map((w) => `warning: ${w}`).join('\n')}` : ''}`;
}

/** The tools as in the app, a view's build standing in for Python's. */
function evalTools(files) {
    const fileTools = createFileTools({ files }).map((tool) => (['write_file', 'edit_file'].includes(tool.name) ? {
        ...tool,
        run: async (args, context) => {
            const result = await tool.run(args, context);
            if (!String(args.file_path).endsWith('.py')) return result;
            return [...result, { type: 'text', text: describeReport(await buildFrame(files.resolve(args.file_path))) }];
        },
    } : tool));
    return [...fileTools, todoTool(() => {}), {
        name: 'check_frame',
        description: 'Build a Python frame file and say whether it built, with its warnings and errors.',
        shape: { file_path: require('zod').z.string().describe('A path in the project.') },
        readOnly: true,
        run: async ({ file_path: file }) => [{ type: 'text', text: describeReport(await buildFrame(files.resolve(file))) }],
    }];
}

async function runOne(task, modelId, key) {
    const root = fs.mkdtempSync(path.join(os.tmpdir(), `kigumi-eval-${task.name}-`));
    fs.mkdirSync(path.join(root, '.kigumi', 'docs'), { recursive: true });
    for (const doc of DOCS) fs.copyFileSync(path.join(REPO, 'docs', doc), path.join(root, '.kigumi', 'docs', doc));
    for (const [name, content] of Object.entries(task.files)) fs.writeFileSync(path.join(root, name), content);
    const kumikiSource = path.join(REPO, 'kumiki');
    const files = createProjectFiles({ root: () => root, readOnly: () => [kumikiSource] });
    const model = findModel(modelId);
    const tools = [];
    const notices = [];
    const started = Date.now();
    let costUsd = 0;
    let failure = null;
    try {
        const result = await runTurn({
            model: await languageModelFor(routeModel(model, { openrouterKey: key })), images: model.images,
            cacheMarks: Boolean(model.cacheMarks), maxSteps: Number(option('max-steps', String(MAX_STEPS))), tools: evalTools(files), files, system: loadSystemPrompt()(kumikiSource),
            history: [], prompt: task.prompt, askPermission: async () => true,
            onEvent: (event) => {
                if (event.type === 'agent:tool') tools.push(event.name);
                if (event.type === 'agent:notice') notices.push(event.text);
            },
        });
        costUsd = result.costUsd || 0;
    } catch (error) {
        failure = String(error.message || error);
    }
    const report = await buildFrame(path.join(root, task.target));
    const checks = task.checks.map((check) => {
        const [passed, said] = check(report);
        return { passed: Boolean(passed), said };
    });
    if (!process.argv.includes('--keep')) fs.rmSync(root, { recursive: true, force: true });
    return {
        task: task.name, model: modelId, ...(process.argv.includes('--keep') ? { project: root } : {}), passed: !failure && checks.every((check) => check.passed), checks,
        tools: tools.length, toolsUsed: Object.fromEntries([...new Set(tools)].map((name) => [name, tools.filter((t) => t === name).length])),
        notices, costUsd, seconds: Math.round((Date.now() - started) / 1000), failure,
    };
}

async function main() {
    const key = process.env.KIGUMI_EVAL_OPENROUTER_KEY;
    if (!key) throw new Error('Set KIGUMI_EVAL_OPENROUTER_KEY to an OpenRouter key.');
    const models = option('models', MODELS[0].id).split(',');
    const tasks = option('tasks', TASKS.map((task) => task.name).join(',')).split(',')
        .map((name) => TASKS.find((task) => task.name === name) || (() => { throw new Error(`No task ${name}`); })());
    const repeat = Number(option('repeat', '1'));
    const results = [];
    for (const modelId of models) {
        for (const task of tasks) {
            for (let i = 0; i < repeat; i++) {
                const result = await runOne(task, modelId, key);
                results.push(result);
                console.log(`${result.passed ? 'PASS' : 'FAIL'} ${modelId} ${task.name}: ${result.checks.map((c) => `${c.passed ? '✓' : '✗'} ${c.said}`).join('; ')}`
                    + ` | ${result.tools} tool calls, $${result.costUsd.toFixed(4)}, ${result.seconds}s`
                    + `${result.notices.length ? ` | ${result.notices.join(' ')}` : ''}${result.failure ? ` | ${result.failure}` : ''}`);
            }
        }
    }
    console.log('\nmodel                     passed  tool calls  cost      time');
    for (const modelId of models) {
        const mine = results.filter((result) => result.model === modelId);
        const sum = (key) => mine.reduce((total, result) => total + result[key], 0);
        console.log(`${modelId.padEnd(25)} ${`${mine.filter((r) => r.passed).length}/${mine.length}`.padEnd(7)} `
            + `${String(Math.round(sum('tools') / mine.length)).padEnd(11)} $${sum('costUsd').toFixed(4).padEnd(8)} ${sum('seconds')}s`);
    }
    const out = option('out', null);
    if (out) fs.writeFileSync(out, JSON.stringify(results, null, 1));
}

main().catch((error) => {
    console.error(error.message || error);
    process.exit(1);
});
