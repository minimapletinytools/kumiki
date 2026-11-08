/**
 * Code editor tabs (webview/editor/): open a file in one, save it, follow changes made on disk, and
 * ask before one with unsaved edits closes. The host gives where the editor page is served from and
 * how to ask the user.
 */

const fs = require('fs');
const path = require('path');

/**
 * @param {object} options
 * @param {import('./shell-connection').ShellConnection} options.connection
 * @param {string} options.editorUrl  where webview/editor/editor.html is served
 * @param {(line: string) => void} options.log
 * @param {(level: string, message: string) => void} options.setStatus
 * @param {(name: string) => Promise<'save'|'discard'|'cancel'>} options.askToSave  for a tab with unsaved edits
 */
function createEditorTabs({ connection, editorUrl, log, setStatus, askToSave }) {
    // By panel id: whether each tab has unsaved edits, and how to ask it for them.
    const tabs = new Map();

    function open(filePath, line = 1) {
        const existing = connection.findPanel((panel) => panel.type === 'editor' && panel.filePath === filePath);
        if (existing) {
            existing.reveal();
            if (line > 1) {
                void existing.postMessage({ type: 'revealLine', line });
            }
            return existing;
        }

        let fileContent = '';
        try {
            fileContent = fs.readFileSync(filePath, 'utf8');
        } catch (error) {
            log(`[editor] Failed to read ${filePath}: ${error.message}`);
            setStatus('error', `Cannot open ${path.basename(filePath)}: ${error.message}`);
            return null;
        }

        const baseName = path.basename(filePath);
        const surface = connection.createPanel('editor', { title: baseName, filePath });
        const pendingContent = new Map();
        let nextRequest = 1;
        const tab = {
            name: baseName,
            isDirty: false,
            // What the editor holds now, unsaved edits included.
            content() {
                const requestId = nextRequest++;
                return new Promise((resolve, reject) => {
                    const timer = setTimeout(() => {
                        pendingContent.delete(requestId);
                        reject(new Error(`${baseName} did not answer`));
                    }, 3000);
                    pendingContent.set(requestId, (content) => {
                        clearTimeout(timer);
                        resolve(content);
                    });
                    void surface.postMessage({ type: 'getContent', requestId });
                });
            },
            save(content) {
                fs.writeFileSync(filePath, content, 'utf8');
                fileContent = content;
                tab.isDirty = false;
                surface.title = baseName;
                void surface.postMessage({ type: 'saved' });
            },
        };
        tabs.set(surface.id, tab);

        surface.onMessage(async (message) => {
            if (!message) return;
            if (message.type === 'editorReady') {
                void surface.postMessage({ type: 'init', filePath, content: fileContent, line });
            } else if (message.type === 'editorDirty') {
                tab.isDirty = !!message.isDirty;
                surface.title = tab.isDirty ? `● ${baseName}` : baseName;
            } else if (message.type === 'editorContent') {
                const resolve = pendingContent.get(message.requestId);
                pendingContent.delete(message.requestId);
                if (resolve) resolve(message.content);
            } else if (message.type === 'editorSave') {
                try {
                    tab.save(message.content);
                } catch (error) {
                    setStatus('error', `Failed to save ${baseName}: ${error.message}`);
                }
            }
        });

        // Changes made elsewhere -- another editor, an agent -- come into the tab. Polled: an editor
        // that saves by renaming the file would leave an fs.watch watching nothing.
        const onDiskChange = () => {
            let content;
            try {
                content = fs.readFileSync(filePath, 'utf8');
            } catch {
                return;
            }
            if (content === fileContent) {
                return; // our own save, or nothing that matters
            }
            fileContent = content;
            if (tab.isDirty) {
                setStatus('warning', `${baseName} changed on disk; the tab keeps your unsaved edits.`);
                return;
            }
            void surface.postMessage({ type: 'externalUpdate', content });
        };
        fs.watchFile(filePath, { interval: 1000 }, onDiskChange);
        surface.onDispose(() => {
            fs.unwatchFile(filePath, onDiskChange);
            tabs.delete(surface.id);
        });

        surface.loadUrl(editorUrl);
        return surface;
    }

    /** Before an editor tab with unsaved edits closes: save, discard, or keep it open. */
    async function confirmClose(panelId) {
        const tab = tabs.get(panelId);
        if (!tab || !tab.isDirty) {
            return true;
        }
        const answer = await askToSave(tab.name);
        if (answer === 'cancel') {
            return false;
        }
        if (answer === 'save') {
            try {
                tab.save(await tab.content());
            } catch (error) {
                setStatus('error', `Failed to save ${tab.name}: ${error.message}`);
                return false;
            }
        }
        return true;
    }

    /** The ids of the tabs with unsaved edits. */
    function dirtyIds() {
        return [...tabs].filter(([, tab]) => tab.isDirty).map(([id]) => id);
    }

    return { tabs, open, confirmClose, dirtyIds };
}

module.exports = { createEditorTabs };
