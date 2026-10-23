// The title bar's toggles: the explorer hides and comes back; the agent opens, and hides without
// being closed, so its conversation is kept.

module.exports = {
    name: 'layout',
    async run({ check, inShell, waitFor, connection }) {
        const slot = (side, shown) => waitFor(() => inShell(`(() => {
            const slot = document.querySelector('#slot-${side}');
            return ${shown ? "slot && !slot.hidden" : "!slot || slot.hidden"};
        })()`), { timeoutMs: 10000 }).then(() => true, () => false);

        await inShell(`document.querySelector('#toggle-left').click()`);
        check('clicking toggle-left hides the explorer sidebar', await slot('left', false));
        await inShell(`document.querySelector('#toggle-left').click()`);
        check('clicking toggle-left restores the explorer sidebar', await slot('left', true));

        await inShell(`document.querySelector('#toggle-right').click()`);
        const agentFrame = await waitFor(() => inShell(`!!document.querySelector('#slot-right:not([hidden]) iframe')`), { timeoutMs: 10000 })
            .then(() => true, () => false);
        check('clicking toggle-right opens the agent sidebar', agentFrame && connection().findPanel((p) => p.type === 'agent') !== undefined);
        await inShell(`document.querySelector('#toggle-right').click()`);
        check('clicking toggle-right again hides the agent and keeps it',
            await slot('right', false) && connection().findPanel((p) => p.type === 'agent') !== undefined);
    },
};
