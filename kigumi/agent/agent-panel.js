/**
 * The agent's panel in a Kigumi window: shown on the right, hidden without losing its conversation.
 * It always opens, for its MCP and agent settings; the built-in agent's chat shows only while
 * `agent.enabled` is on (it is off by default). The host gives where the page is served, how the
 * account is kept and its MCP server's controls.
 */

const { AgentSession, CONVERSATION_RETENTION } = require('./agent-session');
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
 * @param {(update: object) => void} [options.onConversationFiles]  conversation-store.js's onFiles
 * @param {object|null} [options.mcp]  the host's MCP controls (host.js `mcp`): state, onChange, copySetup
 * @param {string} options.locale
 * @param {(line: string) => void} options.log
 */
function createAgentPanel({ connection, pageUrl, settings, makeHost, prepare, conversationsDir, onConversationFiles = null,
    mcp = null, locale, log }) {
    let session = null;
    const enabled = () => settings.get('agent.enabled', false) === true;
    const conversations = createConversationStore(conversationsDir, {
        retentionDays: () => {
            const days = settings.get('agent.conversationRetentionDays', CONVERSATION_RETENTION.fallback);
            return CONVERSATION_RETENTION.valid(days) ? days : CONVERSATION_RETENTION.fallback;
        },
        onFiles: onConversationFiles,
    });

    function refreshModels(models) {
        if (models && typeof models.refresh === 'function') {
            models.refresh().catch((error) => log(`[agent] [warn] couldn't fetch the model list: ${error.message}`));
        }
    }

    /** Show the panel, or hide it if shown. Hidden, it keeps its conversation. */
    function toggle() {
        const { account, models } = prepare();
        if (connection.findPanel((panel) => panel.type === 'agent')) {
            connection.setSideShown('right', !connection.layout.right);
            return;
        }
        try {
            conversations.prune();
        } catch (error) {
            log(`[agent] could not delete old conversations: ${error.message}`);
        }
        const surface = connection.createPanel('agent', { title: 'Agent' });
        session = new AgentSession({
            host: makeHost(),
            post: (message) => void surface.postMessage(message),
            setting: (key, fallback) => settings.get(key, fallback),
            setSetting: (key, value) => settings.set(key, value),
            account,
            models,
            conversations,
            mcp,
            strings: loadCatalog(resolveLocale(locale)),
            log,
        });
        surface.onMessage((message) => session && session.handle(message));
        surface.onDispose(() => {
            if (session) session.dispose();
            session = null;
        });
        surface.loadUrl(pageUrl);
        connection.setSideShown('right', true);
        refreshModels(models);
    }

    return {
        enabled,
        toggle,
        /** Show the panel, opening it if it isn't. */
        show() {
            if (connection.findPanel((panel) => panel.type === 'agent')) connection.setSideShown('right', true);
            else toggle();
        },
        /** Show the settings again after one changed elsewhere (agent.enabled from the menu). */
        refresh() {
            if (session) session.postState();
        },
        get session() { return session; },
        stop() {
            if (session) session.stop();
        },
    };
}

module.exports = { createAgentPanel };
