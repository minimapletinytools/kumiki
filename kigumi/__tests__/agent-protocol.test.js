/**
 * The agent panel and its session send each other only the messages webview/agent/protocol.js
 * lists, and each side handles every one the other sends: the protocol can't drift between them.
 */
const fs = require('fs');
const path = require('path');
const { spawnSync } = require('child_process');

const { PANEL_TO_SESSION, SESSION_TO_PANEL } = require('../webview/agent/protocol.js');
const { PANEL_MESSAGES, parsePanelMessage } = require('../agent/panel-messages');

const read = (folder) => fs.readdirSync(folder).filter((name) => name.endsWith('.js'))
    .map((name) => fs.readFileSync(path.join(folder, name), 'utf8')).join('\n');
const sessionSource = read(path.join(__dirname, '..', 'agent'));
const panelSource = read(path.join(__dirname, '..', 'webview', 'agent'));
const types = (source, pattern) => new Set([...source.matchAll(pattern)].map((match) => match[1]));

describe('the agent panel protocol', () => {
    const sentBySession = types(sessionSource, /type: '(agent:\w+)'/g);
    // The session's handler table, one method per type; each has a shape (agent/panel-messages.js).
    const handledBySession = types(sessionSource.slice(sessionSource.indexOf('const HANDLERS')), /'(agent:\w+)'\(/g);
    const sentByPanel = types(panelSource, /type: '(agent:\w+)'/g);
    const handledByPanel = types(panelSource.slice(panelSource.indexOf('const HANDLERS')), /'(agent:\w+)': \(/g);

    test('the session sends only what the protocol lists, and the panel handles all of it', () => {
        const panelBound = [...sentBySession].filter((type) => !PANEL_TO_SESSION.includes(type));
        expect(panelBound.filter((type) => !SESSION_TO_PANEL.includes(type))).toEqual([]);
        expect(SESSION_TO_PANEL.filter((type) => !handledByPanel.has(type))).toEqual([]);
        expect([...handledByPanel].filter((type) => !SESSION_TO_PANEL.includes(type))).toEqual([]);
    });

    test('the panel sends only what the protocol lists, and the session has a shape and a handler for each', () => {
        expect([...sentByPanel].filter((type) => !PANEL_TO_SESSION.includes(type))).toEqual([]);
        expect(Object.keys(PANEL_MESSAGES).sort()).toEqual([...PANEL_TO_SESSION].sort());
        expect([...handledBySession].sort()).toEqual([...PANEL_TO_SESSION].sort());
    });

    test('a message not in its shape, or of a type the panel may not send, is not handled', () => {
        expect(parsePanelMessage({ type: 'agent:prompt', text: 'hi' })).toEqual({ type: 'agent:prompt', text: 'hi', images: [] });
        expect(parsePanelMessage({ type: 'agent:prompt', text: 42 })).toBeNull();
        expect(parsePanelMessage({ type: 'agent:restore', turn: 1.5 })).toBeNull();
        expect(parsePanelMessage({ type: 'agent:state' })).toBeNull();
        expect(parsePanelMessage({ type: 'toString' })).toBeNull();
        expect(parsePanelMessage(null)).toBeNull();
    });

    test('nothing is listed that nobody sends', () => {
        expect(SESSION_TO_PANEL.filter((type) => !sentBySession.has(type))).toEqual([]);
        expect(PANEL_TO_SESSION.filter((type) => !sentByPanel.has(type))).toEqual([]);
    });
});

test('every agent panel module parses: one that doesn\'t leaves the whole panel dead', () => {
    const folder = path.join(__dirname, '..', 'webview', 'agent');
    for (const name of fs.readdirSync(folder).filter((file) => file.endsWith('.js'))) {
        const checked = spawnSync(process.execPath, ['--input-type=module', '--check'],
            { input: fs.readFileSync(path.join(folder, name), 'utf8'), encoding: 'utf8' });
        expect({ name, error: checked.status === 0 ? null : checked.stderr.split('\n').slice(0, 3).join('\n') }).toEqual({ name, error: null });
    }
});
