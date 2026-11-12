/**
 * The agent's past conversations, kept on disk per project: each in its own file, with a small
 * index for listing them. Long strings (screenshots, file snapshots, files read) go in blob files
 * named by their hash, shared between the project's conversations. A web host mirrors the files
 * to the browser through `onFiles`.
 *
 * A conversation is agent/conversation.js's toJSON, with `model` and `updatedAt`.
 */

const crypto = require('crypto');
const fs = require('fs');
const path = require('path');

/** Kept per project; the oldest go past this. */
const MAX_CONVERSATIONS = 50;
/** Strings this long or longer are kept as blobs. */
const BLOB_AT = 16 * 1024;
const BLOB_REF = /"\$blob":"([0-9a-f]{64})"/g;
const DAY_MS = 24 * 60 * 60 * 1000;

/**
 * @param {string} baseDir  where every project's conversations go (the app's data folder)
 * @param {object} [options]
 * @param {() => number} [options.retentionDays]  conversations not updated for this many days are
 *     deleted; 0 keeps them until MAX_CONVERSATIONS
 * @param {(update: {changed: Object<string, string>, deleted: string[]}) => void} [options.onFiles]
 *     each write and delete, by path relative to `baseDir`; a deleted path may be a folder
 */
function createConversationStore(baseDir, { retentionDays = () => 0, onFiles = null } = {}) {
    const folderFor = (project) => path.join(baseDir,
        crypto.createHash('sha256').update(path.resolve(project)).digest('hex').slice(0, 16));
    // The helpers below take a project's folder.
    const indexFile = (folder) => path.join(folder, 'index.json');
    const fileFor = (folder, id) => path.join(folder, `${id.replace(/[^\w-]/g, '')}.json`);
    const blobFolder = (folder) => path.join(folder, 'blobs');
    const relative = (file) => path.relative(baseDir, file).split(path.sep).join('/');

    /** Write `content` to `file` whole or not at all. */
    function write(file, content) {
        fs.mkdirSync(path.dirname(file), { recursive: true });
        const temporary = `${file}.${process.pid}.tmp`;
        fs.writeFileSync(temporary, content);
        fs.renameSync(temporary, file);
        if (onFiles) onFiles({ changed: { [relative(file)]: content }, deleted: [] });
    }

    function remove(file) {
        fs.rmSync(file, { recursive: true, force: true });
        if (onFiles) onFiles({ changed: {}, deleted: [relative(file)] });
    }

    function readIndex(folder) {
        try {
            return JSON.parse(fs.readFileSync(indexFile(folder), 'utf8'));
        } catch (_error) {
            return [];
        }
    }

    /** `conversation` as JSON, its long strings written as blobs. */
    function withBlobs(folder, conversation) {
        return JSON.stringify(conversation, (_key, value) => {
            if (typeof value !== 'string' || value.length < BLOB_AT) return value;
            const hash = crypto.createHash('sha256').update(value).digest('hex');
            const file = path.join(blobFolder(folder), hash);
            if (!fs.existsSync(file)) write(file, value);
            return { $blob: hash };
        });
    }

    /** JSON with its blobs read back in; a blob gone is a note saying so. */
    function readBlobs(folder, json) {
        return JSON.parse(json, (_key, value) => {
            if (!value || typeof value !== 'object' || typeof value.$blob !== 'string') return value;
            try {
                return fs.readFileSync(path.join(blobFolder(folder), value.$blob.replace(/[^0-9a-f]/g, '')), 'utf8');
            } catch (_error) {
                return '[Kept in a file that is gone.]';
            }
        });
    }

    /** Delete the blobs no kept conversation refers to. */
    function collectBlobs(folder, entries) {
        const used = new Set();
        for (const { id } of entries) {
            try {
                for (const [, hash] of fs.readFileSync(fileFor(folder, id), 'utf8').matchAll(BLOB_REF)) used.add(hash);
            } catch (_error) {
                // A conversation file gone keeps nothing.
            }
        }
        let names = [];
        try {
            names = fs.readdirSync(blobFolder(folder));
        } catch (_error) {
            return;
        }
        for (const name of names) {
            if (!used.has(name)) remove(path.join(blobFolder(folder), name));
        }
    }

    /** Keep only `kept` of the index entries in `folder`, deleting the others' files. */
    function keepOnly(folder, entries, kept) {
        const keptIds = new Set(kept.map((entry) => entry.id));
        const dropped = entries.filter((entry) => !keptIds.has(entry.id));
        for (const old of dropped) remove(fileFor(folder, old.id));
        write(indexFile(folder), JSON.stringify(kept));
        if (dropped.length) collectBlobs(folder, kept);
    }

    /** `entries` newest first, without those past the retention or the count. */
    function retained(entries) {
        const days = retentionDays();
        const cutoff = days > 0 ? new Date(Date.now() - days * DAY_MS).toISOString() : '';
        return entries
            .filter((entry) => entry.updatedAt >= cutoff)
            .sort((a, b) => b.updatedAt.localeCompare(a.updatedAt))
            .slice(0, MAX_CONVERSATIONS);
    }

    /** Every project's folder under `baseDir`. */
    function projectFolders() {
        try {
            return fs.readdirSync(baseDir, { withFileTypes: true }).filter((entry) => entry.isDirectory())
                .map((entry) => path.join(baseDir, entry.name));
        } catch (_error) {
            return [];
        }
    }

    function folderSize(file) {
        try {
            const stat = fs.statSync(file);
            if (!stat.isDirectory()) return stat.size;
            return fs.readdirSync(file).reduce((sum, name) => sum + folderSize(path.join(file, name)), 0);
        } catch (_error) {
            return 0;
        }
    }

    return {
        /** The project's conversations, newest first: { id, title, updatedAt }. */
        list(project) {
            return retained(readIndex(folderFor(project)));
        },

        load(project, id) {
            const folder = folderFor(project);
            try {
                return readBlobs(folder, fs.readFileSync(fileFor(folder, id), 'utf8'));
            } catch (_error) {
                return null;
            }
        },

        save(project, conversation) {
            const folder = folderFor(project);
            write(fileFor(folder, conversation.id), withBlobs(folder, conversation));
            const entries = readIndex(folder).filter((entry) => entry.id !== conversation.id);
            entries.push({ id: conversation.id, title: conversation.title, updatedAt: conversation.updatedAt });
            keepOnly(folder, entries, retained(entries));
        },

        remove(project, id) {
            const folder = folderFor(project);
            const entries = readIndex(folder);
            remove(fileFor(folder, id));
            keepOnly(folder, entries, entries.filter((entry) => entry.id !== id));
        },

        /** Delete every project's conversations past the retention. */
        prune() {
            for (const folder of projectFolders()) {
                const entries = readIndex(folder);
                const kept = retained(entries);
                if (kept.length < entries.length) keepOnly(folder, entries, kept);
            }
        },

        /** Delete every project's conversations. */
        clear() {
            for (const folder of projectFolders()) remove(folder);
        },

        /** The bytes every project's conversations take. */
        usage() {
            return folderSize(baseDir);
        },
    };
}

module.exports = { createConversationStore, MAX_CONVERSATIONS, BLOB_AT };
