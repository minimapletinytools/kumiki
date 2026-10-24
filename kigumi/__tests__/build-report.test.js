const { buildReport } = require('../build-report');

/** A view session whose builds take `buildMs` and log what `logs` says for each, in turn. */
function session({ buildMs = 50, logs = [[]], building = false } = {}) {
    const entries = [];
    const fake = {
        filePath: '/project/a.py',
        refreshSequence: 0,
        isRefreshing: false,
        pendingRefreshReason: null,
        builds: 0,
        async refresh() {
            fake.isRefreshing = true;
            fake.refreshSequence += 1;
            const logged = logs[Math.min(fake.builds, logs.length - 1)];
            fake.builds += 1;
            await new Promise((resolve) => setTimeout(resolve, buildMs));
            entries.push(...logged.map((entry) => ({ ...entry, timestamp: new Date().toISOString() })));
            fake.isRefreshing = false;
            if (logged.some((entry) => entry.level === 'error')) throw new Error(logged[0].message);
        },
        getLogSnapshot: () => ({ entries }),
    };
    entries.push({ level: 'error', message: 'an old error', timestamp: '2000-01-01T00:00:00.000Z' });
    if (building) void fake.refresh();
    return fake;
}

describe('the build report after an edit', () => {
    test('builds the file and reports only that build\'s problems', async () => {
        const view = session({ logs: [[{ level: 'warning', message: 'slow joint' }]] });
        const report = await buildReport(view, { graceMs: 0 });
        expect(report).toEqual({ ok: true, filePath: '/project/a.py', error: null, entries: [{ level: 'warning', message: 'slow joint' }] });
        expect(view.builds).toBe(1);
    });

    test('a build that fails says why', async () => {
        const report = await buildReport(session({ logs: [[{ level: 'error', message: 'NameError: brace' }]] }), { graceMs: 0 });
        expect(report.ok).toBe(false);
        expect(report.error).toBe('NameError: brace');
    });

    test('waits for a build the watcher started, rather than building twice', async () => {
        const view = session();
        const asked = buildReport(view, { graceMs: 500 });
        setTimeout(() => void view.refresh(), 100);
        const report = await asked;
        expect(view.builds).toBe(1);
        expect(report.ok).toBe(true);
    });
});
