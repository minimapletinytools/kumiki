const { loadSystemPrompt, systemPromptFrom } = require('../agent/system-prompt');

test('the prompt leaves out comments, is one line, and adds the part after --- only with the kumiki source', () => {
    const prompt = systemPromptFrom('<!-- a note -->\nBe\nbrief.\n\nAsk.\n\n---\n\nThe source is at {kumikiSource}.\n');
    expect(prompt(null)).toBe('Be brief. Ask.');
    expect(prompt('/lib/kumiki')).toBe('Be brief. Ask. The source is at /lib/kumiki.');
});

test('agent/system-prompt.md reads as the agent\'s instructions', () => {
    const prompt = loadSystemPrompt();
    expect(prompt(null)).toMatch(/^You are the agent inside Kigumi/);
    expect(prompt(null)).not.toContain('kumiki library\'s source is at');
    expect(prompt('/lib/kumiki')).toContain('source is at /lib/kumiki (read-only)');
});

test('the example frames are named where the prompt says, else under the source', () => {
    const prompt = systemPromptFrom('Hi.\n---\nSource {kumikiSource}, examples {kumikiExamples}.');
    expect(prompt('/lib/kumiki', '/repo/patterns')).toBe('Hi. Source /lib/kumiki, examples /repo/patterns.');
    expect(prompt('/lib/kumiki')).toBe('Hi. Source /lib/kumiki, examples /lib/kumiki/patterns.');
});

test("kumiki's examples: inside an installed package, else the checkout's patterns/ beside it", () => {
    const fs = require('fs');
    const os = require('os');
    const path = require('path');
    const { kumikiExamples } = require('../agent/kumiki-source');
    const root = fs.mkdtempSync(path.join(os.tmpdir(), 'kigumi-examples-'));
    fs.mkdirSync(path.join(root, 'kumiki'));
    fs.mkdirSync(path.join(root, 'patterns', 'structures'), { recursive: true });
    expect(kumikiExamples(path.join(root, 'kumiki'))).toBe(path.join(root, 'patterns'));
    fs.mkdirSync(path.join(root, 'kumiki', 'patterns', 'structures'), { recursive: true });
    expect(kumikiExamples(path.join(root, 'kumiki'))).toBe(path.join(root, 'kumiki', 'patterns'));
    expect(kumikiExamples(null)).toBeNull();
    fs.rmSync(root, { recursive: true, force: true });
});
