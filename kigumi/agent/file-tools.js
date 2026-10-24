/**
 * The built-in agent's file tools, in the same shape as Kigumi's (agent/tools.js): list, search, read,
 * write and edit files, inside the project folder only. Node's; a web host would supply its own.
 */

const fs = require('fs');
const path = require('path');
const { z } = require('zod');

const text = (value) => [{ type: 'text', text: value }];

/** Folders list_files never walks into. */
const SKIPPED = new Set(['.git', 'node_modules', '.venv', '__pycache__', '.kigumi']);
const MAX_LISTED = 500;
const MAX_MATCHES = 100;
/** Files larger than this are skipped by search_files (generated output, not source). */
const MAX_SEARCHED_BYTES = 1024 * 1024;
const MAX_READ_LINES = 2000;
/** A read's most characters: every read stays in the conversation, which goes with every step. */
const MAX_READ_CHARS = 40000;

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

    /** Every file under `start`, skipping dependency folders, up to `limit`. */
    async function walkFiles(start, limit) {
        const found = [];
        const walk = async (dir) => {
            for (const entry of await fs.promises.readdir(dir, { withFileTypes: true })) {
                if (found.length >= limit) return;
                const full = path.join(dir, entry.name);
                if (entry.isDirectory()) {
                    if (!SKIPPED.has(entry.name)) await walk(full);
                } else {
                    found.push(full);
                }
            }
        };
        await walk(start);
        return found;
    }

    /** A glob on file names (`*.py`), as a RegExp. */
    function globPattern(glob) {
        const escaped = glob.replace(/[.+^${}()|[\]\\]/g, '\\$&').replace(/\*/g, '.*').replace(/\?/g, '.');
        return new RegExp(`^${escaped}$`, 'i');
    }

    return [
        {
            name: 'list_files',
            description: 'List the files under a folder of the project (the whole project by default).',
            shape: { folder: z.string().optional().describe('A folder relative to the project folder.') },
            readOnly: true,
            run: async ({ folder }) => {
                const found = (await walkFiles(resolve(folder), MAX_LISTED)).map((file) => path.relative(root(), file));
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
            readOnly: true,
            run: async ({ pattern, folder, file_glob: fileGlob, ignore_case: ignoreCase }) => {
                const matcher = new RegExp(pattern, ignoreCase ? 'i' : '');
                const names = fileGlob ? globPattern(fileGlob) : null;
                const matches = [];
                for (const file of await walkFiles(resolve(folder), 20000)) {
                    if (names && !names.test(path.basename(file))) continue;
                    const stat = await fs.promises.stat(file);
                    if (stat.size > MAX_SEARCHED_BYTES) continue;
                    const content = await fs.promises.readFile(file, 'utf8');
                    if (content.includes('\u0000')) continue; // binary
                    const lines = content.split('\n');
                    for (let i = 0; i < lines.length && matches.length < MAX_MATCHES; i++) {
                        if (matcher.test(lines[i])) {
                            matches.push(`${path.relative(root(), file)}:${i + 1}: ${lines[i].trim().slice(0, 200)}`);
                        }
                    }
                    if (matches.length >= MAX_MATCHES) break;
                }
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
            readOnly: true,
            run: async ({ file_path: file, offset = 1, limit = MAX_READ_LINES }) => {
                const lines = (await fs.promises.readFile(resolve(file), 'utf8')).split('\n');
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
