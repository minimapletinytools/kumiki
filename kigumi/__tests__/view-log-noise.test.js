const { refreshSummary } = require('../frame-view-session');
const { RefreshProfiler } = require('../refresh-profiler');

describe("a build's one line", () => {
    test('says the timbers, the time, where it went and why', () => {
        expect(refreshSummary('frame.py', {
            reason: 'example file change', totalS: 0.5954, timbers: 48,
            reloadResult: { profiling: { reload_s: 0.351 } }, geometryData: { profiling: { geometry_s: 0.2418 } },
        })).toBe('Built frame.py: 48 timbers in 595ms (loading 351ms, meshes 242ms; example file change)');
    });

    test('leaves out what it does not know', () => {
        expect(refreshSummary('frame.py', { reason: 'manual render', totalS: 0.1, timbers: 1,
            reloadResult: { profiling: { reload_s: 0 } } })).toBe('Built frame.py: 1 timber in 100ms (manual render)');
    });
});

describe("a refresh's steps", () => {
    test('are kept for the stats file but not logged', () => {
        const log = jest.fn();
        const profiler = new RefreshProfiler({ log, logSteps: false });
        const tracker = profiler.createTimingTracker();
        profiler.markTiming(tracker, 'refresh.start');
        profiler.addMilestone('raising frame');
        expect(tracker.steps).toHaveLength(1);
        expect(log).not.toHaveBeenCalled();
    });

    test('are logged when asked for', () => {
        const log = jest.fn();
        const profiler = new RefreshProfiler({ log, logSteps: true });
        profiler.markTiming(profiler.createTimingTracker(), 'refresh.start');
        expect(log.mock.calls[0][0]).toMatch(/^\[refresh\]\[timing\] .* step=refresh\.start/);
    });
});
