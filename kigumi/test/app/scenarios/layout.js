// The title bar's toggles: the explorer hides and comes back; the agent opens, and hides without
// being closed, so its conversation is kept. The update button shows only while a release is newer.

module.exports = {
    name: 'layout',
    async run({ check, inShell, waitFor, connection, updates, capture }) {
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

        // A drag of the divider ends however the button comes up: elsewhere, with the capture lost,
        // or with the window left. Stuck, the panels took no clicks (.is-resizing) and the app seemed broken.
        const dragEnds = await inShell(`(async () => {
            const splitter = document.getElementById('splitter-right');
            const shell = document.getElementById('shell');
            const box = splitter.getBoundingClientRect();
            const at = { bubbles: true, pointerId: 1, clientX: box.left + 2, clientY: box.top + 50 };
            const out = {};
            for (const [name, finish] of [
                ['capture lost', () => splitter.dispatchEvent(new PointerEvent('lostpointercapture', at))],
                ['moved with no button', () => splitter.dispatchEvent(new PointerEvent('pointermove', { ...at, buttons: 0 }))],
                ['window left', () => window.dispatchEvent(new Event('blur'))],
                ['released', () => splitter.dispatchEvent(new PointerEvent('pointerup', at))],
            ]) {
                splitter.dispatchEvent(new PointerEvent('pointerdown', { ...at, buttons: 1 }));
                const during = shell.classList.contains('is-resizing');
                finish();
                out[name] = during && !shell.classList.contains('is-resizing') && !splitter.classList.contains('is-dragging');
            }
            return out;
        })()`);
        check('a divider drag ends however the button comes up, so the panels take clicks again',
            Object.values(dragEnds).every(Boolean), JSON.stringify(dragEnds));
        const narrowest = await inShell(`(() => {
            document.documentElement.style.setProperty('--right-width', '100px');
            const splitter = document.getElementById('splitter-right');
            const box = splitter.getBoundingClientRect();
            const at = { bubbles: true, pointerId: 1, clientY: box.top + 50 };
            splitter.dispatchEvent(new PointerEvent('pointerdown', { ...at, clientX: box.left, buttons: 1 }));
            splitter.dispatchEvent(new PointerEvent('pointermove', { ...at, clientX: window.innerWidth - 50, buttons: 1 }));
            splitter.dispatchEvent(new PointerEvent('pointerup', at));
            return document.querySelector('#slot-right').getBoundingClientRect().width;
        })()`);
        check("the agent side can't be dragged narrower than the agent panel's least width", narrowest >= 279, String(narrowest));
        await inShell(`document.querySelector('#toggle-right').click()`);
        check('clicking toggle-right again hides the agent and keeps it',
            await slot('right', false) && connection().findPanel((p) => p.type === 'agent') !== undefined);

        const updateButton = (shown) => waitFor(() => inShell(`(() => {
            const button = document.querySelector('#update-available');
            return ${shown ? "button && !button.hidden ? button.title : null" : "!button || button.hidden"};
        })()`), { timeoutMs: 5000 }).catch(() => null);
        check('with no newer release, there is no update button', await updateButton(false));
        updates().setAvailable({ version: '99.0.0', tag: 'kigumi-v99.0.0', page: 'https://example.invalid', assets: [] });
        const title = await updateButton(true);
        await capture('03g-update-button');
        check('a newer release shows the update button, naming its version', title === 'Kigumi 99.0.0 is available', title);
        updates().setAvailable(null);
        check('the update button goes once there is no newer release', await updateButton(false));
    },
};
