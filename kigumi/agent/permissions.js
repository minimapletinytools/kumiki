/**
 * Whether a tool that changes something may run: by the permission mode (ask every time, edit
 * files without asking, do everything), the tools always allowed, and plan mode, in which nothing
 * that changes anything runs.
 */

const PERMISSION_MODES = ['ask', 'edits', 'all'];
const FILE_EDIT_TOOLS = new Set(['write_file', 'edit_file']);

/** Added to the system prompt in plan mode. */
const PLAN_MODE_NOTE = 'Plan mode is on: look as much as you need, then propose a plan, and change nothing. Tools '
    + 'that change things are refused until the user turns plan mode off and asks you to go ahead.';
/** What the model is told when a tool is refused in plan mode. */
const PLAN_MODE_REFUSAL = 'Plan mode is on, so nothing that changes anything runs. Propose the change; the user will '
    + 'turn plan mode off and ask you to go ahead.';

/**
 * 'allow', 'ask' (the user decides) or 'refuse', for a tool that changes something.
 * @param {{mode: string, alwaysAllow: string[], planMode: boolean}} settings
 */
function decide({ mode, alwaysAllow, planMode }, toolName) {
    if (planMode) return 'refuse';
    if (mode === 'all' || (mode === 'edits' && FILE_EDIT_TOOLS.has(toolName)) || alwaysAllow.includes(toolName)) {
        return 'allow';
    }
    return 'ask';
}

module.exports = { PERMISSION_MODES, FILE_EDIT_TOOLS, PLAN_MODE_NOTE, PLAN_MODE_REFUSAL, decide };
