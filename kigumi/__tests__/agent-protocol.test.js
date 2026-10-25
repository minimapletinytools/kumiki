/**
 * The agent panel and its session send each other only the messages webview/agent/protocol.js
 * lists, and each side handles every one the other sends: the protocol can't drift between them.
 */
const fs = require('fs');
const path = require('path');

const { PANEL_TO_SESSION, SESSION_TO_PANEL } = require('../webview/agent/protocol.js');

const read = (folder) => fs.readdirSync(folder).filter((name) => name.endsWith('.js'))
    .map((name) => fs.readFileSync(path.join(folder, name), 'utf8')).join('\n');
const sessionSource = read(path.join(__dirname, '..', 'agent'));
const panelSource = read(path.join(__dirname, '..', 'webview', 'agent'));
const types = (source, pattern) => new Set([...source.matchAll(pattern)].map((match) => match[1]));

describe('the agent panel protocol', () => {
    const sentBySession = types(sessionSource, /type: '(agent:\w+)'/g);
    const handledBySession = types(sessionSource, /message\.type === '(agent:\w+)'/g);
    const sentByPanel = types(panelSource, /type: '(agent:\w+)'/g);
    const handledByPanel = types(panelSource.slice(panelSource.indexOf('const HANDLERS')), /'(agent:\w+)': \(/g);

    test('the session sends only what the protocol lists, and the panel handles all of it', () => {
        const panelBound = [...sentBySession].filter((type) => !PANEL_TO_SESSION.includes(type));
        expect(panelBound.filter((type) => !SESSION_TO_PANEL.includes(type))).toEqual([]);
        expect(SESSION_TO_PANEL.filter((type) => !handledByPanel.has(type))).toEqual([]);
        expect([...handledByPanel].filter((type) => !SESSION_TO_PANEL.includes(type))).toEqual([]);
    });

    test('the panel sends only what the protocol lists, and the session handles all of it', () => {
        expect([...sentByPanel].filter((type) => !PANEL_TO_SESSION.includes(type))).toEqual([]);
        expect(PANEL_TO_SESSION.filter((type) => !handledBySession.has(type))).toEqual([]);
    });

    test('nothing is listed that nobody sends', () => {
        expect(SESSION_TO_PANEL.filter((type) => !sentBySession.has(type))).toEqual([]);
        expect(PANEL_TO_SESSION.filter((type) => !sentByPanel.has(type))).toEqual([]);
    });
});
