/**
 * The agent's past conversations, kept on disk per project: each in its own file, with a small
 * index for listing them (a conversation, with the files it read, can be large). Node's; a web host
 * would keep them in the browser.
 *
 * A conversation is { id, title, model, createdAt, updatedAt, history, transcript }: `history` is
 * what the model is sent to carry on, `transcript` what the panel showed, to show it again.
 */

const crypto = require('crypto');
const fs = require('fs');
const path = require('path');

/** Kept per project; the oldest go past this. */
const MAX_CONVERSATIONS = 50;

/** @param {string} baseDir  where every project's conversations go (the app's data folder) */
function createConversationStore(baseDir) {
    const folderFor = (project) => path.join(baseDir,
        crypto.createHash('sha256').update(path.resolve(project)).digest('hex').slice(0, 16));
    const indexFile = (project) => path.join(folderFor(project), 'index.json');
    const fileFor = (project, id) => path.join(folderFor(project), `${id.replace(/[^\w-]/g, '')}.json`);

    function readIndex(project) {
        try {
            return JSON.parse(fs.readFileSync(indexFile(project), 'utf8'));
        } catch (_error) {
            return [];
        }
    }

    function writeIndex(project, entries) {
        fs.mkdirSync(folderFor(project), { recursive: true });
        fs.writeFileSync(indexFile(project), JSON.stringify(entries));
    }

    return {
        /** The project's conversations, newest first: { id, title, updatedAt }. */
        list(project) {
            return readIndex(project).sort((a, b) => b.updatedAt.localeCompare(a.updatedAt));
        },

        load(project, id) {
            try {
                return JSON.parse(fs.readFileSync(fileFor(project, id), 'utf8'));
            } catch (_error) {
                return null;
            }
        },

        save(project, conversation) {
            fs.mkdirSync(folderFor(project), { recursive: true });
            fs.writeFileSync(fileFor(project, conversation.id), JSON.stringify(conversation));
            const entries = readIndex(project).filter((entry) => entry.id !== conversation.id);
            entries.push({ id: conversation.id, title: conversation.title, updatedAt: conversation.updatedAt });
            entries.sort((a, b) => b.updatedAt.localeCompare(a.updatedAt));
            for (const old of entries.splice(MAX_CONVERSATIONS)) {
                fs.rmSync(fileFor(project, old.id), { force: true });
            }
            writeIndex(project, entries);
        },

        remove(project, id) {
            fs.rmSync(fileFor(project, id), { force: true });
            writeIndex(project, readIndex(project).filter((entry) => entry.id !== id));
        },
    };
}

module.exports = { createConversationStore, MAX_CONVERSATIONS };
