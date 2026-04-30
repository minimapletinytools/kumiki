/**
 * RefreshProfiler — Centralises timing, milestone tracking, and stats I/O
 * for Kumiki Viewer refresh cycles.
 */

const fs = require('fs');
const path = require('path');

class RefreshProfiler {
    constructor({ log }) {
        this.log = log;
        this.milestones = [];
        this._milestoneStartNs = null;
    }

    // -------------------------------------------------------------------
    // Milestone tracking (timestamps measured on the extension side)
    // -------------------------------------------------------------------

    resetMilestones() {
        this.milestones = [];
        this._milestoneStartNs = process.hrtime.bigint();
    }

    addMilestone(name) {
        const nowNs = process.hrtime.bigint();
        const elapsedMs = this._milestoneStartNs
            ? Number(nowNs - this._milestoneStartNs) / 1e6
            : 0;
        const previousMs = this.milestones.length > 0
            ? this.milestones[this.milestones.length - 1].elapsed_ms
            : 0;
        const deltaMs = elapsedMs - previousMs;

        this.milestones.push({ name, elapsed_ms: elapsedMs, delta_ms: deltaMs });
        this.log(`[refresh][milestone] ${name} elapsed=${elapsedMs.toFixed(1)}ms delta=${deltaMs.toFixed(1)}ms`);
    }

    getMilestones() {
        return this.milestones.slice();
    }

    // -------------------------------------------------------------------
    // Timing tracker (step-level instrumentation within a refresh)
    // -------------------------------------------------------------------

    createTimingTracker(meta = {}) {
        return {
            startNs: process.hrtime.bigint(),
            lastNs: process.hrtime.bigint(),
            steps: [],
            meta,
        };
    }

    markTiming(tracker, step, extra = null) {
        if (!tracker) {
            return;
        }
        const nowNs = process.hrtime.bigint();
        const elapsedMs = Number(nowNs - tracker.startNs) / 1e6;
        const deltaMs = Number(nowNs - tracker.lastNs) / 1e6;
        tracker.lastNs = nowNs;
        const stampIso = new Date().toISOString();
        const entry = {
            step,
            timestamp: stampIso,
            elapsed_ms: elapsedMs,
            delta_ms: deltaMs,
        };
        if (extra && typeof extra === 'object') {
            entry.extra = extra;
        }
        tracker.steps.push(entry);

        const extraJson = entry.extra ? ` extra=${JSON.stringify(entry.extra)}` : '';
        this.log(`[refresh][timing] ${stampIso} step=${step} elapsed=${elapsedMs.toFixed(1)}ms delta=${deltaMs.toFixed(1)}ms${extraJson}`);
    }

    buildTimingSummary(tracker, reloadResult, geometryData) {
        const reloadRunnerMs = reloadResult && reloadResult.profiling && typeof reloadResult.profiling.reload_s === 'number'
            ? reloadResult.profiling.reload_s * 1000
            : null;
        const geometryRunnerMs = geometryData && geometryData.profiling && typeof geometryData.profiling.geometry_s === 'number'
            ? geometryData.profiling.geometry_s * 1000
            : null;

        const getStep = (name) => tracker.steps.find((s) => s.step === name);
        const durationBetween = (startName, endName) => {
            const start = getStep(startName);
            const end = getStep(endName);
            if (!start || !end) {
                return null;
            }
            return Math.max(0, end.elapsed_ms - start.elapsed_ms);
        };

        const reloadRequestMs = durationBetween('runner.reload_example.start', 'runner.reload_example.end');
        const frameRequestMs = durationBetween('runner.get_frame.start', 'runner.get_frame.end');
        const geometryRequestMs = durationBetween('runner.get_geometry.start', 'runner.get_geometry.end');
        const statsWriteMs = durationBetween('stats.write.start', 'stats.write.end');
        const renderDispatchMs = durationBetween('webview.renderFrameViewer.start', 'webview.renderFrameViewer.end');

        return {
            timeline: tracker.steps,
            breakdown_ms: {
                ensure_runner: durationBetween('ensureRunner.start', 'ensureRunner.end'),
                reload_request: reloadRequestMs,
                reload_runner: reloadRunnerMs,
                reload_overhead: (reloadRequestMs != null && reloadRunnerMs != null)
                    ? Math.max(0, reloadRequestMs - reloadRunnerMs)
                    : null,
                frame_request: frameRequestMs,
                geometry_request: geometryRequestMs,
                geometry_runner: geometryRunnerMs,
                geometry_overhead: (geometryRequestMs != null && geometryRunnerMs != null)
                    ? Math.max(0, geometryRequestMs - geometryRunnerMs)
                    : null,
                stats_write: statsWriteMs,
                render_dispatch: renderDispatchMs,
                refresh_total: durationBetween('refresh.start', 'refresh.end'),
            },
        };
    }

    // -------------------------------------------------------------------
    // Stats file I/O
    // -------------------------------------------------------------------

    writeRefreshStats(statsPayload, outputPath) {
        try {
            fs.mkdirSync(path.dirname(outputPath), { recursive: true });
            fs.writeFileSync(outputPath, `${JSON.stringify(statsPayload, null, 2)}\n`, 'utf8');
            return outputPath;
        } catch (error) {
            this.log(`[refresh] Failed to write stats JSON: ${error.message || error}`);
            return null;
        }
    }
}

module.exports = { RefreshProfiler };
