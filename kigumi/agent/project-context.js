const { createProjectFiles } = require('./project-files');
const { findKumikiSource, kumikiExamples, projectPython } = require('./kumiki-source');
const { pythonKumikiApi } = require('./kumiki-api');
const { loadSystemPrompt } = require('./system-prompt');
const { viewHost } = require('./agent');

/** Return agent hosts bound to the currently open project. */
function createProjectContext({ root, panels, run, projects }) {
    let source = null;
    let sourceFor;
    function knownSource() {
        const asked = root();
        if (sourceFor !== asked) {
            sourceFor = asked;
            source = null;
            void findKumikiSource(asked).then((folder) => {
                if (sourceFor === asked) source = folder;
            });
        }
        return source;
    }
    const livePanels = new Proxy({}, {
        get(_target, key) {
            if (key === 'then') return undefined;
            const current = panels();
            if (!current) return typeof key === 'string'
                ? () => { throw new Error('No project is open.'); } : undefined;
            const value = current[key];
            return typeof value === 'function' ? value.bind(current) : value;
        },
    });
    return function agentHost() {
        knownSource();
        return viewHost({
            panels: livePanels, run,
            files: createProjectFiles({ root, readOnly: () => [source, kumikiExamples(source)].filter(Boolean) }),
            workspaceFolders: () => root() ? [root()] : [],
            kumikiApi: pythonKumikiApi({ python: () => projectPython(root()), cwd: root }),
            kumikiSource: knownSource,
            kumikiExamples: () => kumikiExamples(knownSource()),
            systemPrompt: loadSystemPrompt(),
            projects: projects(),
        });
    };
}

module.exports = { createProjectContext };
