// The view's sidebar: it opens on its tree; its members tab lists the view's members and a click on
// one selects it; an option changes the view; collapsing it gives the 3D view its width.

module.exports = {
    name: 'sidebar',
    async run({ check, inShell, waitFor, sleep, capture, panels, openFrame, viewDoc, showTab, shownPage, FRAME }) {
        await openFrame(FRAME);
        check('the view\'s sidebar opens on its tree', await shownPage() === 'tree', await shownPage());
        await showTab('members');
        const memberRows = await waitFor(() => inShell(`${viewDoc}?.querySelectorAll("#timber-rows tr").length || 0`), { timeoutMs: 15000 })
            .catch(() => 0);
        check('the sidebar\'s members tab lists the members of the view', await shownPage() === 'members' && memberRows > 0,
            `${memberRows} members`);
        await inShell(`${viewDoc}.querySelector("#timber-rows tr").click()`);
        const selectedRows = await waitFor(() => inShell(`${viewDoc}?.querySelectorAll("#timber-rows tr.is-selected").length || 0`), { timeoutMs: 5000 })
            .catch(() => 0);
        const viewSelection = (await panels().describe(`viewer:${FRAME}`)).selection;
        check('a click on a member row selects it in the view, and shows it',
            selectedRows === 1 && viewSelection && viewSelection.members.length === 1,
            `${selectedRows} row, ${viewSelection && viewSelection.members.length} selected in the view`);
        await capture('03b-members');

        const lengthOfFirstRow = () => inShell(`${viewDoc}.querySelector("#timber-rows tr").children[4].textContent`);
        const setUnits = (units) => inShell(`(() => {
            const select = ${viewDoc}.getElementById('units-select');
            select.value = ${JSON.stringify(units)};
            select.dispatchEvent(new Event('change', { bubbles: true }));
        })()`);
        const metricLength = await lengthOfFirstRow();
        await showTab('options');
        await setUnits('imperial');
        try {
            const imperialLength = await waitFor(async () => {
                const length = await lengthOfFirstRow();
                return length !== metricLength ? length : null;
            }, { timeoutMs: 5000 }).catch(() => null);
            check('an option changed in the sidebar changes the view', imperialLength !== null, `${metricLength} -> ${imperialLength}`);
            await capture('03c-options');
        } finally {
            await setUnits('metric');
            await waitFor(async () => (await lengthOfFirstRow()) === metricLength, { timeoutMs: 5000 }).catch(() => null);
        }

        const viewportWide = () => inShell(`${viewDoc}.getElementById('viewport').getBoundingClientRect().width`);
        const widthOpen = await viewportWide();
        await inShell(`${viewDoc}.querySelector('.vsb-collapse').click()`);
        const widthCollapsed = await waitFor(async () => {
            const width = await viewportWide();
            return width > widthOpen ? width : null;
        }, { timeoutMs: 5000 }).catch(() => null);
        await sleep(300);
        await capture('03e-sidebar-collapsed');
        await inShell(`${viewDoc}.querySelector('.vsb-expand').click()`);
        check('collapsing the sidebar gives the 3D view its width', widthCollapsed !== null, `${widthOpen} -> ${widthCollapsed}`);
        await showTab('tree');
    },
};
