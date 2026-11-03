// A frame's parameters: typed in the view's sidebar, held by the view, shown back.

module.exports = {
    name: 'parameters',
    async run({ check, inShell, waitFor, capture, openFrame, viewDoc, showTab, shownPage, PARAMETER_FRAME }) {
        await openFrame(PARAMETER_FRAME);
        await waitFor(() => inShell(`!!${viewDoc}?.querySelector('.vsb-tab[data-tab="parameters"]')`), { timeoutMs: 60000 }).catch(() => false);
        await showTab('parameters');
        const pageAfterClick = await shownPage();
        const parameterRows = await waitFor(() => inShell(`${viewDoc}?.querySelectorAll(".kiwari-row").length || 0`), { timeoutMs: 60000 })
            .catch(() => 0);
        await inShell(`(() => {
            const box = ${viewDoc}.querySelector('input.kiwari-box[type="text"]');
            box.value = '7';
            box.dispatchEvent(new Event('input', { bubbles: true }));
        })()`);
        const parameterEdits = await waitFor(() => inShell(`${viewDoc}.querySelectorAll(".kiwari-row-changed, .kiwari-problem").length`), { timeoutMs: 5000 })
            .catch(() => 0);
        const pageAfterEdit = await shownPage();
        check('the sidebar shows a frame\'s parameters, and an edit there reaches the view',
            pageAfterEdit === 'parameters' && parameterRows > 0 && parameterEdits > 0,
            `${parameterRows} parameters; page ${pageAfterClick} -> ${pageAfterEdit}`);
        await capture('03d-parameters');

        // A ratio: switched on, it has a box per part, labelled by the frame.
        await inShell(`${viewDoc}.getElementById('kiwari-leg_side_splay-on').click()`);
        const parts = await waitFor(() => inShell(`[...${viewDoc}.querySelectorAll('#kiwari-leg_side_splay-rise, #kiwari-leg_side_splay-run')]
            .map((box) => box.closest('.kiwari-axis').querySelector('.kiwari-axis-name').textContent).join('/')`)
            .then((text) => text || null), { timeoutMs: 5000 }).catch(() => '');
        await capture('03e-parameters-ratio');
        await inShell(`${viewDoc}.getElementById('kiwari-leg_side_splay-on').click()`);
        check('a ratio parameter shows a box for each of its parts', parts === 'rise/run', parts);
        await showTab('tree');
    },
};
