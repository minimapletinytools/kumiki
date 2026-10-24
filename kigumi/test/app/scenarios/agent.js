// The agent panel: it lists the models, offers signing in when there is no key, and a model picked
// there is kept; with a key set, it says it is using it.

module.exports = {
    name: 'agent',
    async run({ check, inShell, waitFor, settings }) {
        const agentDoc = 'document.querySelector("#slot-right iframe").contentDocument';
        const read = (script) => inShell(`(() => { const doc = ${agentDoc}; return ${script}; })()`);

        await inShell(`document.querySelector('#toggle-right').click()`);
        const models = await waitFor(() => read(`doc && doc.querySelectorAll('#model-select option').length`)
            .catch(() => 0), { timeoutMs: 10000 }).catch(() => 0);
        const note = await read(`doc.getElementById('route-note').textContent`);
        check('the agent lists the models and, with no key, offers signing in',
            models >= 4 && note.includes('Sign in') && note.includes('GitHub'), `${models} models; ${note}`);

        settings.set('agent.openrouterApiKey', 'sk-or-test');
        await read(`(() => { const select = doc.getElementById('model-select'); select.value = 'claude-haiku-4.5';
            select.dispatchEvent(new Event('change')); })()`);
        const using = await waitFor(() => read(`doc.getElementById('route-note').textContent`)
            .then((text) => (text.includes('OpenRouter key') ? text : null)), { timeoutMs: 5000 }).catch(() => '');
        check('a model picked in the panel is kept, and the panel says which key it uses',
            settings.get('agent.model') === 'claude-haiku-4.5' && Boolean(using), `${settings.get('agent.model')}; ${using}`);
    },
};
