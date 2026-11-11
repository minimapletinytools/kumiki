const { requestWebviewRoundTrip } = require('../webview-request');

/** Return inspection methods for the shell's non-viewer panels. */
function createPanelInspection(connection) {
    // Viewer sessions supply their own entries; the agent panel is excluded.
    function listPanels() {
        return [...connection.panels.values()]
            .filter((panel) => !['viewer', 'agent'].includes(panel.type))
            .map((panel) => ({
                id: `tab:${panel.id}`,
                kind: panel.type,
                title: panel.title,
                filePath: panel.filePath || null,
                active: Boolean(panel.active),
                visible: Boolean(panel.visible),
                central: panel.slot === 'center',
            }));
    }

    async function describePanel(id) {
        const panel = connection.panels.get(String(id).replace(/^tab:/, ''));
        if (!panel) {
            return null;
        }
        if (panel.type === 'editor') {
            return requestWebviewRoundTrip(panel, {
                requestType: 'describePanelRequest',
                resultType: 'describePanelResult',
                requestId: `describe-${Date.now()}-${Math.floor(Math.random() * 1e6)}`,
                timeoutMs: 4000,
                label: 'describePanel',
            });
        }
        return { kind: panel.type, title: panel.title };
    }

    return { listPanels, describePanel };
}

module.exports = { createPanelInspection };
