/**
 * The kumiki_docs tool, and the instructions Kigumi's MCP servers send: how to write frames, for
 * agents that can't read the project's .kigumi/docs/ themselves.
 */

const fs = require('fs');
const path = require('path');
const { z } = require('zod');

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
    'Before writing or changing a frame, read kumiki_docs "agent_usage_instructions" (the rules) and "api_cheat_sheet".',
    'Check a function\'s exact signature with kumiki_api rather than guessing.',
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

/** The kumiki_docs tool over `folder()`, the docs folder or null. */
function kumikiDocsTool(folder) {
    return {
        name: 'kumiki_docs',
        description: 'Read kumiki\'s docs for writing frames. With no name, lists them. Read "agent_usage_instructions" '
            + 'and "api_cheat_sheet" before writing or changing a frame.',
        shape: {
            name: z.string().optional().describe('The doc to read, e.g. "api_cheat_sheet". Leave out to list them.'),
        },
        effect: 'read',
        run: async ({ name }) => {
            const dir = folder();
            if (!dir) throw new Error('kumiki\'s docs aren\'t found yet: open a project whose .venv has kumiki.');
            const docs = listDocs(dir);
            const wanted = name && name.replace(/\.md$/, '');
            if (!wanted) return [{ type: 'text', text: docs.map((doc) => `${doc.name}: ${doc.about}`).join('\n') }];
            if (!docs.some((doc) => doc.name === wanted)) {
                throw new Error(`No doc "${name}". The docs: ${docs.map((doc) => doc.name).join(', ')}.`);
            }
            return [{ type: 'text', text: fs.readFileSync(path.join(dir, `${wanted}.md`), 'utf8') }];
        },
    };
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

module.exports = { kumikiDocsTool, kumikiDocsFolder, MCP_INSTRUCTIONS };
