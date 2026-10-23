// A crashed window reloads its panels and draws its views again.

module.exports = {
    name: 'crash-recovery',
    async run({ check, inShell, waitFor, runAppCommand, window, openFrame, FRAME }) {
        await openFrame(FRAME);
        const refreshCount = async () => (await runAppCommand('kigumi.automationListSessions')).sessions
            .reduce((sum, one) => sum + (one.refreshSequence || 0), 0);
        const refreshesBefore = await refreshCount();
        window().webContents.forcefullyCrashRenderer();
        await waitFor(async () => (await refreshCount()) > refreshesBefore, { timeoutMs: 30000 });
        const rowsAfter = await waitFor(() => inShell(
            'document.querySelector("#slot-left iframe")?.contentDocument?.querySelectorAll(".ks-row").length || 0'));
        check('a crashed window reloads its panels and redraws the viewers', !window().webContents.isCrashed() && rowsAfter > 0,
            `refreshes ${refreshesBefore} -> ${await refreshCount()}, explorer rows ${rowsAfter}`);
    },
};
