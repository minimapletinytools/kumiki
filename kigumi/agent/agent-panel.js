/**
 * The agent's panel in a Kigumi window: shown on the right, hidden without losing its conversation,
 * and closed when `agent.enabled` is turned off (it is off by default). The host gives where the
 * page is served and how the account is kept.
 */

const { AgentSession } = require('./agent-session');
const { createConversationStore } = require('./conversation-store');
const { loadCatalog, resolveLocale } = require('../i18n');

/**
 * @param {object} options
 * @param {import('../app-shell/shell-connection').ShellConnection} options.connection
 * @param {string} options.pageUrl  where webview/agent/agent.html is served
 * @param {{ get: (key: string, fallback: any) => any, set: (key: string, value: any) => void }} options.settings
 * @param {() => object} options.makeHost  the agent's host (agent/agent.js), made when the panel opens
 * @param {() => { account: object|null, models: object }} options.prepare  the account and model list, made once
 * @param {string} options.conversationsDir
 * @param {string} options.locale
 * @param {(line: string) => void} options.log
 */
function createAgentPanel({ connection, pageUrl, settings, makeHost, prepare, conversationsDir, locale, log }) {
    let session = null;
    const enabled = () => settings.get('agent.enabled', false) === true;

    function refreshModels(models) {
        if (models && typeof models.refresh === 'function') {
            models.refresh().catch((error) => log(`[agent] [warn] couldn't fetch the model list: ${error.message}`));
        }
    }

    /** Show the agent, or hide it if shown. Hidden, it keeps its conversation. */
    function toggle() {
        if (!enabled()) return;
        const { account, models } = prepare();
        if (connection.findPanel((panel) => panel.type === 'agent')) {
            connection.setSideShown('right', !connection.layout.right);
            return;
        }
        const surface = connection.createPanel('agent', { title: 'Agent' });
        session = new AgentSession({
            host: makeHost(),
            post: (message) => void surface.postMessage(message),
            setting: (key, fallback) => settings.get(key, fallback),
            setSetting: (key, value) => settings.set(key, value),
            account,
            models,
            conversations: createConversationStore(conversationsDir),
            strings: loadCatalog(resolveLocale(locale)),
            log,
        });
        surface.onMessage((message) => session && session.handle(message));
        surface.onDispose(() => {
            if (session) session.stop();
            session = null;
        });
        surface.loadUrl(pageUrl);
        connection.setSideShown('right', true);
        refreshModels(models);
    }

    /** Close the panel once `agent.enabled` is off. */
    function closeIfDisabled() {
        if (enabled()) return;
        const panel = connection.findPanel((one) => one.type === 'agent');
        if (panel) panel.dispose();
    }

    return {
        enabled,
        toggle,
        closeIfDisabled,
        get session() { return session; },
        stop() {
            if (session) session.stop();
        },
    };
}

module.exports = { createAgentPanel };
