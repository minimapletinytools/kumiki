// The quick pick: Browse Patterns filters by name, and the pattern picked opens in a tab of its own
// beside the view already open.

module.exports = {
    name: 'quick-pick',
    async run({ check, inShell, waitFor, sleep, capture, runAppCommand, connection, openFrame, FRAME }) {
        await openFrame(FRAME);
        const picking = runAppCommand('kigumi.browsePatterns');
        await waitFor(() => inShell('!document.getElementById("quickpick").hidden && document.querySelectorAll("#quickpick .item").length'), { timeoutMs: 30000 });
        await capture('04-quickpick');
        const labels = await inShell('Array.from(document.querySelectorAll("#quickpick .item-label")).map((e) => e.textContent)');
        const wanted = labels[Math.min(1, labels.length - 1)];
        await inShell(`(() => {
            const filter = document.getElementById('quickpick-filter');
            filter.value = ${JSON.stringify(wanted)};
            filter.dispatchEvent(new Event('input'));
        })()`);
        const filtered = await inShell('Array.from(document.querySelectorAll("#quickpick .item-label")).map((e) => e.textContent)');
        check('the quick pick filters by name', filtered.length > 0 && filtered.every((label) => label.includes(wanted)), `${wanted}: ${filtered.join(', ')}`);
        await inShell(`document.getElementById('quickpick-filter').dispatchEvent(new KeyboardEvent('keydown', { key: ${JSON.stringify(filtered.length > 0 ? 'Enter' : 'Escape')} }))`);
        await picking;
        const tabs = connection().tabs.tabs.map((tab) => connection().panels.get(tab.id).title);
        check('the picked pattern opens in a second tab', tabs.length === 2 && tabs[1].includes(wanted), tabs.join(' | '));
        await sleep(1000);
        await capture('05-pattern');
    },
};
