/**
 * The library: a project of Kigumi's own, in its storage folder, with the newest kumiki this Kigumi
 * takes. With no project open, kumiki's examples and patterns and shared frames run in it.
 */

const fs = require('fs');
const path = require('path');
const { ensureKigumiYaml, KUMIKI_YAML_RELATIVE_PATH } = require('./project-root');
const { getVenvPython } = require('./python-env');
const { isPythonAvailable, managedEnvironment } = require('./python-runtime');

function createLibrary({ root }) {
    let preparing = null;
    return {
        root,

        /** Whether it is set up. The browser's Python already has kumiki, so there it needs only the folder. */
        ready() {
            if (!fs.existsSync(path.join(root, KUMIKI_YAML_RELATIVE_PATH))) return false;
            return managedEnvironment || isPythonAvailable(getVenvPython(root));
        },

        get preparing() {
            return Boolean(preparing);
        },

        /** Set it up, or bring its kumiki up to date: a venv with kumiki, as a project gets. */
        prepare() {
            if (!preparing) {
                preparing = (async () => {
                    fs.mkdirSync(root, { recursive: true });
                    ensureKigumiYaml(root);
                    if (!managedEnvironment) {
                        const { updateWorkspaceKumiki } = require('./project-initializer');
                        await updateWorkspaceKumiki(root, null);
                    }
                })().finally(() => { preparing = null; });
            }
            return preparing;
        },
    };
}

module.exports = { createLibrary };
