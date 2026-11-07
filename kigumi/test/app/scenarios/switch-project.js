// Switching projects happens in place: the old project's tabs close, the explorer starts over on the
// new folder, and switching back, a frame builds in a view again. The agent's tools do the same.

const fs = require('fs');
const os = require('os');
const path = require('path');

module.exports = {
    name: 'switch-project',
    async run({ check, waitFor, connection, switchProject, agentProjects, runAppCommand, openFrame, settings, REPO }) {
        const explorerRoot = async () => {
            const snapshot = await runAppCommand('kigumi.testGetSidebarSnapshot', { forceRefresh: false }).catch(() => null);
            return snapshot && snapshot.state ? snapshot.state.workspaceRoot : null;
        };
        const centerTabs = () => connection().tabs.tabs.filter((tab) => tab.kind !== 'explorer' && tab.kind !== 'agent');

        check('a frame opens before switching', await openFrame());
        const other = fs.mkdtempSync(path.join(os.tmpdir(), 'kigumi-switch-'));
        try {
            check('switching reports that it switched', await switchProject(other) === true);
            check('the old project\'s tabs are closed', centerTabs().length === 0, JSON.stringify(centerTabs()));
            check('the explorer starts over on the new folder',
                await waitFor(async () => await explorerRoot() === other, { timeoutMs: 15000 }).then(() => true, () => false));
            check('the new folder is the remembered one, and the most recent',
                settings.get('app.workspaceFolder') === other && settings.get('app.recentFolders')[0] === other);

            await agentProjects().open(REPO);
            check('the agent\'s open_project switches back in place',
                await waitFor(async () => await explorerRoot() === REPO, { timeoutMs: 15000 }).then(() => true, () => false));
            check('a frame builds in a view after switching back', await openFrame());

            await agentProjects().close();
            check('close_project leaves no project open', settings.get('app.workspaceFolder') === null);
            await switchProject(REPO);
            await waitFor(async () => await explorerRoot() === REPO && !(await runAppCommand('kigumi.testGetSidebarSnapshot',
                { forceRefresh: false })).state.isScanning, { timeoutMs: 60000 }).catch(() => null);
        } finally {
            fs.rmSync(other, { recursive: true, force: true });
        }
    },
};
