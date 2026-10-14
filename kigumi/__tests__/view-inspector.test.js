const { ViewInspector } = require('../view-inspector');

function fakeSurface() {
  const listeners = [];
  return {
    posted: [],
    postMessage(message) { this.posted.push(message); return Promise.resolve(true); },
    onMessage: (callback) => listeners.push(callback),
    fromPage: (message) => listeners.forEach((listener) => listener(message)),
    last(type) { return [...this.posted].reverse().find((message) => message.type === type); },
  };
}

function fakeSession(filePath) {
  const logListeners = new Set();
  const stateListeners = new Set();
  return {
    filePath,
    panel: { title: filePath.slice(1) },
    logLines: ['built'],
    viewState: { members: [{ key: 'post' }], selection: [] },
    selected: [],
    onLogLine: (callback) => { logListeners.add(callback); return { dispose: () => logListeners.delete(callback) }; },
    onViewState: (callback) => { stateListeners.add(callback); return { dispose: () => stateListeners.delete(callback) }; },
    selectMembers(keys, options) { this.selected.push([keys, options]); },
    calls: [],
    callViewPanel(method, args, seq) { this.calls.push([method, args, seq]); },
    clearLogLines() { this.logLines = []; },
    log: (line) => logListeners.forEach((listener) => listener(line)),
    publish: (state) => stateListeners.forEach((listener) => listener(state)),
    listenerCount: () => logListeners.size + stateListeners.size,
  };
}

describe('the view inspector', () => {
  test('shows the current view, then follows its log and state', () => {
    const surface = fakeSurface();
    const session = fakeSession('/a.py');
    const inspector = new ViewInspector({ surface, currentSession: () => session });

    inspector.sync();
    expect(surface.last('inspector:view')).toEqual({
      type: 'inspector:view',
      view: { title: 'a.py', filePath: '/a.py' },
      log: ['built'],
      state: { members: [{ key: 'post' }], selection: [] },
      strings: expect.objectContaining({ 'common.enabled': 'enabled' }),
    });

    session.log('rebuilt');
    session.publish({ members: [], selection: ['post'] });
    expect(surface.last('inspector:log')).toEqual({ type: 'inspector:log', line: 'rebuilt' });
    expect(surface.last('inspector:state').state.selection).toEqual(['post']);
  });

  test('moves to another view, leaving the first one alone', () => {
    const surface = fakeSurface();
    const first = fakeSession('/a.py');
    const second = fakeSession('/b.py');
    let current = first;
    const inspector = new ViewInspector({ surface, currentSession: () => current });

    inspector.sync();
    current = second;
    inspector.sync();
    expect(surface.last('inspector:view').view.filePath).toBe('/b.py');
    expect(first.listenerCount()).toBe(0);

    current = null;
    inspector.sync();
    expect(surface.last('inspector:view').view).toBeNull();
  });

  test('a click in the inspector selects in the view', () => {
    const surface = fakeSurface();
    const session = fakeSession('/a.py');
    const inspector = new ViewInspector({ surface, currentSession: () => session });
    inspector.sync();

    surface.fromPage({ type: 'inspector:select', memberKeys: ['post'], additive: true });
    expect(session.selected).toEqual([[['post'], { additive: true }]]);
  });

  test('a change to an option or a parameter goes to the view', () => {
    const surface = fakeSurface();
    const session = fakeSession('/a.py');
    const inspector = new ViewInspector({ surface, currentSession: () => session });
    inspector.sync();

    surface.fromPage({ type: 'inspector:call', method: 'setKiwariDraft', args: [0, 'span', '2m'], seq: 7 });
    expect(session.calls).toEqual([['setKiwariDraft', [0, 'span', '2m'], 7]]);
  });
});
