/**
 * The agent panel's page, loaded in a hidden Electron window as the app serves it, with its controls
 * used (test/agent-panel/drive.js). Skipped where Electron can't run: not installed, or Linux with no display.
 */
const fs = require('fs');
const path = require('path');
const { spawnSync } = require('child_process');

let electron = null;
try {
    electron = require('electron');
} catch (_error) {
    electron = null;
}
const canRun = typeof electron === 'string' && fs.existsSync(electron) && (process.platform !== 'linux' || Boolean(process.env.DISPLAY));

(canRun ? describe : describe.skip)('the agent panel page', () => {
    let result;

    beforeAll(() => {
        const env = { ...process.env };
        delete env.ELECTRON_RUN_AS_NODE;
        // Linux CI's Electron has no set-up sandbox helper; the switch must come before it starts.
        const args = [...(process.platform === 'linux' ? ['--no-sandbox'] : []), path.join(__dirname, '..', 'test', 'agent-panel', 'drive.js')];
        const ran = spawnSync(electron, args, { encoding: 'utf8', timeout: 60000, env });
        const line = (ran.stdout || '').trim().split('\n').pop();
        result = line && line.startsWith('{') ? JSON.parse(line) : { failure: `${ran.stderr || ''}${ran.error || ''}`.slice(-2000) };
    }, 70000);

    test('loads without errors and says it is ready', () => {
        expect(result.failure).toBeUndefined();
        expect(result.errors).toEqual([]);
        expect(result.ready).toBe(true);
    });

    test('Enter sends the request', () => {
        expect(result.prompt).toEqual({ type: 'agent:prompt', text: 'make it taller', images: [] });
    });

    test('the settings menu opens and sets the permission mode; the model picker sets the model', () => {
        expect(result.settingsOpen).toBe(true);
        expect(result.setting).toEqual({ type: 'agent:setSetting', key: 'agent.permissionMode', value: 'auto' });
        expect(result.setModel).toEqual({ type: 'agent:setModel', id: 'm2' });
    });

    test('history, new conversation, and stop while busy each ask the session', () => {
        expect(result.history).toEqual({ type: 'agent:listConversations' });
        expect(result.clear).toEqual({ type: 'agent:clear' });
        expect(result.stop).toEqual({ type: 'agent:stop' });
    });

    test('a permission card answers its question; one left when the turn ends can no longer be answered', () => {
        expect(result.answer).toEqual({ type: 'agent:permissionAnswer', requestId: 7, allow: true, always: false });
        expect(result.unansweredLeft).toBe(0);
    });

    test('a replayed conversation is drawn', () => {
        expect(result.drawn).toContain('a sawhorse please');
        expect(result.drawn).toContain('Here is a sawhorse.');
        expect(result.drawn).toContain('check_frame');
    });
});
