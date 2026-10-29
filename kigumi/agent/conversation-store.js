/**
 * The agent's past conversations, kept on disk per project: each in its own file, with a small
 * index for listing them. Long strings (screenshots, file snapshots, files read) go in blob files
 * named by their hash, shared between the project's conversations. Node's; a web host would keep
 * them in the browser.
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

/** Write `content` to `file` whole or not at all. */
function writeAtomic(file, content) {
    const temporary = `${file}.${process.pid}.tmp`;
    fs.writeFileSync(temporary, content);
    fs.renameSync(temporary, file);
}

/** @param {string} baseDir  where every project's conversations go (the app's data folder) */
function createConversationStore(baseDir) {
    const folderFor = (project) => path.join(baseDir,
        crypto.createHash('sha256').update(path.resolve(project)).digest('hex').slice(0, 16));
    const indexFile = (project) => path.join(folderFor(project), 'index.json');
    const fileFor = (project, id) => path.join(folderFor(project), `${id.replace(/[^\w-]/g, '')}.json`);
    const blobFolder = (project) => path.join(folderFor(project), 'blobs');

    function readIndex(project) {
        try {
            return JSON.parse(fs.readFileSync(indexFile(project), 'utf8'));
        } catch (_error) {
            return [];
        }
    }

    function writeIndex(project, entries) {
        fs.mkdirSync(folderFor(project), { recursive: true });
        writeAtomic(indexFile(project), JSON.stringify(entries));
    }

    /** `conversation` as JSON, its long strings written as blobs. */
    function withBlobs(project, conversation) {
        const folder = blobFolder(project);
        fs.mkdirSync(folder, { recursive: true });
        return JSON.stringify(conversation, (_key, value) => {
            if (typeof value !== 'string' || value.length < BLOB_AT) return value;
            const hash = crypto.createHash('sha256').update(value).digest('hex');
            const file = path.join(folder, hash);
            if (!fs.existsSync(file)) writeAtomic(file, value);
            return { $blob: hash };
        });
    }

    /** JSON with its blobs read back in; a blob gone is a note saying so. */
    function readBlobs(project, json) {
        return JSON.parse(json, (_key, value) => {
            if (!value || typeof value !== 'object' || typeof value.$blob !== 'string') return value;
            try {
                return fs.readFileSync(path.join(blobFolder(project), value.$blob.replace(/[^0-9a-f]/g, '')), 'utf8');
            } catch (_error) {
                return '[Kept in a file that is gone.]';
            }
        });
    }

    /** Delete the blobs no kept conversation refers to. */
    function collectBlobs(project, entries) {
        const used = new Set();
        for (const { id } of entries) {
            try {
                for (const [, hash] of fs.readFileSync(fileFor(project, id), 'utf8').matchAll(BLOB_REF)) used.add(hash);
            } catch (_error) {
                // A conversation file gone keeps nothing.
            }
        }
        let names = [];
        try {
            names = fs.readdirSync(blobFolder(project));
        } catch (_error) {
            return;
        }
        for (const name of names) {
            if (!used.has(name)) fs.rmSync(path.join(blobFolder(project), name), { force: true });
        }
    }

    return {
        /** The project's conversations, newest first: { id, title, updatedAt }. */
        list(project) {
            return readIndex(project).sort((a, b) => b.updatedAt.localeCompare(a.updatedAt));
        },

        load(project, id) {
            try {
                return readBlobs(project, fs.readFileSync(fileFor(project, id), 'utf8'));
            } catch (_error) {
                return null;
            }
        },

        save(project, conversation) {
            fs.mkdirSync(folderFor(project), { recursive: true });
            writeAtomic(fileFor(project, conversation.id), withBlobs(project, conversation));
            const entries = readIndex(project).filter((entry) => entry.id !== conversation.id);
            entries.push({ id: conversation.id, title: conversation.title, updatedAt: conversation.updatedAt });
            entries.sort((a, b) => b.updatedAt.localeCompare(a.updatedAt));
            const dropped = entries.splice(MAX_CONVERSATIONS);
            for (const old of dropped) fs.rmSync(fileFor(project, old.id), { force: true });
            writeIndex(project, entries);
            if (dropped.length) collectBlobs(project, entries);
        },

        remove(project, id) {
            fs.rmSync(fileFor(project, id), { force: true });
            const entries = readIndex(project).filter((entry) => entry.id !== id);
            writeIndex(project, entries);
            collectBlobs(project, entries);
        },
    };
}

module.exports = { createConversationStore, MAX_CONVERSATIONS, BLOB_AT };
