/**
 * The agent docs Kigumi keeps in a project, in .kigumi/docs/.
 *
 * They come from the kumiki installed in the project's .venv (the wheel ships its docs as
 * kumiki/docs), so they always match the library the project builds with. The folder is
 * Kigumi's: it is replaced whole on every sync, and committed so an agent in a fresh clone
 * still finds it. AGENTS.md stays the user's -- Kigumi only rewrites its own marked block.
 */
const crypto = require('crypto');
const fs = require('fs');
const path = require('path');

const { runCommand } = require('./python-env');

const PROJECT_DOCS_DIR = path.join('.kigumi', 'docs');
const VERSION_FILE = 'kumiki-version.txt';
const AGENT_USAGE_DOC = '.kigumi/docs/agent_usage_instructions.md';

// The extension's own copy of the repo's docs/, and the repo's docs/ for a dev checkout.
const EXTENSION_DOCS_PATHS = [
    path.resolve(__dirname, '.kigumi', 'docs'),
    path.resolve(__dirname, '..', 'docs'),
];
// Kigumi-only skills, which the kumiki wheel does not ship.
const SKILLS_SOURCE_PATH = path.resolve(__dirname, 'skills');
// Website files and our own notes: not for an agent working in someone's project.
const NOT_FOR_AGENTS = new Set(['internal', 'assets', 'stylesheets', 'index.md']);

const README = [
    '# Kumiki docs, managed by Kigumi',
    '',
    'Kigumi copies these from the kumiki installed in `.venv` and replaces this whole folder',
    'whenever kumiki is updated, so do not edit them here: changes will be lost. Put notes',
    'for your project in AGENTS.md instead, outside the block Kigumi manages there.',
    '',
].join('\n');

const BLOCK_BEGIN = '<!-- kigumi:begin -->';
const BLOCK_END = '<!-- kigumi:end -->';
const AGENTS_BLOCK = [
    BLOCK_BEGIN,
    `Always read and follow \`${AGENT_USAGE_DOC}\`.`,
    '',
    'Kigumi keeps `.kigumi/docs/` in step with the kumiki installed in `.venv` and replaces it',
    'on update; this block is Kigumi\'s too. Put your own notes elsewhere in this file.',
    BLOCK_END,
].join('\n');

// Texts earlier Kigumi versions wrote into AGENTS.md, whole or appended to the user's.
const LEGACY_AGENTS_TEXTS = [
    [
        '# Agent Instructions', '', 'Always read and follow:', '', '- docs/agent_usage_instructions.md', '',
        'Note: the `docs/` folder was copied from the bundled Kigumi docs at project initialization',
        'time and may be out of date. The kumiki library installed in `.venv` ships its own docs.',
        'To check for a more recent version, resolve the library path:', '',
        '  .venv/bin/python3 -c "import kumiki, pathlib; print(pathlib.Path(kumiki.__file__).resolve().parent)"',
        '  (Windows: .venv\\Scripts\\python.exe)', '',
        'Then read `<that_path>/docs/agent_usage_instructions.md` for the most up-to-date instructions.', '',
    ].join('\n'),
    [
        '# Agent Instructions', '', 'Always read and follow:', '', '- docs/agent_usage_instructions.md', '',
        'Note: the `docs/` folder was copied from the bundled Kigumi docs at project initialization',
        'time and may be out of date. Run the "Kigumi: Update Kumiki" command (or reinitialize the',
        'project) to refresh it to the latest version.', '',
    ].join('\n'),
    ['# Agent Instructions', '', 'Always read and follow:', '', '- docs/agent_usage_instructions.md', ''].join('\n'),
    ['# Agent Instructions', '', 'Always read and follow:', '', '- .kigumi/docs/authoring.instructions.md', ''].join('\n'),
];

function sha256(buffer) {
    return crypto.createHash('sha256').update(buffer).digest('hex');
}

/** Every file under `root`, as paths relative to it with forward slashes. */
function listFiles(root, relative = '') {
    const here = path.join(root, relative);
    if (!fs.existsSync(here)) {
        return [];
    }
    return fs.readdirSync(here, { withFileTypes: true }).flatMap((entry) => {
        const child = relative ? `${relative}/${entry.name}` : entry.name;
        return entry.isDirectory() ? listFiles(root, child) : [child];
    });
}

/** The docs folder inside the kumiki installed for `pythonPath`, or null. Finds it without importing kumiki. */
async function installedKumikiDocsPath(projectRoot, pythonPath) {
    const snippet = [
        'import importlib.util, pathlib',
        'spec = importlib.util.find_spec("kumiki")',
        'print(pathlib.Path(spec.origin).parent / "docs" if spec and spec.origin else "")',
    ].join('\n');
    try {
        const { stdout } = await runCommand(pythonPath, ['-c', snippet], { cwd: projectRoot });
        const docs = (stdout || '').trim();
        return docs && fs.existsSync(path.join(docs, 'agent_usage_instructions.md')) ? docs : null;
    } catch (_error) {
        return null;
    }
}

/** Where to copy docs from: the installed kumiki's, else the extension's own copy. */
async function resolveDocsSource(projectRoot, pythonPath) {
    const installed = pythonPath ? await installedKumikiDocsPath(projectRoot, pythonPath) : null;
    if (installed) {
        return installed;
    }
    return EXTENSION_DOCS_PATHS.find((candidate) => fs.existsSync(candidate)) || null;
}

/** The files from `sourceDir` an agent should have, relative to it. */
function agentDocFiles(sourceDir) {
    return listFiles(sourceDir).filter((file) => !NOT_FOR_AGENTS.has(file.split('/')[0]));
}

/** Replace .kigumi/docs/ with the docs in `sourceDir`, the Kigumi skills, and a README. */
function writeProjectDocs(projectRoot, sourceDir, kumikiVersion) {
    const target = path.join(projectRoot, PROJECT_DOCS_DIR);
    fs.rmSync(target, { recursive: true, force: true });
    fs.mkdirSync(target, { recursive: true });
    for (const file of sourceDir ? agentDocFiles(sourceDir) : []) {
        fs.mkdirSync(path.dirname(path.join(target, file)), { recursive: true });
        fs.copyFileSync(path.join(sourceDir, file), path.join(target, file));
    }
    if (fs.existsSync(SKILLS_SOURCE_PATH)) {
        fs.cpSync(SKILLS_SOURCE_PATH, path.join(target, 'skills'), { recursive: true });
    }
    fs.writeFileSync(path.join(target, 'README.md'), README, 'utf8');
    fs.writeFileSync(path.join(target, VERSION_FILE), `${kumikiVersion || 'unknown'}\n`, 'utf8');
    return listFiles(target);
}

/** The kumiki version .kigumi/docs/ was copied from, or null if it has not been. */
function projectDocsVersion(projectRoot) {
    const file = path.join(projectRoot, PROJECT_DOCS_DIR, VERSION_FILE);
    return fs.existsSync(file) ? fs.readFileSync(file, 'utf8').trim() : null;
}

/** Copy the installed kumiki's docs into .kigumi/docs/. Returns where they came from and what was written. */
async function syncProjectDocs(projectRoot, pythonPath, kumikiVersion) {
    const source = await resolveDocsSource(projectRoot, pythonPath);
    return { source, files: writeProjectDocs(projectRoot, source, kumikiVersion) };
}

/** syncProjectDocs, only if .kigumi/docs/ is missing or was copied from another kumiki version. */
async function syncProjectDocsIfStale(projectRoot, pythonPath, kumikiVersion) {
    if (!kumikiVersion || kumikiVersion === 'unknown' || projectDocsVersion(projectRoot) === kumikiVersion) {
        return null;
    }
    return syncProjectDocs(projectRoot, pythonPath, kumikiVersion);
}

let legacyHashes = null;
function knownLegacyHashes() {
    if (legacyHashes === null) {
        const file = path.join(__dirname, 'legacy-doc-hashes.json');
        legacyHashes = fs.existsSync(file) ? JSON.parse(fs.readFileSync(file, 'utf8')) : {};
    }
    return legacyHashes;
}

/**
 * Remove the copies earlier Kigumi versions wrote into docs/: only files byte-for-byte as
 * Kigumi wrote them. The user's edits and their own files stay. Returns what was removed and kept.
 */
function removeLegacyDocs(projectRoot, known = knownLegacyHashes()) {
    const docs = path.join(projectRoot, 'docs');
    const removed = [];
    const kept = [];
    for (const file of listFiles(docs)) {
        if (!(file in known)) {
            continue; // never Kigumi's
        }
        if (known[file].includes(sha256(fs.readFileSync(path.join(docs, file))))) {
            fs.rmSync(path.join(docs, file));
            removed.push(`docs/${file}`);
        } else {
            kept.push(`docs/${file}`);
        }
    }
    removeEmptyDirectories(docs);
    return { removed, kept };
}

function removeEmptyDirectories(dir) {
    if (!fs.existsSync(dir) || !fs.statSync(dir).isDirectory()) {
        return;
    }
    for (const entry of fs.readdirSync(dir)) {
        removeEmptyDirectories(path.join(dir, entry));
    }
    if (fs.readdirSync(dir).length === 0) {
        fs.rmdirSync(dir);
    }
}

/**
 * Point AGENTS.md at .kigumi/docs/ through Kigumi's marked block, leaving the rest alone.
 * An earlier Kigumi's text is replaced by the block; otherwise the block is added at the end.
 */
function updateAgentsFile(projectRoot) {
    const agentsPath = path.join(projectRoot, 'AGENTS.md');
    if (!fs.existsSync(agentsPath)) {
        fs.writeFileSync(agentsPath, `# Agent Instructions\n\n${AGENTS_BLOCK}\n`, 'utf8');
        return { created: true, changed: true };
    }
    const current = fs.readFileSync(agentsPath, 'utf8');
    let next;
    const begin = current.indexOf(BLOCK_BEGIN);
    const end = current.indexOf(BLOCK_END, begin);
    if (begin !== -1 && end !== -1) {
        next = current.slice(0, begin) + AGENTS_BLOCK + current.slice(end + BLOCK_END.length);
    } else {
        const legacy = LEGACY_AGENTS_TEXTS.find((text) => current.includes(text));
        if (legacy) {
            const replacement = current.trim() === legacy.trim() ? `# Agent Instructions\n\n${AGENTS_BLOCK}\n` : `${AGENTS_BLOCK}\n`;
            next = current.replace(legacy, replacement);
        } else {
            next = `${current}${current.endsWith('\n') ? '' : '\n'}\n${AGENTS_BLOCK}\n`;
        }
    }
    if (next === current) {
        return { created: false, changed: false };
    }
    fs.writeFileSync(agentsPath, next, 'utf8');
    return { created: false, changed: true };
}

module.exports = {
    AGENTS_BLOCK,
    LEGACY_AGENTS_TEXTS,
    PROJECT_DOCS_DIR,
    projectDocsVersion,
    removeLegacyDocs,
    resolveDocsSource,
    syncProjectDocs,
    syncProjectDocsIfStale,
    updateAgentsFile,
    writeProjectDocs,
};
