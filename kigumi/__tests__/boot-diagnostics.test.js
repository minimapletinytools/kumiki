const { describeError, installBootDiagnostics } = require('../webview/boot-diagnostics.js');

function fakeScope() {
    const listeners = {};
    return {
        listeners,
        addEventListener(type, handler) { listeners[type] = handler; },
        console: { error: jest.fn() },
    };
}

function fakeApi() {
    return { posted: [], postMessage(message) { this.posted.push(message); } };
}

describe('describeError', () => {
    test('an Error keeps its message and the head of its stack', () => {
        const described = describeError(new Error('boom'));
        expect(described.message).toBe('boom');
        expect(described.stack).toContain('Error: boom');
    });

    test('a thrown non-Error is still said out loud', () => {
        expect(describeError('just a string').message).toBe('just a string');
        expect(describeError(404).message).toBe('404');
    });

    test('a thrown nothing does not become "undefined"', () => {
        expect(describeError(undefined).message).toBe('thrown value was empty');
        expect(describeError(null).message).toBe('thrown value was empty');
    });
});

describe('installBootDiagnostics', () => {
    test('an uncaught error is reported with where it came from', () => {
        const scope = fakeScope();
        const api = fakeApi();
        installBootDiagnostics(scope, { api });

        scope.listeners.error({
            error: new Error('cannot read camera of null'),
            filename: 'viewer-app.js',
            lineno: 42,
            colno: 7,
        });

        expect(api.posted).toHaveLength(1);
        const [message] = api.posted;
        expect(message.type).toBe('viewerLog');
        expect(message.level).toBe('error');
        expect(message.details.message).toBe('cannot read camera of null');
        expect(message.details).toMatchObject({ file: 'viewer-app.js', line: 42, column: 7 });
    });

    test('a rejected promise is reported too', () => {
        const scope = fakeScope();
        const api = fakeApi();
        installBootDiagnostics(scope, { api });

        scope.listeners.unhandledrejection({ reason: new Error('runner never answered') });

        expect(api.posted[0].event).toBe('unhandled-rejection');
        expect(api.posted[0].details.message).toBe('runner never answered');
    });

    test('with no extension to tell, it says so where a console would show', () => {
        const scope = fakeScope();
        installBootDiagnostics(scope, { api: null });

        scope.listeners.error({ error: new Error('boom') });

        expect(scope.console.error).toHaveBeenCalled();
    });

    test('a scope that cannot listen is survivable', () => {
        // Node's global has no addEventListener; requiring this file must not
        // throw just because of that.
        expect(() => installBootDiagnostics({}, { api: null })).not.toThrow();
    });
});
