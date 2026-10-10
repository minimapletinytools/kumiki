// Monaco Editor controller inside the editor panel iframe.
// Talks to the host/core via window.acquireVsCodeApi() provided by panel-bridge.js.

(function () {
    'use strict';

    const vscode = window.acquireVsCodeApi();
    const container = document.getElementById('editor-container');

    let editor = null;
    let currentFilePath = null;
    let isDirty = false;
    let originalContent = '';

    const isDarkMode = window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches;
    const theme = isDarkMode ? 'vs-dark' : 'vs';

    // Configure Monaco AMD loader to load scripts relative to ../vendor/monaco/vs
    require.config({
        paths: {
            vs: '../vendor/monaco/vs',
        },
    });

    function getLanguage(filePath) {
        if (!filePath) return 'plaintext';
        const lower = filePath.toLowerCase();
        if (lower.endsWith('.py')) return 'python';
        if (lower.endsWith('.json')) return 'json';
        if (lower.endsWith('.js') || lower.endsWith('.mjs')) return 'javascript';
        if (lower.endsWith('.html')) return 'html';
        if (lower.endsWith('.css')) return 'css';
        if (lower.endsWith('.md')) return 'markdown';
        return 'plaintext';
    }

    function initMonaco({ filePath, content, line = 1 }) {
        currentFilePath = filePath;
        originalContent = content;
        isDirty = false;

        require(['vs/editor/editor.main', 'vs/basic-languages/monaco.contribution'], function () {
            const lang = getLanguage(filePath);
            const model = monaco.editor.createModel(content, lang);

            editor = monaco.editor.create(container, {
                model,
                theme,
                automaticLayout: true,
                fontSize: 13,
                fontFamily: 'ui-monospace, "SF Mono", Menlo, Consolas, monospace',
                lineNumbers: 'on',
                minimap: { enabled: true },
                scrollBeyondLastLine: false,
                tabSize: 4,
                insertSpaces: true,
            });

            if (line > 1) {
                editor.revealLineInCenter(line);
                editor.setPosition({ lineNumber: line, column: 1 });
            }
            editor.focus();

            // Track dirty changes
            model.onDidChangeContent(() => {
                const nowDirty = editor.getValue() !== originalContent;
                if (nowDirty !== isDirty) {
                    isDirty = nowDirty;
                    vscode.postMessage({ type: 'editorDirty', isDirty });
                }
            });

            // Save shortcut (Cmd+S / Ctrl+S)
            editor.addCommand(monaco.KeyMod.CtrlCmd | monaco.KeyCode.KeyS, () => {
                const value = editor.getValue();
                vscode.postMessage({ type: 'editorSave', content: value });
            });
        });
    }

    window.addEventListener('message', (event) => {
        const message = event.data;
        if (!message) return;

        switch (message.type) {
            case 'init':
                initMonaco(message);
                break;

            case 'revealLine':
                if (editor && message.line) {
                    editor.revealLineInCenter(message.line);
                    editor.setPosition({ lineNumber: message.line, column: 1 });
                    editor.focus();
                }
                break;

            case 'saved':
                if (editor) {
                    originalContent = editor.getValue();
                    if (isDirty) {
                        isDirty = false;
                        vscode.postMessage({ type: 'editorDirty', isDirty: false });
                    }
                }
                break;

            case 'externalUpdate':
                if (editor && !isDirty && message.content !== undefined) {
                    originalContent = message.content;
                    editor.setValue(message.content);
                }
                break;
        }
    });

    // Notify shell/core that the iframe is ready to receive initialization data
    vscode.postMessage({ type: 'editorReady' });
})();
