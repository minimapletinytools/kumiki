/**
 * kumiki's docs, which kumiki_source lists first (agent/kumiki-source-tool.js), and the instructions
 * Kigumi's MCP servers send: how to write frames.
 */

const fs = require('fs');
const path = require('path');

// What each doc is for, in the order to read them. Any other doc is listed by its first heading.
const ABOUT = {
    agent_usage_instructions: 'How to write kumiki frames: the rules to follow. Read it first.',
    api_cheat_sheet: 'The common functions\' signatures, which joint for the job, which way each face looks, and a small complete frame.',
    concepts: 'Coordinates, timbers, faces and joints, explained.',
    patternbook: 'How pattern files and @frame/@pattern work.',
};

// Website pages: not for agents.
const SKIP = new Set(['index']);

const MCP_INSTRUCTIONS = [
    'Kigumi shows timber frames written in Python with the kumiki library.',
    'Before writing or changing a frame, read kumiki_source "docs/agent_usage_instructions.md" (the rules) and "docs/api_cheat_sheet.md".',
    'Check a function\'s exact signature with kumiki_api rather than guessing.',
    'kumiki_source also reads and searches kumiki\'s source and its example frames.',
    'After an edit, build the frame with check_frame and see where its timbers ended up with describe_frame.',
].join(' ');

/** The docs in `folder`: [{ name, about }], the known ones first. */
function listDocs(folder) {
    const names = fs.readdirSync(folder)
        .filter((file) => file.endsWith('.md'))
        .map((file) => file.slice(0, -3))
        .filter((name) => !SKIP.has(name));
    const known = Object.keys(ABOUT).filter((name) => names.includes(name));
    const rest = names.filter((name) => !ABOUT[name]).sort();
    return [...known, ...rest].map((name) => ({ name, about: ABOUT[name] || firstHeading(path.join(folder, `${name}.md`)) }));
}

function firstHeading(file) {
    const line = fs.readFileSync(file, 'utf8').split('\n').find((one) => one.startsWith('#'));
    return line ? line.replace(/^#+\s*/, '') : '';
}

/**
 * The docs folder for kumiki at `source`: the wheel's kumiki/docs, a checkout's docs/, or else the
 * project's .kigumi/docs/. Null if none has them.
 */
function kumikiDocsFolder(source, projectRoot) {
    return [source && path.join(source, 'docs'), source && path.join(source, '..', 'docs'),
        projectRoot && path.join(projectRoot, '.kigumi', 'docs')]
        .filter(Boolean)
        .map((folder) => path.resolve(folder))
        .find((folder) => fs.existsSync(path.join(folder, 'agent_usage_instructions.md'))) || null;
}

module.exports = { listDocs, kumikiDocsFolder, MCP_INSTRUCTIONS };
