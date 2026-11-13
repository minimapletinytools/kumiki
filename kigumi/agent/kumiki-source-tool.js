/**
 * The kumiki_source tool: list, read and search the kumiki library the project's Python imports (in
 * its .venv, or the checkout an editable install points at) and kumiki's example frames, read-only.
 * For agents that can't read those folders themselves, such as MCP clients without file access.
 */

const path = require('path');
const fs = require('fs');
const { z } = require('zod');
const { createProjectFiles } = require('./project-files');
const { numberedLines } = require('./file-tools');

const MAX_LISTED = 500;
const MAX_MATCHES = 100;

const text = (value) => [{ type: 'text', text: value }];

/**
 * The tool over `source()`, kumiki's package folder, and `examples()`, its example frames' folder
 * (each null until found). Paths are kumiki/... and examples/...
 */
function kumikiSourceTool({ source, examples }) {
    function roots() {
        const found = source();
        if (!found) throw new Error('kumiki\'s source isn\'t found yet: open a project whose .venv has kumiki.');
        const kumiki = fs.realpathSync(found);
        const frames = examples() && fs.realpathSync(examples());
        return [
            { name: 'kumiki', folder: kumiki, files: createProjectFiles({ root: () => kumiki }),
                // An installed kumiki keeps its examples inside it: they're listed under examples/ only.
                skip: frames && frames.startsWith(kumiki + path.sep) ? path.relative(kumiki, frames) : null },
            ...(frames ? [{ name: 'examples', folder: frames, files: createProjectFiles({ root: () => frames }), skip: null }] : []),
        ];
    }

    /** The root and the path inside it that `wanted` names: kumiki/x.py, examples/..., or a module, kumiki.construction. */
    function locate(wanted) {
        const all = roots();
        let name = String(wanted || '').trim().replace(/^\.\//, '').replace(/\/+$/, '');
        if (/^kumiki(\.\w+)+$/.test(name)) {
            // A package is its folder, listed; a module its file.
            const parts = name.split('.').slice(1).join('/');
            name = `kumiki/${fs.existsSync(path.join(all[0].folder, parts)) ? parts : `${parts}.py`}`;
        }
        const [head, ...rest] = name.split('/');
        const root = all.find((one) => one.name === head);
        if (root) return { root, inner: rest.join('/') };
        return { root: all[0], inner: name };
    }

    /** The absolute path of `inner` in `root`; throws for one outside it (a ../ out of kumiki). */
    function inside(root, inner, wanted) {
        try {
            return root.files.resolve(inner || '.');
        } catch (_error) {
            throw new Error(`${wanted} is outside kumiki's source and examples.`);
        }
    }

    const shown = (root, relative) => `${root.name}/${relative.split(path.sep).join('/')}`;
    const skipped = (root, relative) => root.skip && (relative === root.skip || relative.startsWith(root.skip + path.sep));

    async function listing(roots_, folder) {
        const lines = [];
        for (const { root, inner } of roots_) {
            const found = await root.files.list(inner || undefined, MAX_LISTED);
            for (const absolute of found) {
                const relative = path.relative(root.folder, path.resolve(root.folder, absolute));
                if (!relative.endsWith('.py') && !relative.endsWith('.md') || skipped(root, relative)) continue;
                const count = (await fs.promises.readFile(path.join(root.folder, relative), 'utf8')).split('\n').length;
                lines.push(`${shown(root, relative)} (${count} lines)`);
            }
        }
        if (!lines.length) return `Nothing under ${folder || 'kumiki/ or examples/'}.`;
        return lines.join('\n') + (lines.length >= MAX_LISTED ? `\n(first ${MAX_LISTED} only)` : '');
    }

    return {
        name: 'kumiki_source',
        description: 'Read the kumiki library\'s source, and its example frames, as installed for this project (read-only). '
            + 'With no arguments, lists every file with its length: kumiki/... is the library, examples/... the example frames. '
            + 'With a path (kumiki/construction.py, a module like kumiki.construction, examples/structures/..., or a folder), '
            + 'reads the file with line numbers, a page at a time, or lists the folder. With search, finds a regular expression '
            + 'in them. For one name\'s signature and docstring, kumiki_api is quicker.',
        shape: {
            path: z.string().optional().describe('A file or folder: kumiki/..., examples/..., or a module, e.g. kumiki.construction.'),
            offset: z.number().int().min(1).optional().describe('Reading a file: the first line to read (1-based).'),
            limit: z.number().int().min(1).optional().describe('Reading a file: how many lines.'),
            search: z.string().optional().describe('A JavaScript regular expression to find, e.g. "def cut_.*scarf"; under path if given.'),
            ignore_case: z.boolean().optional(),
        },
        effect: 'read',
        run: async ({ path: wanted, offset, limit, search, ignore_case: ignoreCase }) => {
            if (search) {
                const targets = wanted ? [locate(wanted)] : roots().map((root) => ({ root, inner: '' }));
                for (const { root, inner } of targets) inside(root, inner, wanted);
                const matches = [];
                for (const { root, inner } of targets) {
                    const found = await root.files.search(search, { folder: inner || undefined, nameGlob: '*.py',
                        ignoreCase, maxMatches: MAX_MATCHES });
                    for (const line of found) {
                        if (line.startsWith('(')) { matches.push(line); continue; }
                        if (skipped(root, line.split(':')[0])) continue;
                        matches.push(`${root.name}/${line}`);
                    }
                }
                const kept = matches.slice(0, MAX_MATCHES);
                return text(kept.length ? kept.join('\n') + (matches.length > MAX_MATCHES ? `\n(first ${MAX_MATCHES} matches only)` : '')
                    : 'No matches.');
            }
            if (!wanted) return text(await listing(roots().map((root) => ({ root, inner: '' }))));
            const { root, inner } = locate(wanted);
            const target = inside(root, inner, wanted);
            if (!fs.existsSync(target)) throw new Error(`${wanted} isn't in kumiki's source or examples. List them with no path.`);
            if (fs.statSync(target).isDirectory()) return text(await listing([{ root, inner }], wanted));
            const content = await root.files.read(target);
            return text(`${shown(root, path.relative(root.folder, target))}\n${numberedLines(content, offset, limit)}`);
        },
    };
}

module.exports = { kumikiSourceTool };
