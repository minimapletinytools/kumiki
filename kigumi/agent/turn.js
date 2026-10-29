/**
 * One turn of the agent panel's conversation: the user's request into the conversation's log, the
 * agent loop run on it (agent/agent-loop.js), the turn's checkpoint, and how it ended for the panel:
 * done with its cost, stopped, or failed.
 */

const { harnessOf } = require('./models');
const { runTurn } = require('./agent-loop');
const { instructions } = require('./agent');
const { promptEntries } = require('./prompt-content');

/** What to tell the user for a failed request: {key, text}, the key for the panel to show it in its language. */
function describeFailure(error) {
    const status = error && (error.statusCode || (error.lastError && error.lastError.statusCode));
    if (status === 402) {
        return { key: 'agent.error.noCredit', text: 'Out of credit.' };
    }
    if (status === 401) {
        return { key: 'agent.error.refused', text: 'Not signed in, or the API key was refused.' };
    }
    return { text: String((error && error.message) || error) };
}

/**
 * Run the user's request `text` (and `images`) as a turn of `conversation`.
 *
 * @param {object} options
 * @param {object} options.conversation  agent/conversation.js
 * @param {string} options.text
 * @param {object[]} options.images      [{mediaType, data}]
 * @param {object} options.host          agent/agent.js
 * @param {object[]} options.tools
 * @param {object} options.profile       the model's row (agent/models.js)
 * @param {() => Promise<object>} options.createModel  the AI SDK language model
 * @param {{maxOutputTokens: number, planMode: boolean}} options.settings
 * @param {(toolName: string, input: object) => Promise<boolean>} options.askPermission
 * @param {() => Promise<object|null>} options.describe  what the user is looking at
 * @param {AbortSignal} options.abortSignal
 * @param {(event: object) => void} options.post  to the panel, while the conversation is the panel's
 * @param {(costUsd: number|undefined) => number|undefined} options.charged  what the user pays for a cost
 * @param {(line: string) => void} options.log
 */
async function runPanelTurn({ conversation, text, images, host, tools, profile, createModel, settings, askPermission,
    describe, abortSignal, post, charged, log }) {
    conversation.turn += 1;
    const { checkpoints } = conversation;
    checkpoints.begin(conversation.turn);
    let finished = false;
    try {
        const { costUsd } = await runTurn({
            model: await createModel(),
            images: profile.images,
            cacheMarks: Boolean(profile.cacheMarks),
            harness: harnessOf(profile),
            contextWindow: profile.contextWindow,
            maxOutputTokens: settings.maxOutputTokens,
            tools,
            files: host.files.root() ? host.files : null,
            system: instructions(host, { planMode: settings.planMode }),
            log: conversation.log,
            prompt: await promptEntries({ text, images, files: host.files, describe, modelSeesImages: profile.images }),
            abortSignal,
            askPermission,
            onEvent: post,
        });
        // Stopped, a turn can end without an error.
        finished = !abortSignal.aborted;
        post(finished ? { type: 'agent:done', isError: false, costUsd: charged(costUsd) } : { type: 'agent:done', isError: false, stopped: true });
    } catch (error) {
        // The log keeps what the turn did before it failed, so asking again carries on from there.
        if (abortSignal.aborted) {
            post({ type: 'agent:done', isError: false, stopped: true });
        } else {
            log(`[agent] ${(error && error.stack) || error}`);
            const failure = describeFailure(error);
            post({ type: 'agent:done', isError: true, error: failure.text, errorKey: failure.key });
        }
    } finally {
        const changed = await checkpoints.end();
        if (changed) post({ type: 'agent:checkpoint', ...changed });
        // A step cut off after an edit never reached the log: say what changed.
        if (changed && !finished) {
            conversation.log.push({ note: 'interrupted', text: `Before it stopped, your last turn changed ${changed.files.join(', ')}. `
                + 'Read them before relying on what you think is in them.' });
        }
    }
}

module.exports = { runPanelTurn, describeFailure };
