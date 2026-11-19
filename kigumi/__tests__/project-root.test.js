// Which project a frame belongs to, so which environment builds it (project-root.js).
const fs = require('fs');
const os = require('os');
const path = require('path');
const { resolveProjectEnvironment, KUMIKI_YAML_RELATIVE_PATH, LEGACY_KIGUMI_YAML_NAME } = require('../project-root');

function folder(files = {}) {
    const root = fs.realpathSync(fs.mkdtempSync(path.join(os.tmpdir(), 'kigumi-root-')));
    for (const [name, text] of Object.entries(files)) {
        fs.mkdirSync(path.dirname(path.join(root, name)), { recursive: true });
        fs.writeFileSync(path.join(root, name), text);
    }
    return root;
}

test('a frame anywhere in a project belongs to the project its marker is in', () => {
    const root = folder({ [KUMIKI_YAML_RELATIVE_PATH]: 'kumiki_version: latest\n', 'sheds/small/shed.py': '' });
    expect(resolveProjectEnvironment({ filePath: path.join(root, 'sheds/small/shed.py'), workspaceRoot: root }))
        .toMatchObject({ projectRoot: root, isLocalDev: false, marker: KUMIKI_YAML_RELATIVE_PATH, source: 'file' });
});

test('a kumiki checkout is local development; a folder named kumiki alone is not', () => {
    const checkout = folder({ 'kumiki/__init__.py': '', 'pyproject.toml': '', 'patterns/a.py': '' });
    expect(resolveProjectEnvironment({ filePath: path.join(checkout, 'patterns/a.py') }))
        .toMatchObject({ projectRoot: checkout, isLocalDev: true, marker: 'kumiki' });
    const notOne = folder({ 'kumiki/notes.txt': '', 'a.py': '' });
    expect(resolveProjectEnvironment({ filePath: path.join(notOne, 'a.py'), createMarkerIfMissing: false }))
        .toMatchObject({ isLocalDev: false, marker: null });
});

test('a shipped pattern outside the workspace builds in the workspace project', () => {
    const project = folder({ [KUMIKI_YAML_RELATIVE_PATH]: '' });
    const library = folder({ [KUMIKI_YAML_RELATIVE_PATH]: '', 'patterns/joint.py': '' });
    expect(resolveProjectEnvironment({ filePath: path.join(library, 'patterns/joint.py'), workspaceRoot: project }))
        .toMatchObject({ projectRoot: project, source: 'workspace-preferred' });
});

test('an older project\'s .kigumi.yaml still marks it, and is not rewritten', () => {
    const root = folder({ [LEGACY_KIGUMI_YAML_NAME]: 'old\n', 'a.py': '' });
    expect(resolveProjectEnvironment({ filePath: path.join(root, 'a.py'), workspaceRoot: root }))
        .toMatchObject({ projectRoot: root, marker: LEGACY_KIGUMI_YAML_NAME });
    expect(fs.existsSync(path.join(root, KUMIKI_YAML_RELATIVE_PATH))).toBe(false);
    expect(fs.readFileSync(path.join(root, LEGACY_KIGUMI_YAML_NAME), 'utf8')).toBe('old\n');
});

test('with no marker the workspace becomes the project, marked, unless told not to write', () => {
    const root = folder({ 'a.py': '' });
    expect(resolveProjectEnvironment({ filePath: path.join(root, 'a.py'), workspaceRoot: root, createMarkerIfMissing: false }))
        .toMatchObject({ projectRoot: root, marker: null, source: 'workspace-fallback' });
    expect(fs.existsSync(path.join(root, KUMIKI_YAML_RELATIVE_PATH))).toBe(false);
    resolveProjectEnvironment({ filePath: path.join(root, 'a.py'), workspaceRoot: root });
    expect(fs.readFileSync(path.join(root, KUMIKI_YAML_RELATIVE_PATH), 'utf8')).toBe('kumiki_version: latest\n');
});

test('a lone file with no workspace is its own folder\'s project; with nothing, there is none', () => {
    const root = folder({ 'a.py': '' });
    expect(resolveProjectEnvironment({ filePath: path.join(root, 'a.py'), createMarkerIfMissing: false }))
        .toMatchObject({ projectRoot: root, source: 'file-fallback' });
    expect(resolveProjectEnvironment({})).toEqual({ projectRoot: null, isLocalDev: false, marker: null, source: 'none' });
});
