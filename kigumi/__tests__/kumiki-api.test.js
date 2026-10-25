const fs = require('fs');
const path = require('path');
const { createKumikiApiTool } = require('../agent/kumiki-api');

const REPO = path.resolve(__dirname, '..', '..');
const PYTHON = path.join(REPO, '.venv', 'bin', 'python');
const tool = createKumikiApiTool({ python: () => PYTHON, env: { PYTHONPATH: REPO } });
const ask = async (args) => JSON.parse((await tool.run(args))[0].text);

(fs.existsSync(PYTHON) ? describe : describe.skip)('kumiki_api', () => {
    test('a function: its signature in plain type names, its docstring, and where it is', async () => {
        const found = await ask({ name: 'create_axis_aligned_timber' });
        expect(found).toMatchObject({ found: true, kind: 'function' });
        expect(found.signature).toMatch(/^\(bottom_position: Matrix, length: .*length_direction: TimberFace/);
        expect(found.doc).toContain('bottom_position');
        expect(found.where).toMatch(/construction\.py:\d+$/);
    }, 60000);

    test("a class: its fields and methods; a method by Class.name", async () => {
        const arrangement = await ask({ name: 'ButtJointTimberArrangement' });
        expect(arrangement.fields.map((field) => field.name)).toContain('front_face_on_butt_timber');
        expect(arrangement.methods.map((method) => method.name)).toContain('check_plane_aligned');
        expect((await ask({ name: 'Frame.from_joints' })).signature).toMatch(/^\(joints/);
    }, 60000);

    test('no such name: close ones instead', async () => {
        const missing = await ask({ name: 'create_axis_timber' });
        expect(missing.found).toBe(false);
        expect(missing.did_you_mean).toContain('create_axis_aligned_timber');
    }, 60000);
});

test('without a Python environment, it says so', async () => {
    await expect(createKumikiApiTool({ python: () => null }).run({ name: 'x' })).rejects.toThrow('no Python environment');
});
