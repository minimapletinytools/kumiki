/**
 * The web version's projects, kept in this browser (IndexedDB), and the page that lists them when
 * none is open: make one, open one, export one as a .zip, or delete one.
 *
 * The server works on a copy of the open project and sends back every change (`web:files`), which
 * is stored here, so closing the tab loses nothing. Nothing is saved to disk or to the cloud.
 *
 * Kigumi's settings are kept here too (localStorage): sent to the server when the page connects,
 * and stored again each time they change (`web:settings`). So are the agent's saved conversations
 * (IndexedDB, by their path under the server's conversations folder): sent at connect
 * (`web:conversations`), and stored as the server writes or deletes them (`web:conversationFiles`).
 */
(function () {
    'use strict';

    const SETTINGS_KEY = 'kigumi.web.settings';
    // The agent's account session and model list (the worker's web:store).
    const STORE_KEY = 'kigumi.web.store';
    const DB_NAME = 'kigumi-web';
    const STORE = 'projects';
    const CONVERSATIONS = 'conversations';
    const WARNING = 'Your files are saved to browser cache, NOT to disk and NOT to the cloud. '
        + "We aren't doing cloud files yet. Export a project to keep a copy.";

    let projects = []; // { id, name, created, updated, files }, newest first
    let lastRender = null; // the shell's last renderWelcome call, to draw again when projects change
    let send = () => {};

    function openDb() {
        return new Promise((resolve, reject) => {
            const request = indexedDB.open(DB_NAME, 2);
            request.onupgradeneeded = () => {
                const db = request.result;
                if (!db.objectStoreNames.contains(STORE)) db.createObjectStore(STORE, { keyPath: 'id' });
                if (!db.objectStoreNames.contains(CONVERSATIONS)) db.createObjectStore(CONVERSATIONS);
            };
            request.onsuccess = () => resolve(request.result);
            request.onerror = () => reject(request.error);
        });
    }

    async function transact(mode, work, storeName = STORE) {
        const db = await openDb();
        return new Promise((resolve, reject) => {
            const tx = db.transaction(storeName, mode);
            const request = work(tx.objectStore(storeName));
            tx.oncomplete = () => {
                db.close();
                resolve(request ? request.result : undefined);
            };
            tx.onerror = () => {
                db.close();
                reject(tx.error);
            };
        });
    }

    const getProject = (id) => transact('readonly', (store) => store.get(id));
    const putProject = (record) => transact('readwrite', (store) => store.put(record));
    const deleteRecord = (id) => transact('readwrite', (store) => store.delete(id));

    /** Every saved conversation file, { path: content }. */
    async function storedConversations() {
        const db = await openDb();
        return new Promise((resolve, reject) => {
            const files = {};
            const tx = db.transaction(CONVERSATIONS, 'readonly');
            const cursor = tx.objectStore(CONVERSATIONS).openCursor();
            cursor.onsuccess = () => {
                if (!cursor.result) return;
                files[cursor.result.key] = cursor.result.value;
                cursor.result.continue();
            };
            tx.oncomplete = () => {
                db.close();
                resolve(files);
            };
            tx.onerror = () => {
                db.close();
                reject(tx.error);
            };
        });
    }

    /** The server's writes and deletes of conversation files; a deleted path takes what is under it too. */
    function receiveConversationFiles({ changed = {}, deleted = [] }) {
        return transact('readwrite', (store) => {
            for (const [relative, content] of Object.entries(changed)) store.put(content, relative);
            for (const relative of deleted) {
                store.delete(relative);
                store.delete(IDBKeyRange.bound(`${relative}/`, `${relative}/\uffff`));
            }
            return null;
        }, CONVERSATIONS);
    }

    async function reload() {
        const all = await transact('readonly', (store) => store.getAll());
        projects = (all || []).sort((a, b) => b.updated - a.updated);
        // The server's agent tools go by this list (names only; the files stay here).
        command('web:projects', { projects: projects.map(({ id, name }) => ({ id, name })) });
        if (lastRender) renderWelcome(...lastRender);
    }

    function warn(error) {
        console.error('[kigumi web]', error);
        const status = document.getElementById('status-message');
        if (status) {
            status.textContent = `Couldn't use this browser's storage: ${error.message || error}`;
            status.hidden = false;
        }
    }

    /** The server's news of the open project's files: the whole set (`full`), or what changed. */
    async function receiveFiles(message) {
        const record = (await getProject(message.id))
            || { id: message.id, name: message.name, created: Date.now(), files: {} };
        if (message.full) {
            record.files = { ...message.files };
        } else {
            Object.assign(record.files, message.changed || {});
            for (const relative of message.deleted || []) delete record.files[relative];
        }
        record.name = message.name || record.name;
        record.updated = Date.now();
        await putProject(record);
        await reload();
    }

    function command(id, ...args) {
        send({ type: 'shell:command', command: id, args });
    }

    function newProject(name) {
        const trimmed = name.trim();
        if (!trimmed) return;
        command('web:newProject', { id: crypto.randomUUID(), name: trimmed.slice(0, 80) });
    }

    async function openProject(id) {
        const record = await getProject(id);
        if (record) command('web:openProject', { id: record.id, name: record.name, files: record.files });
    }

    async function deleteProject(id, openId) {
        const record = await getProject(id);
        if (!record || !await confirmDelete(record)) return;
        if (id === openId) command('web:closeProject');
        await deleteRecord(id);
        await reload();
    }

    /** Ask before deleting `record` for good: its name typed in, with a last chance to export it. */
    function confirmDelete(record) {
        const el = (tag, className, text) => Object.assign(document.createElement(tag), { className, textContent: text || '' });
        const dialog = el('dialog', 'web-delete');
        const count = Object.keys(record.files || {}).length;
        const input = Object.assign(el('input'), { type: 'text', autocomplete: 'off', spellcheck: false });
        input.setAttribute('aria-label', 'Project name');
        const exportButton = Object.assign(el('button', 'web-delete-export', 'Export .zip first'), { type: 'button' });
        exportButton.addEventListener('click', () => void exportProject(record.id).catch(warn));
        const cancel = Object.assign(el('button', '', 'Cancel'), { type: 'button' });
        const remove = Object.assign(el('button', 'web-delete-confirm', 'Delete forever'), { type: 'button', disabled: true });
        input.addEventListener('input', () => { remove.disabled = input.value.trim() !== record.name.trim(); });
        const actions = el('div', 'web-delete-actions');
        actions.append(exportButton, el('span', 'web-delete-spacer'), cancel, remove);
        const name = el('strong', '', record.name);
        const typeIt = el('label', 'web-delete-type', 'Type ');
        typeIt.append(el('code', '', record.name), ' to confirm:', input);
        dialog.append(el('h2', '', '⚠ Delete this project forever?'), name,
            el('p', '', `This deletes the project and all ${count} file${count === 1 ? '' : 's'} in it. `
                + 'The project lives only in this browser: there is no other copy, no trash and no undo. '
                + 'Once deleted, it is gone for good.'),
            el('p', '', 'Export a .zip first if you might want it back.'), typeIt, actions);
        document.body.appendChild(dialog);
        return new Promise((resolve) => {
            const finish = (answer) => {
                dialog.close();
                dialog.remove();
                resolve(answer);
            };
            cancel.addEventListener('click', () => finish(false));
            remove.addEventListener('click', () => finish(!remove.disabled));
            dialog.addEventListener('cancel', (event) => {
                event.preventDefault();
                finish(false);
            });
            dialog.showModal();
            input.focus();
        });
    }

    function download(name, bytes, type) {
        const url = URL.createObjectURL(new Blob([bytes], { type }));
        const link = document.createElement('a');
        link.href = url;
        link.download = name;
        document.body.appendChild(link);
        link.click();
        link.remove();
        setTimeout(() => URL.revokeObjectURL(url), 60000);
    }

    /** A project's name as a file name. */
    function fileName(name) {
        return name.replace(/[^\w.-]+/g, '_').replace(/^_+|_+$/g, '') || 'project';
    }

    async function exportProject(id) {
        const record = await getProject(id);
        if (!record) return;
        const folder = fileName(record.name);
        const files = Object.fromEntries(Object.entries(record.files).map(([relative, text]) => [`${folder}/${relative}`, text]));
        download(`${folder}.zip`, window.KigumiZip.makeZip(files), 'application/zip');
    }

    /** A file the server made for the user, e.g. an export, as a download. */
    function downloadBase64(name, base64) {
        const binary = atob(base64);
        const bytes = new Uint8Array(binary.length);
        for (let i = 0; i < binary.length; i++) bytes[i] = binary.charCodeAt(i);
        download(name, bytes, 'application/octet-stream');
    }

    /**
     * Draw the projects page in the shell's welcome area when no project is open; return whether it
     * did (with one open, the shell's own welcome shows).
     */
    function renderWelcome(state, tools) {
        lastRender = [state, tools];
        const $ = (id) => document.getElementById(id);
        const welcome = $('welcome');
        let warning = $('web-storage-warning');
        if (!warning) {
            warning = tools.el('p', 'web-storage-warning', WARNING);
            warning.id = 'web-storage-warning';
            welcome.insertBefore(warning, $('welcome-actions'));
        }
        if (state.workspace) {
            warning.hidden = true;
            return false;
        }
        warning.hidden = false;
        const openId = state.web && state.web.projectId;
        $('welcome-lead').textContent = 'Your projects, kept in this browser.';

        const form = tools.el('form', 'web-new-project');
        const input = tools.el('input');
        input.type = 'text';
        input.placeholder = 'New project name';
        input.maxLength = 80;
        input.setAttribute('aria-label', 'New project name');
        const create = tools.el('button', '', 'New Project');
        create.type = 'submit';
        form.append(input, create);
        form.addEventListener('submit', (event) => {
            event.preventDefault();
            newProject(input.value || 'Untitled project');
        });
        $('welcome-actions').replaceChildren(form);

        $('welcome-recent').hidden = projects.length === 0;
        $('welcome-recent').querySelector('h2').textContent = 'Projects';
        $('welcome-recent-list').replaceChildren(...projects.map((record) => {
            const item = tools.el('li', 'web-project');
            item.dataset.projectId = record.id;
            const open = tools.el('button', 'welcome-recent-folder', record.name);
            open.title = `Open ${record.name}`;
            open.addEventListener('click', () => void openProject(record.id).catch(warn));
            const count = Object.keys(record.files || {}).length;
            const when = tools.el('span', 'welcome-recent-path',
                `${count} file${count === 1 ? '' : 's'} · ${new Date(record.updated).toLocaleString()}`);
            const exportButton = tools.el('button', 'web-project-action', 'Export .zip');
            exportButton.addEventListener('click', () => void exportProject(record.id).catch(warn));
            const remove = tools.el('button', 'web-project-action is-danger', 'Delete…');
            remove.addEventListener('click', () => void deleteProject(record.id, openId).catch(warn));
            item.append(open, when, exportButton, remove);
            return item;
        }));
        return true;
    }

    function storedSettings() {
        try {
            const values = JSON.parse(localStorage.getItem(SETTINGS_KEY) || '{}');
            return values && typeof values === 'object' && !Array.isArray(values) ? values : {};
        } catch (_error) {
            return {};
        }
    }

    function storeSettings(values) {
        try {
            localStorage.setItem(SETTINGS_KEY, JSON.stringify(values || {}));
        } catch (error) {
            warn(error);
        }
    }

    function readJson(key) {
        try {
            const values = JSON.parse(localStorage.getItem(key) || '{}');
            return values && typeof values === 'object' && !Array.isArray(values) ? values : {};
        } catch (_error) {
            return {};
        }
    }

    function storeValues(values) {
        try {
            localStorage.setItem(STORE_KEY, JSON.stringify(values || {}));
        } catch (error) {
            warn(error);
        }
    }

    window.kigumiWeb = Object.freeze({
        /** Called once by transport.js with how to send to the server. */
        connect(sendMessage) {
            send = sendMessage;
            // First, before the shell asks for anything: this browser's settings are the ones in force.
            command('web:settings', { values: storedSettings() });
            command('web:store', { values: readJson(STORE_KEY) });
            storedConversations().catch((error) => {
                warn(error);
                return {};
            }).then((files) => command('web:conversations', { files }));
            reload().catch(warn);
            if (navigator.storage && navigator.storage.persist) navigator.storage.persist().catch(() => {});
        },
        receiveFiles: (message) => receiveFiles(message).catch(warn),
        receiveConversationFiles: (message) => receiveConversationFiles(message).catch(warn),
        storeSettings,
        storeValues,
        storedSettings,
        downloadBase64,
        renderWelcome,
        // For tests and the console.
        listProjects: () => projects.map(({ id, name, updated, files }) => ({ id, name, updated, files: Object.keys(files || {}) })),
        exportProject,
        openProject,
    });
})();
