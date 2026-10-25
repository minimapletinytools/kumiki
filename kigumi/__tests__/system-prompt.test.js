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
