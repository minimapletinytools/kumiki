/**
 * The built-in agent's file tools, in the same shape as Kigumi's (agent/tools.js): list, search, read,
 * write and edit files, inside the project only, through a project-files interface
 * (agent/project-files.js for Node; a web host gives its own).
 */

const { z } = require('zod');

const text = (value) => [{ type: 'text', text: value }];

const MAX_LISTED = 500;
const MAX_MATCHES = 100;
const MAX_READ_LINES = 2000;
/** A read's most characters: every read stays in the conversation, which goes with every step. */
const MAX_READ_CHARS = 40000;

/** @param {{files: object}} options  the project's files (agent/project-files.js) */
function createFileTools({ files }) {
    const filePath = z.string().describe('A path relative to the project folder (or absolute, inside it).');
    // Writes and edits one at a time: a model asks for several at once, and two edits of a file at
    // once would each write their own copy, losing one, or interleave into garbage.
    let changing = Promise.resolve();
    const oneAtATime = (change) => {
        const done = changing.then(change);
        changing = done.catch(() => {});
        return done;
    };

    return [
        {
            name: 'list_files',
            description: 'List the files under a folder of the project (the whole project by default).',
            shape: { folder: z.string().optional().describe('A folder relative to the project folder.') },
            effect: 'read',
            run: async ({ folder }) => {
                const found = await files.list(folder, MAX_LISTED);
                return text(found.join('\n') + (found.length >= MAX_LISTED ? `\n(first ${MAX_LISTED} only)` : ''));
            },
        },
        {
            name: 'search_files',
            description: 'Search the project\'s files for a regular expression, giving each matching line with its '
                + `file and line number (at most ${MAX_MATCHES}). Cheaper than reading whole files to find something.`,
            shape: {
                pattern: z.string().describe('A JavaScript regular expression, e.g. "def cut_.*tenon".'),
                folder: z.string().optional().describe('A folder relative to the project folder; the whole project by default.'),
                file_glob: z.string().optional().describe('Only files whose name matches, e.g. "*.py".'),
                ignore_case: z.boolean().optional(),
            },
            effect: 'read',
            run: async ({ pattern, folder, file_glob: nameGlob, ignore_case: ignoreCase }) => {
                const matches = await files.search(pattern, { folder, nameGlob, ignoreCase, maxMatches: MAX_MATCHES });
                return text(matches.length
                    ? matches.join('\n') + (matches.length >= MAX_MATCHES ? `\n(first ${MAX_MATCHES} matches only)` : '')
                    : 'No matches.');
            },
        },
        {
            name: 'read_file',
            description: `Read a text file of the project, with line numbers; at most ${MAX_READ_LINES} lines or ${MAX_READ_CHARS} characters at a time.`,
            shape: {
                file_path: filePath,
                offset: z.number().int().min(1).optional().describe('The first line to read (1-based).'),
                limit: z.number().int().min(1).optional(),
            },
            effect: 'read',
            run: async ({ file_path: file, offset = 1, limit = MAX_READ_LINES }) => {
                const content = await files.read(file);
                if (content === null) throw new Error(`${file} doesn't exist.`);
                const lines = content.split('\n');
                const shown = [];
                let size = 0;
                for (const line of lines.slice(offset - 1, offset - 1 + Math.min(limit, MAX_READ_LINES))) {
                    size += line.length + 8;
                    if (size > MAX_READ_CHARS && shown.length) break;
                    shown.push(line);
                }
                const next = offset + shown.length;
                return text(shown.map((line, i) => `${offset + i}\t${line}`).join('\n')
                    + (next - 1 < lines.length ? `\n(${lines.length} lines in all; read on from line ${next})` : ''));
            },
        },
        {
            name: 'write_file',
            description: 'Create a file in the project, or replace one whole. Prefer edit_file to change part of a file.',
            shape: { file_path: filePath, content: z.string() },
            effect: 'edit',
            run: ({ file_path: file, content }) => oneAtATime(async () => {
                const target = await files.write(file, content);
                return text(`Wrote ${files.relative(target)}.`);
            }),
        },
        {
            name: 'edit_file',
            description: 'Replace text in a project file. old_string must appear exactly once, unless replace_all.',
            shape: {
                file_path: filePath,
                old_string: z.string(),
                new_string: z.string(),
                replace_all: z.boolean().optional(),
            },
            effect: 'edit',
            run: ({ file_path: file, old_string: before, new_string: after, replace_all: all }) => oneAtATime(async () => {
                files.resolve(file, { write: true });
                const content = await files.read(file);
                if (content === null) throw new Error(`${file} doesn't exist.`);
                const count = before ? content.split(before).length - 1 : 0;
                if (count === 0) {
                    throw new Error('old_string was not found in the file.');
                }
                if (count > 1 && !all) {
                    throw new Error(`old_string appears ${count} times; give more context, or set replace_all.`);
                }
                const target = await files.write(file, content.split(before).join(after));
                return text(`Edited ${files.relative(target)} (${all ? count : 1} replacement${all && count > 1 ? 's' : ''}).`);
            }),
        },
    ];
}

module.exports = { createFileTools };
