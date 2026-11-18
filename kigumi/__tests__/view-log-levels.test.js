const { FrameViewSession, pythonLineLevel } = require('../frame-view-session');

/** A view session's log, writing to fakes. */
function fakeSession() {
    const fake = {
        filePath: '/p/frame.py', slotName: 'main', sessionType: 'frame',
        appendSessionLog: jest.fn(), channel: { appendLine: jest.fn() },
    };
    fake.log = (message, level) => FrameViewSession.prototype.log.call(fake, message, level);
    return fake;
}

describe('a view log line has the level it is given', () => {
    test('an explicit level reaches both the view log and the channel', () => {
        const session = fakeSession();
        session.log('[drawing] requestDrawings error: boom', 'error');
        expect(session.appendSessionLog.mock.calls[0][0].level).toBe('error');
        expect(session.channel.appendLine).toHaveBeenCalledWith('[frame.py] [drawing] requestDrawings error: boom', 'error');
    });

    test('without one, a tag in the line decides, and timings are debug', () => {
        const session = fakeSession();
        session.log('[update] [warn] offline');
        session.log('[refresh][timing] step=x');
        session.log('[refresh] Reloading');
        expect(session.appendSessionLog.mock.calls.map(([entry]) => entry.level)).toEqual(['warn', 'debug', 'info']);
    });
});

describe("the level of the runner's lines", () => {
    test.each([
        ['[warn] skipping footprint 2: bad', 'warn'],
        ['[error] skipping geometry for post: boom', 'error'],
        ['/p/frame.py:12: FrameWarning: the joint cuts into air', 'warn'],
        ['placed 12 top plates', 'info'],
        ['Warning: a word in what the frame printed', 'info'],
    ])('%s is %s', (line, level) => {
        expect(pythonLineLevel(line)).toBe(level);
    });
});
