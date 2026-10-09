const crypto = require('crypto');
const fs = require('fs');
const os = require('os');
const path = require('path');

const {
  AGENTS_BLOCK, LEGACY_AGENTS_TEXTS, projectDocsVersion, removeLegacyDocs, syncProjectDocsIfStale, updateAgentsFile,
  writeProjectDocs,
} = require('../project-docs');

const sha256 = (text) => crypto.createHash('sha256').update(text).digest('hex');

describe('project docs', () => {
  let root;
  let source;

  beforeEach(() => {
    root = fs.mkdtempSync(path.join(os.tmpdir(), 'kigumi-docs-test-'));
    source = path.join(root, 'kumiki-docs');
    fs.mkdirSync(path.join(source, 'internal'), { recursive: true });
    fs.mkdirSync(path.join(source, 'assets'), { recursive: true });
    fs.writeFileSync(path.join(source, 'agent_usage_instructions.md'), 'usage');
    fs.writeFileSync(path.join(source, 'concepts.md'), 'concepts');
    fs.writeFileSync(path.join(source, 'index.md'), 'website');
    fs.writeFileSync(path.join(source, 'internal', 'notes.md'), 'ours');
    fs.writeFileSync(path.join(source, 'assets', 'logo.png'), 'png');
  });

  afterEach(() => fs.rmSync(root, { recursive: true, force: true }));

  test('writes the agent docs, the skills, a README and the version, and nothing for the website', () => {
    const files = writeProjectDocs(root, source, '0.8.1');

    expect(files).toEqual(expect.arrayContaining([
      'agent_usage_instructions.md', 'concepts.md', 'README.md', 'kumiki-version.txt',
      'skills/init-kumiki-project/SKILL.md',
    ]));
    expect(files.some((file) => /^(internal|assets)\/|^index\.md$/.test(file))).toBe(false);
    expect(projectDocsVersion(root)).toBe('0.8.1');
  });

  test('replaces the folder whole', () => {
    writeProjectDocs(root, source, '0.8.0');
    fs.writeFileSync(path.join(root, '.kigumi', 'docs', 'concepts.md'), 'edited');
    fs.writeFileSync(path.join(root, '.kigumi', 'docs', 'extra.md'), 'added');

    writeProjectDocs(root, source, '0.8.1');

    expect(fs.readFileSync(path.join(root, '.kigumi', 'docs', 'concepts.md'), 'utf8')).toBe('concepts');
    expect(fs.existsSync(path.join(root, '.kigumi', 'docs', 'extra.md'))).toBe(false);
  });

  test('re-syncs only when the installed kumiki is a different version', async () => {
    writeProjectDocs(root, source, '0.8.0');
    fs.writeFileSync(path.join(root, '.kigumi', 'docs', 'extra.md'), 'added');

    expect(await syncProjectDocsIfStale(root, null, '0.8.0')).toBeNull();
    expect(await syncProjectDocsIfStale(root, null, 'unknown')).toBeNull();
    expect(fs.existsSync(path.join(root, '.kigumi', 'docs', 'extra.md'))).toBe(true);

    // No python to ask, so it falls back to the extension's own copy.
    const synced = await syncProjectDocsIfStale(root, null, '0.8.1');

    expect(synced.files).toContain('agent_usage_instructions.md');
    expect(projectDocsVersion(root)).toBe('0.8.1');
    expect(fs.existsSync(path.join(root, '.kigumi', 'docs', 'extra.md'))).toBe(false);
  });

  test('removes only old docs/ copies exactly as Kigumi wrote them', () => {
    fs.mkdirSync(path.join(root, 'docs', 'skills', 'init-kumiki-project'), { recursive: true });
    fs.writeFileSync(path.join(root, 'docs', 'concepts.md'), 'as shipped');
    fs.writeFileSync(path.join(root, 'docs', 'skills', 'init-kumiki-project', 'SKILL.md'), 'as shipped too');
    fs.writeFileSync(path.join(root, 'docs', 'agent_usage_instructions.md'), 'edited by the user');
    fs.writeFileSync(path.join(root, 'docs', 'mine.md'), 'the user\'s own');
    const known = {
      'concepts.md': [sha256('as shipped')],
      'skills/init-kumiki-project/SKILL.md': [sha256('as shipped too')],
      'agent_usage_instructions.md': [sha256('as shipped')],
    };

    const result = removeLegacyDocs(root, known);

    expect(result.removed.sort()).toEqual(['docs/concepts.md', 'docs/skills/init-kumiki-project/SKILL.md']);
    expect(result.kept).toEqual(['docs/agent_usage_instructions.md']);
    expect(fs.existsSync(path.join(root, 'docs', 'skills'))).toBe(false);
    expect(fs.readFileSync(path.join(root, 'docs', 'mine.md'), 'utf8')).toBe('the user\'s own');
  });

  test('every released copy is known', () => {
    const known = JSON.parse(fs.readFileSync(path.join(__dirname, '..', 'legacy-doc-hashes.json'), 'utf8'));
    expect(Object.keys(known)).toEqual(expect.arrayContaining([
      'agent_usage_instructions.md', 'concepts.md', 'skills/init-kumiki-project/SKILL.md']));
  });

  describe('AGENTS.md', () => {
    const agents = () => fs.readFileSync(path.join(root, 'AGENTS.md'), 'utf8');

    test('a new file is just the block', () => {
      expect(updateAgentsFile(root)).toEqual({ created: true, changed: true });
      expect(agents()).toBe(`# Agent Instructions\n\n${AGENTS_BLOCK}\n`);
    });

    test.each(LEGACY_AGENTS_TEXTS.map((text, i) => [i, text]))('an earlier Kigumi\'s whole file %i becomes the block', (_i, text) => {
      fs.writeFileSync(path.join(root, 'AGENTS.md'), text);

      updateAgentsFile(root);

      expect(agents()).toBe(`# Agent Instructions\n\n${AGENTS_BLOCK}\n`);
    });

    test('an earlier Kigumi\'s text appended to the user\'s is replaced in place', () => {
      fs.writeFileSync(path.join(root, 'AGENTS.md'), `# Mine\n\nKeep me.\n\n\n${LEGACY_AGENTS_TEXTS[0]}`);

      updateAgentsFile(root);

      expect(agents()).toBe(`# Mine\n\nKeep me.\n\n\n${AGENTS_BLOCK}\n`);
    });

    test('the block is refreshed in place and the rest left alone', () => {
      fs.writeFileSync(path.join(root, 'AGENTS.md'),
        '# Mine\n\n<!-- kigumi:begin -->\nold pointer\n<!-- kigumi:end -->\n\nAfter.\n');

      updateAgentsFile(root);

      expect(agents()).toBe(`# Mine\n\n${AGENTS_BLOCK}\n\nAfter.\n`);
    });

    test('a file of the user\'s own gets the block at the end, once', () => {
      fs.writeFileSync(path.join(root, 'AGENTS.md'), '# Mine');

      expect(updateAgentsFile(root).changed).toBe(true);
      expect(updateAgentsFile(root).changed).toBe(false);
      expect(agents()).toBe(`# Mine\n\n${AGENTS_BLOCK}\n`);
    });
  });
});
