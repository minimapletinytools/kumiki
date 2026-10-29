const fs = require('fs');
const os = require('os');
const path = require('path');

const { headlessHost } = require('../test/evals/run-evals');
const { agentTools } = require('../agent/agent');
const { Checkpoints } = require('../agent/checkpoints');
const { createProjectFiles } = require('../agent/project-files');

const REPO = path.resolve(__dirname, '..', '..');
const PYTHON = path.join(REPO, '.venv', 'bin', 'python');
const STARTER = fs.readFileSync(path.join(REPO, 'patterns', 'structures', 'my_cute_frame.py'), 'utf8');

(fs.existsSync(PYTHON) ? describe : describe.skip)('the evals\' headless host', () => {
    test('an edit builds the frame with Python and says how it went, as in the app', async () => {
        const root = fs.mkdtempSync(path.join(os.tmpdir(), 'kigumi-headless-'));
        fs.writeFileSync(path.join(root, 'frame.py'), STARTER);
        const files = createProjectFiles({ root: () => root });
        const host = headlessHost(files, { kumikiSource: path.join(REPO, 'kumiki'), examples: path.join(REPO, 'patterns') });
        const tools = Object.fromEntries(agentTools(host, { checkpoints: () => new Checkpoints(files) }).map((tool) => [tool.name, tool]));

        const broken = await tools.write_file.run({ file_path: 'frame.py', content: `${STARTER}\nundefined_name\n` });
        expect(broken.at(-1).text).toMatch(/^The view of this file rebuilt with errors:\nerror: NameError/);

        const fixed = await tools.write_file.run({ file_path: 'frame.py', content: STARTER });
        expect(fixed.at(-1).text).toMatch(/^The view of this file rebuilt without errors/);
        expect(JSON.parse((await tools.check_frame.run({ file_path: 'frame.py' }))[0].text).ok).toBe(true);
        fs.rmSync(root, { recursive: true, force: true });
    }, 120000);
});
