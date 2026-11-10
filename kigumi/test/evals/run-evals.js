#!/usr/bin/env node
/**
 * Agent evals: each task (tasks.js) run by each model, in a project of its own, through the agent's
 * own loop, tools and prompt (agent/agent.js), on a host whose frames are built by Python
 * (build_frame.py) rather than in a view.
 * Scored on the task's checks, with steps, cost and time. Costs real money, on the OpenRouter key in
 * KIGUMI_EVAL_OPENROUTER_KEY.
 *
 *   node test/evals/run-evals.js [--models a,b] [--tasks a,b] [--repeat n] [--max-steps n] [--effort e]
 *                                [--out results.json] [--transcripts dir] [--keep]
 *
 * A task's prompts run as turns of one conversation. Each result has its prompt tokens and how many
 * were read from the cache, and each step's time and tokens written.
 *
 * --max-steps is the most steps in a turn (the app's 40 by default). --effort sets the reasoning
 * effort (models.js REASONING_EFFORTS; "" for the model's default). --transcripts writes each run as
 * Markdown, reasoning and tool calls included, for reading what the agent did (the scratch folder
 * test/evals/transcripts by default). --keep leaves each run's project folder.
 */

const fs = require('fs');
const os = require('os');
const path = require('path');
const { execFile } = require('child_process');

const { runTurn, languageModelFor, MAX_STEPS } = require('../../agent/agent-loop');
const { MODELS, REASONING_EFFORTS, findModel, harnessOf, routeModel } = require('../../agent/models');
const { loadSystemPrompt } = require('../../agent/system-prompt');
const { createProjectFiles } = require('../../agent/project-files');
const { pythonKumikiApi } = require('../../agent/kumiki-api');
const { agentTools, instructions } = require('../../agent/agent');
const { Checkpoints } = require('../../agent/checkpoints');
const { TASKS } = require('./tasks');

const REPO = path.resolve(__dirname, '..', '..', '..');
const PYTHON = path.join(REPO, '.venv', 'bin', 'python');
const DOCS = ['agent_usage_instructions.md', 'concepts.md', 'patternbook.md', 'api_cheat_sheet.md'];

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

/** build_frame.py's report as a host's frames give one (agent/frames.js). */
function asBuildReport(report) {
    const entries = (report.warnings || []).map((message) => ({ level: 'warning', message }));
    if (report.traceback) entries.push({ level: 'error', message: report.traceback.slice(-2000) });
    return { ok: report.ok, error: report.ok ? null : report.error, entries };
}

/** The app's host without its views: every .py file counts as shown, and is built by Python. */
function headlessHost(files, { kumikiSource, examples }) {
    const build = async (file) => asBuildReport(await buildFrame(files.resolve(file)));
    return {
        files,
        frames: { shows: (file) => String(file).endsWith('.py'), check: build, rebuild: build },
        view: null,
        kumikiApi: pythonKumikiApi({ python: () => PYTHON, env: { PYTHONPATH: REPO } }),
        kumikiSource: () => kumikiSource,
        kumikiExamples: () => examples,
        systemPrompt: loadSystemPrompt(),
    };
}

/** Text of `content`, a log entry's: a string, or parts. */
function partsText(content, limit) {
    const cut = (text) => (text.length > limit ? `${text.slice(0, limit)}\n[…${text.length - limit} more characters]` : text);
    if (typeof content === 'string') return cut(content);
    return (content || []).map((part) => {
        if (part.type === 'text') return cut(part.text);
        if (part.type === 'reasoning') return `> **thinking** ${cut(part.text).replace(/\n/g, '\n> ')}`;
        if (part.type === 'tool-call') return `**${part.toolName}** \`${JSON.stringify(part.input).slice(0, 300)}\``;
        if (part.type === 'tool-result') {
            const value = part.output && part.output.value;
            const text = Array.isArray(value) ? value.map((v) => v.text || `[${v.type}]`).join('\n') : JSON.stringify(part.output);
            return `\`\`\`\n${cut(text)}\n\`\`\``;
        }
        return `[${part.type}]`;
    }).join('\n\n');
}

/** `result`'s run as Markdown: the conversation, each step's time and tokens, then the checks. */
function transcript(result, log) {
    const lines = [`# ${result.task} · ${result.model}${result.effort !== undefined ? ` · effort ${result.effort || 'default'}` : ''}`, '',
        `${result.passed ? 'PASS' : 'FAIL'}: ${result.checks.map((c) => `${c.passed ? '✓' : '✗'} ${c.said}`).join('; ')}`,
        `${result.tools} tool calls, ${result.steps.length} steps, ${result.seconds}s, $${result.costUsd.toFixed(4)}`, ''];
    let step = 0;
    for (const entry of log) {
        if (entry.role === 'assistant') {
            const s = result.steps[step++];
            lines.push(`## Step ${step}${s ? ` (${s.seconds}s, ${s.output ?? '?'} tokens written, ${s.reasoning ?? '?'} reasoning)` : ''}`);
            lines.push(partsText(entry.content, 4000), '');
        } else if (entry.role === 'tool') {
            lines.push(partsText(entry.content, 1500), '');
        } else if (entry.role === 'user') {
            lines.push(`## User`, partsText(entry.content, 4000), '');
        } else if (entry.note || entry.summary) {
            lines.push(`*[${entry.note || 'summary'}] ${String(entry.text || entry.summary).slice(0, 600)}*`, '');
        }
    }
    return lines.join('\n');
}

/** Run `task` on `modelId`; `languageModel` stands in for the real one in tests. */
async function runOne(task, modelId, key, { languageModel: given = null } = {}) {
    const root = fs.mkdtempSync(path.join(os.tmpdir(), `kigumi-eval-${task.name}-`));
    fs.mkdirSync(path.join(root, '.kigumi', 'docs'), { recursive: true });
    for (const doc of DOCS) fs.copyFileSync(path.join(REPO, 'docs', doc), path.join(root, '.kigumi', 'docs', doc));
    for (const [name, content] of Object.entries(task.files)) fs.writeFileSync(path.join(root, name), content);
    const kumikiSource = path.join(REPO, 'kumiki');
    const examples = path.join(REPO, 'patterns');
    const files = createProjectFiles({ root: () => root, readOnly: () => [kumikiSource, examples] });
    const host = headlessHost(files, { kumikiSource, examples });
    const checkpoints = new Checkpoints(files);
    checkpoints.begin(1);
    const model = findModel(modelId);
    const toolCalls = [];
    const notices = [];
    // Each call with its arguments, for seeing what a model spends its steps on.
    const calls = [];
    const started = Date.now();
    let costUsd = 0;
    let failure = null;
    const log = [];
    const tokens = { prompt: 0, cached: 0, output: 0, reasoning: 0 };
    // Each step's time, and what it wrote.
    const steps = [];
    let stepStarted = Date.now();
    const effort = option('effort', null);
    if (effort !== null && !REASONING_EFFORTS.includes(effort)) throw new Error(`No reasoning effort ${effort}`);
    const harness = { ...harnessOf(model), ...(effort !== null ? { reasoningEffort: effort } : {}) };
    // The last turn's reply, for checks on what the agent said.
    let reply = '';
    const languageModel = given || await languageModelFor(routeModel(model, { openrouterKey: key }));
    const tools = agentTools(host, { checkpoints: () => checkpoints });
    try {
        for (const prompt of task.prompts) {
            reply = '';
            const result = await runTurn({
                model: languageModel, images: model.images, cacheMarks: Boolean(model.cacheMarks), harness,
                maxSteps: Number(option('max-steps', String(MAX_STEPS))), tools, files, system: instructions(host),
                log, prompt: [{ role: 'user', content: prompt, shown: { text: prompt, images: 0 } }], askPermission: async () => true,
                onEvent: (event) => {
                    if (event.type === 'agent:tool') {
                        toolCalls.push(event.name);
                        calls.push({ name: event.name, input: event.input });
                    }
                    if (event.type === 'agent:notice') notices.push(event.text);
                    if (event.type === 'agent:text') reply += event.text;
                    if (event.type === 'agent:context') {
                        tokens.prompt += event.tokens;
                        tokens.cached += event.cached || 0;
                        tokens.output += event.output || 0;
                        tokens.reasoning += event.reasoning || 0;
                        steps.push({ seconds: Math.round((Date.now() - stepStarted) / 100) / 10, prompt: event.tokens,
                            output: event.output, reasoning: event.reasoning });
                        stepStarted = Date.now();
                    }
                },
            });
            costUsd += result.costUsd || 0;
            stepStarted = Date.now();
        }
    } catch (error) {
        failure = String(error.message || error);
    }
    const report = await buildFrame(path.join(root, task.target));
    const project = { read: (name) => fs.readFileSync(path.join(root, name), 'utf8'), reply, tools: toolCalls.length };
    const checks = task.checks.map((check) => {
        const [passed, said] = check(report, project);
        return { passed: Boolean(passed), said };
    });
    if (!process.argv.includes('--keep')) fs.rmSync(root, { recursive: true, force: true });
    const result = {
        task: task.name, model: modelId, effort: harness.reasoningEffort, ...(process.argv.includes('--keep') ? { project: root } : {}), passed: !failure && checks.every((check) => check.passed), checks,
        tools: toolCalls.length, toolsUsed: Object.fromEntries([...new Set(toolCalls)].map((name) => [name, toolCalls.filter((t) => t === name).length])),
        promptTokens: tokens.prompt, cachedTokens: tokens.cached, outputTokens: tokens.output, reasoningTokens: tokens.reasoning, steps, cacheRate: tokens.prompt ? tokens.cached / tokens.prompt : 0,
        notices, notes: log.filter((entry) => entry.note).map(({ note, text }) => ({ note, text })), calls, costUsd, seconds: Math.round((Date.now() - started) / 1000), failure,
    };
    return { ...result, transcript: transcript(result, log) };
}

async function main() {
    const key = process.env.KIGUMI_EVAL_OPENROUTER_KEY;
    if (!key) throw new Error('Set KIGUMI_EVAL_OPENROUTER_KEY to an OpenRouter key.');
    const models = option('models', MODELS[0].id).split(',');
    const tasks = option('tasks', TASKS.map((task) => task.name).join(',')).split(',')
        .map((name) => TASKS.find((task) => task.name === name) || (() => { throw new Error(`No task ${name}`); })());
    const repeat = Number(option('repeat', '1'));
    const results = [];
    const transcripts = option('transcripts', path.join(__dirname, 'transcripts'));
    fs.mkdirSync(transcripts, { recursive: true });
    for (const modelId of models) {
        for (const task of tasks) {
            for (let i = 0; i < repeat; i++) {
                const { transcript: text, ...result } = await runOne(task, modelId, key);
                results.push(result);
                const file = path.join(transcripts, `${modelId}-${task.name}-${result.effort || 'default'}-${i + 1}.md`);
                fs.writeFileSync(file, text);
                console.log(`${result.passed ? 'PASS' : 'FAIL'} ${modelId} ${task.name}: ${result.checks.map((c) => `${c.passed ? '✓' : '✗'} ${c.said}`).join('; ')}`
                    + ` | ${result.tools} tool calls, ${result.steps.length} steps, ${result.reasoningTokens} reasoning tokens,`
                    + ` $${result.costUsd.toFixed(4)}, ${Math.round(result.cacheRate * 100)}% cached, ${result.seconds}s`
                    + `${result.notices.length ? ` | ${result.notices.join(' ')}` : ''}${result.failure ? ` | ${result.failure}` : ''}`
                    + `\n  ${path.relative(process.cwd(), file)}`);
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

if (require.main === module) {
    main().catch((error) => {
        console.error(error.message || error);
        process.exit(1);
    });
}

module.exports = { headlessHost, runOne, transcript };
