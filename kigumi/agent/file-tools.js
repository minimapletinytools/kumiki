/**
 * The built-in agent's file tools, in the same shape as Kigumi's (agent/tools.js): read, list, write
 * and edit files, inside the project folder only. Node's; a web host would supply its own.
 */

const fs = require('fs');
const path = require('path');
const { z } = require('zod');

const text = (value) => [{ type: 'text', text: value }];

/** Folders list_files never walks into. */
const SKIPPED = new Set(['.git', 'node_modules', '.venv', '__pycache__', '.kigumi']);
const MAX_LISTED = 500;
const MAX_READ_LINES = 2000;

/**
 * @param {object} options
 * @param {() => string|null} options.root  the project folder
 */
function createFileTools({ root }) {
    /** The absolute path of `relative` (or absolute) `file`, refusing anything outside the project. */
    function resolve(file) {
        const base = root();
        if (!base) {
            throw new Error('No project folder is open.');
        }
        const resolved = path.resolve(base, file || '.');
        const inside = path.relative(base, resolved);
        if (inside.startsWith('..') || path.isAbsolute(inside)) {
            throw new Error(`${file} is outside the project folder.`);
        }
        return resolved;
    }

    const filePath = z.string().describe('A path relative to the project folder (or absolute, inside it).');

    return [
        {
            name: 'list_files',
            description: 'List the files under a folder of the project (the whole project by default).',
            shape: { folder: z.string().optional().describe('A folder relative to the project folder.') },
            readOnly: true,
            run: async ({ folder }) => {
                const start = resolve(folder);
                const found = [];
                const walk = async (dir) => {
                    for (const entry of await fs.promises.readdir(dir, { withFileTypes: true })) {
                        if (found.length >= MAX_LISTED) return;
                        const full = path.join(dir, entry.name);
                        if (entry.isDirectory()) {
                            if (!SKIPPED.has(entry.name)) await walk(full);
                        } else {
                            found.push(path.relative(root(), full));
                        }
                    }
                };
                await walk(start);
                return text(found.join('\n') + (found.length >= MAX_LISTED ? `\n(first ${MAX_LISTED} only)` : ''));
            },
        },
        {
            name: 'read_file',
            description: `Read a text file of the project, with line numbers; at most ${MAX_READ_LINES} lines at a time.`,
            shape: {
                file_path: filePath,
                offset: z.number().int().min(1).optional().describe('The first line to read (1-based).'),
                limit: z.number().int().min(1).optional(),
            },
            readOnly: true,
            run: async ({ file_path: file, offset = 1, limit = MAX_READ_LINES }) => {
                const lines = (await fs.promises.readFile(resolve(file), 'utf8')).split('\n');
                const shown = lines.slice(offset - 1, offset - 1 + Math.min(limit, MAX_READ_LINES));
                return text(shown.map((line, i) => `${offset + i}\t${line}`).join('\n')
                    + (offset - 1 + shown.length < lines.length ? `\n(${lines.length} lines in all)` : ''));
            },
        },
        {
            name: 'write_file',
            description: 'Create a file in the project, or replace one whole. Prefer edit_file to change part of a file.',
            shape: { file_path: filePath, content: z.string() },
            readOnly: false,
            run: async ({ file_path: file, content }) => {
                const target = resolve(file);
                await fs.promises.mkdir(path.dirname(target), { recursive: true });
                await fs.promises.writeFile(target, content, 'utf8');
                return text(`Wrote ${path.relative(root(), target)}.`);
            },
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
            readOnly: false,
            run: async ({ file_path: file, old_string: before, new_string: after, replace_all: all }) => {
                const target = resolve(file);
                const content = await fs.promises.readFile(target, 'utf8');
                const count = before ? content.split(before).length - 1 : 0;
                if (count === 0) {
                    throw new Error('old_string was not found in the file.');
                }
                if (count > 1 && !all) {
                    throw new Error(`old_string appears ${count} times; give more context, or set replace_all.`);
                }
                await fs.promises.writeFile(target, content.split(before).join(after), 'utf8');
                return text(`Edited ${path.relative(root(), target)} (${all ? count : 1} replacement${all && count > 1 ? 's' : ''}).`);
            },
        },
    ];
}

module.exports = { createFileTools };
