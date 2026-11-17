/**
 * Publishes: a frame frozen at a public link (kigumi-backend's /publishes). Publishing uploads a
 * copy that never changes; opening one downloads it into the library folder and shows it read-only.
 * The links opened are kept in the `shared.publishes` setting, for the explorer's Shared section.
 *
 * Host-neutral: the host gives the backend's URL. Anyone may publish, signed in or not; the backend
 * limits how often, and records no one.
 */

const fs = require('fs');
const path = require('path');

const LINK_BASE = 'https://kumiki.build/p/#';
const ID = /^[A-Za-z0-9]{22}$/;
const SETTING = 'shared.publishes';

const publishLink = (id) => `${LINK_BASE}${id}`;

/** The publish id in a link someone pasted: kumiki.build/p/#<id>, kigumi://publish/<id>, …#publish=<id>, or the id. */
function parsePublishLink(text) {
    const value = String(text || '').trim();
    if (ID.test(value)) return value;
    const match = /(?:\/p\/?#|kigumi:\/\/publish\/|[#?&]publish=)([A-Za-z0-9]{22})(?![A-Za-z0-9])/.exec(value);
    return match ? match[1] : null;
}

/**
 * What a frame uses from its project besides kumiki, which a copy of the frame alone can't run
 * without: modules it imports from the project, and files it names (an STL, say).
 * @returns {{kind: 'import'|'file', name: string}[]}
 */
function findLocalDependencies(filePath, projectRoot) {
    const source = fs.readFileSync(filePath, 'utf8');
    const roots = [...new Set([path.dirname(filePath), projectRoot].filter(Boolean))];
    const found = [];
    const add = (kind, name) => {
        if (!found.some((one) => one.kind === kind && one.name === name)) found.push({ kind, name });
    };
    const isLocalModule = (name) => name !== 'kumiki' && roots.some((root) =>
        fs.existsSync(path.join(root, `${name}.py`)) || fs.existsSync(path.join(root, name, '__init__.py'))
        || (fs.existsSync(path.join(root, name)) && fs.statSync(path.join(root, name)).isDirectory()));

    for (const line of source.split('\n')) {
        const from = /^\s*from\s+(\.*)([\w.]*)\s+import\b/.exec(line);
        if (from) {
            if (from[1]) add('import', `${from[1]}${from[2]}`);
            else if (isLocalModule(from[2].split('.')[0])) add('import', from[2]);
            continue;
        }
        const imported = /^\s*import\s+([\w., ]+)/.exec(line);
        if (imported) {
            for (const part of imported[1].split(',')) {
                const name = part.trim().split(/\s+as\s+/)[0];
                if (name && isLocalModule(name.split('.')[0])) add('import', name);
            }
        }
    }

    const self = path.resolve(filePath);
    for (const match of source.matchAll(/(['"])([^'"\n\\]{1,200})\1/g)) {
        const value = match[2];
        if (!/[./]/.test(value)) continue;
        const candidates = path.isAbsolute(value) ? [value] : roots.map((root) => path.resolve(root, value));
        if (candidates.some((candidate) => candidate !== self && fs.existsSync(candidate) && fs.statSync(candidate).isFile())) {
            add('file', value);
        }
    }
    return found;
}

// Mesh files a mesh timber loads (kumiki/stl.py).
const MESH_FILE = /\.(stl|obj|ply|off|3mf|glb|gltf)$/i;

/**
 * What sharing a frame would leave behind. `refused`: what it can't run without (modules it imports
 * from the project, files it reads), so it isn't shared. `notShared`: what it is shared without,
 * which viewers won't see: mesh files and mesh timbers, its measurements and drawings, and its saved
 * parameter values.
 * @returns {{refused: {kind, name}[], notShared: {kind: 'mesh'|'measurements'|'parameters', name: string}[]}}
 */
function checkSharing(filePath, projectRoot) {
    const refused = [];
    const notShared = [];
    for (const one of findLocalDependencies(filePath, projectRoot)) {
        if (one.kind === 'file' && MESH_FILE.test(one.name)) notShared.push({ kind: 'mesh', name: one.name });
        else refused.push(one);
    }
    const source = fs.readFileSync(filePath, 'utf8');
    if (notShared.length === 0 && /\b(create_stl_timber|STLTimber|MeshTimber)\b/.test(source)) {
        notShared.push({ kind: 'mesh', name: 'mesh timbers' });
    }
    const dir = path.dirname(filePath);
    const stem = path.basename(filePath, '.py');
    // Where runner.py keeps them: measurements and drawings, and parameter values.
    const drawings = path.join('.kigumi', 'drawings', `${stem}.json`);
    if (fs.existsSync(path.join(dir, drawings))) notShared.push({ kind: 'measurements', name: drawings });
    const parameters = `${stem}.parameters.json`;
    if (fs.existsSync(path.join(dir, parameters))) notShared.push({ kind: 'parameters', name: parameters });
    return { refused, notShared };
}

/**
 * @param {object} options
 * @param {string|(() => string)} options.backendUrl
 * @param {string} options.libraryRoot  where opened publishes are kept: <libraryRoot>/publishes/<id>/
 * @param {(key: string, fallback: any) => any} options.getConfig
 * @param {(key: string, value: any) => Promise<void>} options.updateConfig
 * @param {typeof fetch} [options.fetch]
 */
function createPublishes({ backendUrl, libraryRoot, getConfig, updateConfig,
    fetch: fetcher = (...args) => fetch(...args) }) {
    const apiOf = () => String((typeof backendUrl === 'function' ? backendUrl() : backendUrl) || '').replace(/\/$/, '');
    const publishesDir = path.join(libraryRoot, 'publishes');

    async function failure(response) {
        const body = await response.json().catch(() => null);
        const message = body && body.error && (body.error.message || body.error);
        return new Error(typeof message === 'string' ? message : `The server answered ${response.status}.`);
    }

    const list = () => (getConfig(SETTING, []) || []).filter((entry) => entry && ID.test(entry.id));

    async function remember(manifest) {
        const entry = { id: manifest.id, title: manifest.title, entry: manifest.entry,
            kumikiVersion: manifest.kumikiVersion, createdAt: manifest.createdAt };
        await updateConfig(SETTING, [entry, ...list().filter((one) => one.id !== manifest.id)]);
        return entry;
    }

    const dirFor = (id) => path.join(publishesDir, id);

    return {
        link: publishLink,
        list,

        /** Whether this host can publish: it has a backend. */
        get canPublish() {
            return Boolean(apiOf());
        },

        /** The publish a path is part of, or null: its files are read-only. */
        idForPath(filePath) {
            const relative = path.relative(publishesDir, path.resolve(filePath));
            if (!relative || relative.startsWith('..') || path.isAbsolute(relative)) return null;
            const id = relative.split(path.sep)[0];
            return ID.test(id) ? id : null;
        },

        /**
         * Upload a copy of a frame. Refuses one that uses other project files (`error.dependencies`).
         * @returns {Promise<{manifest: object, link: string}>}
         */
        async publish(filePath, { projectRoot, title, kumikiVersion, kigumiVersion }) {
            const dependencies = checkSharing(filePath, projectRoot).refused;
            if (dependencies.length > 0) {
                const error = new Error('This frame uses other files in its project, which can\'t be published yet.');
                error.dependencies = dependencies;
                throw error;
            }
            const name = path.basename(filePath);
            const response = await fetcher(`${apiOf()}/publishes`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ title: title || name.replace(/\.py$/, ''), entry: name, kumikiVersion, kigumiVersion,
                    files: [{ path: name, text: fs.readFileSync(filePath, 'utf8') }] }),
            });
            if (!response.ok) throw await failure(response);
            const manifest = await response.json();
            return { manifest, link: publishLink(manifest.id) };
        },

        /**
         * Download a publish (once: it never changes) and add it to the Shared list.
         * @returns {Promise<{manifest: object, entryPath: string}>}
         */
        async open(id) {
            if (!ID.test(id)) throw new Error('That is not a Kigumi share link.');
            const dir = dirFor(id);
            const manifestPath = path.join(dir, 'publish.json');
            let manifest = null;
            try {
                manifest = JSON.parse(fs.readFileSync(manifestPath, 'utf8'));
            } catch {
                const response = await fetcher(`${apiOf()}/publishes/${id}`);
                if (response.status === 404) throw new Error('Nothing is shared at that link (it may have been taken down).');
                if (!response.ok) throw await failure(response);
                manifest = await response.json();
                fs.mkdirSync(dir, { recursive: true });
                for (const file of manifest.files) {
                    const target = path.resolve(dir, file.path);
                    if (!target.startsWith(dir + path.sep)) throw new Error(`The share holds a file outside it: ${file.path}`);
                    const fileResponse = await fetcher(`${apiOf()}/publishes/${id}/files/${file.sha256}`);
                    if (!fileResponse.ok) throw await failure(fileResponse);
                    fs.mkdirSync(path.dirname(target), { recursive: true });
                    fs.writeFileSync(target, await fileResponse.text(), 'utf8');
                }
                // Last, so a download cut short is fetched again.
                fs.writeFileSync(manifestPath, JSON.stringify(manifest, null, 1), 'utf8');
            }
            await remember(manifest);
            return { manifest, entryPath: path.join(dir, manifest.entry) };
        },

        /** Take a publish off the Shared list and delete its downloaded copy. */
        async remove(id) {
            await updateConfig(SETTING, list().filter((one) => one.id !== id));
            if (ID.test(id)) fs.rmSync(dirFor(id), { recursive: true, force: true });
        },

        /** Where an opened publish's entry frame is, if it is downloaded. */
        entryPath(id) {
            const entry = list().find((one) => one.id === id);
            return entry ? path.join(dirFor(id), entry.entry) : null;
        },
    };
}

module.exports = { createPublishes, parsePublishLink, publishLink, findLocalDependencies, checkSharing, LINK_BASE, SETTING };
