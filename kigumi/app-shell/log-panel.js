/** Return an opener for the shared log panel, optionally filtered by source file. */
function createLogPanel({ connection, channel, pageUrl, filePath = null, openFile, openLocation, onShow = () => {} }) {
    return function openLog({ source } = {}) {
        onShow();
        const existing = connection.findPanel((panel) => panel.type === 'log');
        if (existing) {
            existing.reveal();
            if (typeof source === 'string') void existing.postMessage({ type: 'logShowSource', source });
            return;
        }
        const panel = connection.createPanel('log', { title: 'Log' });
        const subscription = channel.onEntry((entry) => panel.postMessage({ type: 'logEntry', entry }));
        panel.onMessage((message) => {
            if (!message) return;
            if (message.type === 'logReady') {
                void panel.postMessage({ type: 'logEntries', entries: channel.entries, filePath,
                    ...(typeof source === 'string' ? { source } : {}) });
            } else if (message.type === 'openLogFile' && openFile) {
                void openFile();
            } else if (message.type === 'openLogLocation' && typeof message.filePath === 'string' && openLocation) {
                openLocation(message.filePath, Number(message.lineNumber) || 1);
            }
        });
        panel.onDispose(() => subscription.dispose());
        panel.loadUrl(pageUrl);
    };
}

module.exports = { createLogPanel };
