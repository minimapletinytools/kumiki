const fs = require('fs');
const os = require('os');
const path = require('path');
const { kumikiSourceTool } = require('../agent/kumiki-source-tool');

// An installed kumiki: the package, with its example frames inside it (kumiki/patterns).
function installedKumiki() {
    const site = fs.mkdtempSync(path.join(os.tmpdir(), 'kumiki-source-'));
    const files = {
        'kumiki/__init__.py': 'from .rule import *\n',
        'kumiki/rule.py': Array.from({ length: 30 }, (_, i) => `line_${i + 1} = ${i + 1}`).join('\n'),
        'kumiki/csg/__init__.py': '',
        'kumiki/csg/cutcsg.py': 'def cut_scarf():\n    pass\n',
        'kumiki/patterns/structures/shed.py': 'from kumiki import *\n# a scarf in a shed\n',
        'kumiki/__pycache__/rule.cpython-313.pyc': 'x',
        'secret.txt': 'not kumiki',
    };
    for (const [file, content] of Object.entries(files)) {
        fs.mkdirSync(path.dirname(path.join(site, file)), { recursive: true });
        fs.writeFileSync(path.join(site, file), content);
    }
    return { source: path.join(site, 'kumiki'), examples: path.join(site, 'kumiki', 'patterns') };
}

const folders = installedKumiki();
const tool = kumikiSourceTool({ source: () => folders.source, examples: () => folders.examples });
const run = async (args) => (await tool.run(args))[0].text;

describe('kumiki_source', () => {
    test('with nothing asked, lists the library and the examples, each file once, with its length', async () => {
        const listed = (await run({})).split('\n');
        expect(listed).toEqual(expect.arrayContaining(['kumiki/rule.py (30 lines)', 'kumiki/csg/cutcsg.py (3 lines)',
            'examples/structures/shed.py (3 lines)']));
        expect(listed.some((line) => line.startsWith('kumiki/patterns'))).toBe(false);
        expect(listed.some((line) => line.includes('__pycache__'))).toBe(false);
    });

    test('reads a file by path or module name, a page at a time, saying where to read on', async () => {
        const page = await run({ path: 'kumiki.rule', offset: 10, limit: 2 });
        expect(page).toBe('kumiki/rule.py\n10\tline_10 = 10\n11\tline_11 = 11\n(30 lines in all; read on from line 12)');
        expect(await run({ path: 'kumiki/rule.py' })).toContain('30\tline_30 = 30');
        expect(await run({ path: 'examples/structures/shed.py' })).toContain('2\t# a scarf in a shed');
    });

    test('a package or folder is listed', async () => {
        expect(await run({ path: 'kumiki.csg' })).toContain('kumiki/csg/cutcsg.py (3 lines)');
        expect(await run({ path: 'examples/structures' })).toBe('examples/structures/shed.py (3 lines)');
    });

    test('searches the library and the examples, or one folder', async () => {
        expect((await run({ search: 'scarf' })).split('\n')).toEqual([
            'kumiki/csg/cutcsg.py:1: def cut_scarf():',
            'examples/structures/shed.py:2: # a scarf in a shed',
        ]);
        expect(await run({ search: 'scarf', path: 'examples' })).toBe('examples/structures/shed.py:2: # a scarf in a shed');
        expect(await run({ search: 'no such thing' })).toBe('No matches.');
    });

    test('reads nothing outside kumiki, and says when kumiki is not found', async () => {
        await expect(run({ path: 'kumiki/../secret.txt' })).rejects.toThrow("outside kumiki's source and examples");
        await expect(run({ search: 'kumiki', path: '../' })).rejects.toThrow("outside kumiki's source and examples");
        await expect(run({ path: 'kumiki/nope.py' })).rejects.toThrow("isn't in kumiki's source or examples");
        const none = kumikiSourceTool({ source: () => null, examples: () => null });
        await expect(none.run({})).rejects.toThrow("kumiki's source isn't found yet");
    });
});
