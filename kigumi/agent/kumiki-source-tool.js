/**
 * The kumiki_source tool: list, read and search kumiki's docs, the kumiki library the project's Python
 * imports (in its .venv, or the checkout an editable install points at) and kumiki's example frames,
 * read-only. For agents that can't read those folders themselves, such as MCP clients without file access.
 */

const path = require('path');
const fs = require('fs');
const { z } = require('zod');
const { createProjectFiles } = require('./project-files');
const { numberedLines } = require('./file-tools');
const { listDocs } = require('./kumiki-docs');

const MAX_LISTED = 500;
const MAX_MATCHES = 100;

const text = (value) => [{ type: 'text', text: value }];

/**
 * The tool over `docs()`, kumiki's docs folder, `source()`, its package folder, and `examples()`, its
 * example frames' folder (each null until found). Paths are docs/..., kumiki/... and examples/...
 */
function kumikiSourceTool({ docs = () => null, source, examples }) {
    function roots() {
        const real = (folder) => (folder && fs.existsSync(folder) ? fs.realpathSync(folder) : null);
        const [docsFolder, kumiki, frames] = [real(docs()), real(source()), real(examples())];
        if (!docsFolder && !kumiki) throw new Error('kumiki isn\'t found yet: open a project whose .venv has kumiki.');
        const root = (name, folder, kind) => ({ name, folder, kind, files: createProjectFiles({ root: () => folder }),
            // An installed kumiki keeps its docs and examples inside it: they're listed in their own sections only.
            skip: name === 'kumiki' ? [docsFolder, frames].filter((one) => one && one.startsWith(folder + path.sep))
                .map((one) => path.relative(folder, one)) : [] });
        return [
            ...(docsFolder ? [root('docs', docsFolder, '*.md')] : []),
            ...(kumiki ? [root('kumiki', kumiki, '*.py')] : []),
            ...(frames ? [root('examples', frames, '*.py')] : []),
        ];
    }

    /** The root and the path inside it that `wanted` names: docs/..., kumiki/x.py, examples/..., a doc's name, or a module. */
    function locate(wanted) {
        const all = roots();
        const named = (name) => all.find((one) => one.name === name);
        let name = String(wanted || '').trim().replace(/^\.\//, '').replace(/\/+$/, '');
        if (/^kumiki(\.\w+)+$/.test(name) && named('kumiki')) {
            // A package is its folder, listed; a module its file.
            const parts = name.split('.').slice(1).join('/');
            name = `kumiki/${fs.existsSync(path.join(named('kumiki').folder, parts)) ? parts : `${parts}.py`}`;
        }
        const [head, ...rest] = name.split('/');
        const root = named(head);
        // A doc by its name alone, with or without .md: api_cheat_sheet.
        if (root && root.name === 'docs' && rest.length === 1 && !rest[0].endsWith('.md')) return { root, inner: `${rest[0]}.md` };
        if (root) return { root, inner: rest.join('/') };
        const doc = named('docs') && path.join(named('docs').folder, `${name.replace(/\.md$/, '')}.md`);
        if (doc && !name.includes('/') && fs.existsSync(doc)) return { root: named('docs'), inner: path.basename(doc) };
        return { root: named('kumiki') || all[0], inner: name };
    }

    /** The absolute path of `inner` in `root`; throws for one outside it (a ../ out of kumiki). */
    function inside(root, inner, wanted) {
        try {
            return root.files.resolve(inner || '.');
        } catch (_error) {
            throw new Error(`${wanted} is outside kumiki's docs, source and examples.`);
        }
    }

    const shown = (root, relative) => `${root.name}/${relative.split(path.sep).join('/')}`;
    const skipped = (root, relative) => root.skip.some((one) => relative === one || relative.startsWith(one + path.sep));

    async function listing(targets, folder) {
        const lines = [];
        for (const { root, inner } of targets) {
            if (root.name === 'docs' && !inner) {
                // The docs in the order to read them, each with what it's for.
                for (const doc of listDocs(root.folder)) lines.push(`docs/${doc.name}.md: ${doc.about}`);
                continue;
            }
            for (const absolute of await root.files.list(inner || undefined, MAX_LISTED)) {
                const relative = path.relative(root.folder, path.resolve(root.folder, absolute));
                if (!/\.(py|md)$/.test(relative) || skipped(root, relative)) continue;
                const count = (await fs.promises.readFile(path.join(root.folder, relative), 'utf8')).split('\n').length;
                lines.push(`${shown(root, relative)} (${count} lines)`);
            }
        }
        if (!lines.length) return `Nothing under ${folder || 'docs/, kumiki/ or examples/'}.`;
        return lines.join('\n') + (lines.length >= MAX_LISTED ? `\n(first ${MAX_LISTED} only)` : '');
    }

    return {
        name: 'kumiki_source',
        description: 'Read kumiki\'s docs, its library source and its example frames, as installed for this project (read-only). '
            + 'With no arguments, lists them: docs/... (read docs/agent_usage_instructions.md and docs/api_cheat_sheet.md '
            + 'before writing a frame), kumiki/... the library, examples/... the example frames. With a path (docs/concepts.md, '
            + 'kumiki/construction.py, a module like kumiki.construction, examples/structures/..., or a folder), reads the file '
            + 'with line numbers, a page at a time, or lists the folder. With search, finds a regular expression in them. '
            + 'For one name\'s signature and docstring, kumiki_api is quicker.',
        shape: {
            path: z.string().optional().describe('A file or folder: docs/..., kumiki/..., examples/..., or a module, e.g. kumiki.construction.'),
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
                    const found = await root.files.search(search, { folder: inner || undefined, nameGlob: root.kind,
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
            if (!fs.existsSync(target)) throw new Error(`${wanted} isn't in kumiki's docs, source or examples. List them with no path.`);
            if (fs.statSync(target).isDirectory()) return text(await listing([{ root, inner }], wanted));
            const content = await root.files.read(target);
            return text(`${shown(root, path.relative(root.folder, target))}\n${numberedLines(content, offset, limit)}`);
        },
    };
}

module.exports = { kumikiSourceTool };
