// The agent panel: it lists the models, offers signing in when there is no key, and a model picked
// there is kept; with a key set, it says it is using it. Its settings set the longest step. And the
// build an agent's edit runs. Turned off, the panel shows only its settings; turned on from there, the chat is back.

module.exports = {
    name: 'agent',
    async run({ check, inShell, waitFor, capture, settings, openFrame, runAppCommand, connection, onShellCommand, FRAME }) {
        const agentDoc = 'document.querySelector("#slot-right iframe").contentDocument';
        const read = (script) => inShell(`(() => { const doc = ${agentDoc}; return ${script}; })()`);

        await inShell(`document.querySelector('#toggle-right').click()`);
        const models = await waitFor(() => read(`doc && doc.querySelectorAll('#model-select option').length`)
            .catch(() => 0), { timeoutMs: 10000 }).catch(() => 0);
        const note = await read(`doc.getElementById('route-note').textContent`);
        check('the agent lists the models and, with no key, offers signing in',
            models >= 4 && note.includes('Sign in') && note.includes('GitHub'), `${models} models; ${note}`);
        const askToSignIn = await read(`[...doc.querySelectorAll('.welcome-sign-in-needed')].some((one) => one.offsetParent !== null)
            && [...doc.querySelectorAll('.suggestions')].every((one) => one.offsetParent === null)`);
        check('with no key, the chat area says to sign in, in place of the suggestions', askToSignIn === true);

        settings.set('agent.openrouterApiKey', 'sk-or-test');
        await read(`(() => { const select = doc.getElementById('model-select'); select.value = 'claude-haiku-4.5';
            select.dispatchEvent(new Event('change')); })()`);
        const using = await waitFor(() => read(`doc.getElementById('route-note').textContent`)
            .then((text) => (text.includes('OpenRouter key') ? text : null)), { timeoutMs: 5000 }).catch(() => '');
        check('a model picked in the panel is kept, and the panel says which key it uses',
            settings.get('agent.model') === 'claude-haiku-4.5' && Boolean(using), `${settings.get('agent.model')}; ${using}`);

        await read(`doc.getElementById('settings-toggle').click()`);
        const shown = await read(`doc.getElementById('setting-output-limit').value`);
        await read(`(() => { const select = doc.getElementById('setting-output-limit'); select.value = '32000';
            select.dispatchEvent(new Event('change')); })()`);
        const limit = await waitFor(() => settings.get('agent.maxOutputTokens') === 32000, { timeoutMs: 5000 }).catch(() => false);
        await capture('agent-settings');
        await read(`doc.getElementById('settings-toggle').click()`);
        settings.set('agent.maxOutputTokens', 16000);
        check('the settings menu sets the longest step', shown === '16000' && limit, `shown ${shown}, now ${settings.get('agent.maxOutputTokens')}`);

        // The agent's to-do list: its × hides it, and the agent's next change to it shows it again.
        const agentSurface = connection().findPanel((panel) => panel.type === 'agent');
        const todos = (items) => agentSurface.postMessage({ type: 'agent:todos', items });
        todos([{ text: 'Write the sills', done: true }, { text: 'Join the posts' }]);
        const listed = await waitFor(() => read(`!doc.getElementById('todos').hidden && doc.querySelectorAll('#todos li').length === 2`),
            { timeoutMs: 5000 }).catch(() => false);
        await capture('agent-todos');
        await read(`doc.querySelector('#todos .todos-close').click()`);
        const hid = await read(`doc.getElementById('todos').hidden`);
        todos([{ text: 'Write the sills', done: true }, { text: 'Join the posts', done: true }]);
        const shownAgain = await waitFor(() => read(`!doc.getElementById('todos').hidden`), { timeoutMs: 5000 }).catch(() => false);
        todos([]);
        check('the to-do list\'s × hides it until the agent changes it', listed && hid === true && shownAgain,
            JSON.stringify({ listed, hid, shownAgain }));

        // What an edit by the agent runs: the view's file built as it is, and that build's problems.
        await openFrame(FRAME);
        const report = await runAppCommand('kigumi.automationBuildReport', { filePath: FRAME, graceMs: 0 });
        const described = await runAppCommand('kigumi.automationDescribeFrame', { filePath: FRAME });
        check("describe_frame gives a view's timbers with their faces, what each touches and its joints, all one group",
            described && described.ok && described.timbers.length === 4 && described.groups.length === 1
                && described.timbers.every((one) => one.min && one.touches.length > 0 && one.joints.length === 2
                    && Object.keys(one.faces).length === 6 && /^[+-][XYZ]$/.test(one.faces.TOP)),
            JSON.stringify(described && { groups: described.groups, first: described.timbers && described.timbers[0] }).slice(0, 300));
        check('a view\'s file builds on request, reporting that build\'s problems',
            report && report.ok === true && Array.isArray(report.entries) && report.entries.length === 0, JSON.stringify(report).slice(0, 200));

        const { Menu } = require('electron');
        const agentPanel = () => Boolean(connection().findPanel((panel) => panel.type === 'agent'));
        settings.set('agent.enabled', false);
        const onlySettings = await waitFor(() => read(`!doc.getElementById('settings-menu').hidden
            && doc.getElementById('messages').offsetParent === null && doc.querySelector('.agent-off-note').offsetParent !== null`),
        { timeoutMs: 5000 }).catch(() => false);
        check('turned off, the agent panel stays, showing only its settings, and its button stays',
            onlySettings && agentPanel() && !(await inShell(`document.querySelector('#toggle-right').hidden`)));
        await read(`doc.getElementById('setting-agent-enabled').click()`);
        const back = await waitFor(() => settings.get('agent.enabled') === true
            && read(`doc.getElementById('messages').offsetParent !== null`), { timeoutMs: 5000 }).catch(() => false);
        check('turned back on from its settings, the chat returns, the panel still shown', back && agentPanel()
            && await inShell(`!document.querySelector('#slot-right').hidden`));

        const enableItem = () => Menu.getApplicationMenu().items.flatMap((item) => (item.submenu ? item.submenu.items : []))
            .find((item) => item.label === 'Enable Built-in Agent');
        check('Kigumi > Enable Built-in Agent is checked while it is on', enableItem() && enableItem().checked === true);
        enableItem().click();
        check('and unchecking it turns the agent off', await waitFor(() => settings.get('agent.enabled') === false,
            { timeoutMs: 5000 }).then(() => true, () => false));

        check('a view\'s options offer the agent panel', await openFrame() && await waitFor(() => inShell(`(() => {
            const doc = document.querySelector('#slot-center iframe:not([hidden])').contentDocument;
            return !!doc.querySelector('#beta-agent-toggle');
        })()`), { timeoutMs: 10000 }).then(() => true, () => false));
        settings.set('agent.enabled', true);
    },
};
