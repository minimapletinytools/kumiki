/**
 * Build a view's file as it is now and report that build's warnings and errors, for an agent that
 * has just edited it (kigumi.automationBuildReport). A build already running, such as the file
 * watcher's after the save, is let finish first, and counts if it started after this was asked.
 */

const TIMEOUT_MS = 120000;
/** How long the file watcher may take to start a build after a save. */
const WATCHER_GRACE_MS = 1500;
const POLL_MS = 100;

const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

async function until(done, limitMs) {
    for (let waited = 0; !done() && waited < limitMs; waited += POLL_MS) {
        await sleep(POLL_MS);
    }
}

/**
 * @param {object} session  a view session: refresh(reason), refreshSequence, isRefreshing,
 *     pendingRefreshReason, getLogSnapshot({minLevel}), filePath
 * @param {{reason?: string, graceMs?: number}} [options]
 */
async function buildReport(session, { reason = 'agent edit', graceMs = WATCHER_GRACE_MS } = {}) {
    const since = new Date().toISOString();
    const startedWith = session.refreshSequence;
    const idle = () => until(() => !session.isRefreshing && !session.pendingRefreshReason, TIMEOUT_MS);
    // Rather than build twice, give the watcher its moment to start the build.
    await until(() => session.refreshSequence !== startedWith || session.isRefreshing, graceMs);
    await idle();
    let failure = null;
    if (session.refreshSequence === startedWith) {
        await session.refresh(reason).catch((error) => { failure = error; });
        await idle();
    }
    const fresh = session.getLogSnapshot({ minLevel: 'warn' }).entries
        .filter((entry) => typeof entry.timestamp === 'string' && entry.timestamp >= since);
    return {
        ok: !failure && !fresh.some((entry) => entry.level === 'error'),
        filePath: session.filePath,
        error: failure ? String(failure.message || failure) : null,
        entries: fresh.slice(-20).map((entry) => ({ level: entry.level, message: entry.message })),
    };
}

module.exports = { buildReport };
