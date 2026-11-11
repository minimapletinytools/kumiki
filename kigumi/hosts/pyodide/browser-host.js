/**
 * The Host (see ../../host.js) for Kigumi in a browser: the server side of the web host. Files open
 * in the shared code editor tabs; links and the clipboard go to the browser.
 */

const { createShellHostServices } = require('../../app-shell/host-services');

/**
 * @param {object} options
 * @param {import('../../app-shell/shell-connection').ShellConnection} options.connection
 * @param {string|null} options.workspaceFolder  the open project's working folder
 * @param {import('../../app-shell/settings-store').SettingsStore} options.settings
 * @param {(command: string, ...args: any[]) => Promise<any>} options.runCommand
 * @param {(level: string, text: string) => void} options.setStatus
 * @param {(title: string|null) => void} options.setProgress
 * @param {{ open: (filePath: string, line?: number) => any }} options.editors  app-shell/editor-tabs.js
 * @param {(options: {source?: string}) => void} [options.showLog]
 * @param {(line: string) => void} [options.log]
 * @param {boolean} [options.agentPanel]  whether the agent panel can be turned on
 * @param {object} [options.mcp]  Kigumi's MCP server's controls (agent/mcp-service.js)
 * @param {object} [options.projects]  opening a project (host.js `projects`)
 */
function createBrowserHost({ connection, workspaceFolder, settings, runCommand, setStatus, setProgress, editors,
    showLog = null, log = () => {}, agentPanel = false, mcp = null, closeProject = null, projects = null }) {
    return {
        locale: 'en',
        ...createShellHostServices({ connection, settings, workspaceFolder, documents: editors, setProgress, log }),
        showsFileBrowser: true,
        agentPanel,
        // Kigumi's MCP server, which the views' options turn on and copy the setup of.
        ...(mcp ? { mcp } : {}),
        // Project status's Close Project: back to the projects page.
        ...(closeProject ? { closeProject } : {}),
        // Project status's Open Project and recent projects, with none open.
        ...(projects ? { projects } : {}),
        ...(showLog ? { showLog } : {}),
        async showMessage(level, text, ...actions) {
            setStatus(level, text);
            if (actions.length) {
                const picked = await connection.pick(actions.map((label) => ({ label })), text);
                return picked ? picked.label : undefined;
            }
            return undefined;
        },
        async confirm({ message, detail, action }) {
            const picked = await connection.pick([{ label: action }, { label: 'Cancel' }], `${message} ${detail || ''}`.trim());
            return Boolean(picked && picked.label === action);
        },
        async openExternal(url) {
            if (!/^https?:\/\//i.test(url)) throw new Error('Only web links can be opened.');
            connection.send({ type: 'browser:external', url });
        },
        async copyText(text) {
            connection.send({ type: 'browser:clipboard', text });
        },
        // The browser can't show the server's folders; the explorer lists the project's files.
        async revealInFileManager() {
            setStatus('info', 'The browser keeps your project; its files are listed under All Files in the explorer.');
        },
        async openFileAt(filePath, line = 1) {
            editors.open(filePath, line);
        },
        async showFile(filePath) {
            editors.open(filePath, 1);
        },
        async showSourceBesideViewer() {},
        runCommand,
    };
}

module.exports = { createBrowserHost };
