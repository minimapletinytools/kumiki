/**
 * Whether a tool may run: by its effect, the permission mode, the tools always allowed, and plan mode.
 *
 * Effects: 'read' changes nothing; 'ui' changes only what the user sees; 'run' builds a frame,
 * running its Python; 'edit' changes project files.
 */

const EFFECTS = ['read', 'ui', 'run', 'edit'];
/** 'ask': ask before edits, and before running a file the agent didn't write and no view shows. 'auto': never ask. */
const PERMISSION_MODES = ['ask', 'auto'];

/** Added to the system prompt in plan mode. */
const PLAN_MODE_NOTE = 'Plan mode is on: look and build as much as you need, then propose a plan, and edit nothing. '
    + 'File edits are refused until the user turns plan mode off and asks you to go ahead.';
/** What the model is told when an edit is refused in plan mode. */
const PLAN_MODE_REFUSAL = 'Plan mode is on, so files are not edited. Propose the change; the user will turn plan mode '
    + 'off and ask you to go ahead.';

/** The mode a stored setting means, or null: the old 'edits' and 'all', and the old bypass switch, are 'auto'. */
function permissionMode(value, bypass = false) {
    if (PERMISSION_MODES.includes(value)) return value;
    if (value === 'edits' || value === 'all' || bypass === true) return 'auto';
    return null;
}

/**
 * Return 'allow', 'ask' or 'refuse' for `tool` ({name, effect}).
 * `knownFile`: a 'run' tool's file is shown in a view, or was written by the agent.
 */
function decide({ mode, alwaysAllow, planMode }, { name, effect }, { knownFile = false } = {}) {
    if (effect === 'read' || effect === 'ui') return 'allow';
    if (effect === 'edit' && planMode) return 'refuse';
    if (mode === 'auto' || alwaysAllow.includes(name)) return 'allow';
    if (effect === 'run' && knownFile) return 'allow';
    return 'ask';
}

module.exports = { EFFECTS, PERMISSION_MODES, PLAN_MODE_NOTE, PLAN_MODE_REFUSAL, permissionMode, decide };
