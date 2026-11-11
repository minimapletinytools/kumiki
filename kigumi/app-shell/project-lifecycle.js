/** Create a serialized project switch that preserves application panels. */
function createProjectLifecycle({ connection, editors, replace, current }) {
    let pending = Promise.resolve();
    return function switchProject(next, options) {
        const run = async () => {
            if (current && current() === next) return true;
            for (const id of editors.dirtyIds()) {
                const panel = connection.panels.get(id);
                if (panel) panel.reveal();
                if (!(await editors.confirmClose(id))) return false;
            }
            for (const panel of [...connection.panels.values()]) {
                if (!['agent', 'log'].includes(panel.type)) panel.dispose();
            }
            await replace(next, options);
            connection.pushState();
            return true;
        };
        const result = pending.then(run);
        pending = result.catch(() => {});
        return result;
    };
}

module.exports = { createProjectLifecycle };
