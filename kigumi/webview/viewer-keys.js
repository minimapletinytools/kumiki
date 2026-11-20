// Which of the viewer's keys a keydown is. The order is the point: each branch reads correctly on
// its own, and moving one past another breaks it (viewer-app.js onWindowKeyDown does the action).

/**
 * @param {{key: string, defaultPrevented: boolean}} event
 * @param {object} context
 * @param {boolean} context.hovering  the pointer is over a feature
 * @param {boolean} context.typing  the caret is in a text box or other control
 * @param {(action: string) => boolean} context.pressed  whether the event is one of an action's keys
 * @returns {'cycleFeature'|'undo'|'redo'|'delete'|'escape'|'measure'|'focusSelection'|null}
 */
export function viewerKeyAction(event, { hovering, typing, pressed }) {
    // Tab, undo and redo are decided before the defaultPrevented check. The host claims them on the
    // way through: VS Code forwards a webview's keys to its own keybindings and marks ctrl-Z
    // handled, so below the check undo never ran at all. Tab only acts over a feature, which is
    // not a moment anyone is tabbing between controls.
    if (event.key === 'Tab' && hovering) return 'cycleFeature';
    // Nothing else belongs to the control with the caret: Delete in a search box deletes text,
    // and ctrl-Z there undoes typing.
    if (typing) return null;
    if (pressed('undo')) return 'undo';
    if (pressed('redo')) return 'redo';
    if (event.defaultPrevented) return null;
    if (event.key === 'Delete' || event.key === 'Backspace') return 'delete';
    if (event.key === 'Escape') return 'escape';
    if (pressed('measure')) return 'measure';
    if (pressed('focusSelection')) return 'focusSelection';
    return null;
}
