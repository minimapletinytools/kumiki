/**
 * The agent panel's tool permissions: whether a tool may run (agent/permissions.js), and when the
 * user must say, the question put to the panel and its answer.
 */

const { PLAN_MODE_REFUSAL, decide } = require('./permissions');

class PermissionGate {
    /**
     * @param {object} options
     * @param {() => object[]} options.tools      the agent's tools, for their effects
     * @param {() => {mode: string, alwaysAllow: string[], planMode: boolean}} options.settings
     * @param {(toolName: string) => void} options.allowAlways  keep a tool allowed from now on
     * @param {(input: object) => boolean} options.knownFile  whether a 'run' tool's file is one a view
     *     shows or the agent wrote
     * @param {(message: object) => void} options.post  to the panel
     */
    constructor({ tools, settings, allowAlways, knownFile, post }) {
        Object.assign(this, { tools, settings, allowAlways, knownFile, post });
        this.pending = new Map();
        this.nextRequest = 1;
    }

    /** Resolve true if `toolName` may run with `input`, asking the panel if the user must say; reject in plan mode. */
    ask(toolName, input) {
        // An unknown tool is treated as one that edits.
        const tool = this.tools().find((candidate) => candidate.name === toolName) || { name: toolName, effect: 'edit' };
        const decision = decide(this.settings(), tool, { knownFile: tool.effect === 'run' && this.knownFile(input) });
        if (decision === 'refuse') return Promise.reject(new Error(PLAN_MODE_REFUSAL));
        if (decision === 'allow') return Promise.resolve(true);
        const requestId = this.nextRequest++;
        return new Promise((resolve) => {
            this.pending.set(requestId, { toolName, answer: resolve });
            this.post({ type: 'agent:permission', requestId, toolName, input });
        });
    }

    /** The panel's answer to a question; `always` keeps the tool allowed. */
    answer({ requestId, allow, always }) {
        const pending = this.pending.get(requestId);
        if (!pending) return;
        this.pending.delete(requestId);
        if (allow && always) this.allowAlways(pending.toolName);
        pending.answer(Boolean(allow));
    }

    /** Answer every question waiting with no. */
    refuseAll() {
        for (const { answer } of this.pending.values()) answer(false);
        this.pending.clear();
    }
}

module.exports = { PermissionGate };
