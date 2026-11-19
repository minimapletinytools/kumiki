// The messages between a panel and the shell's layout (webview/shell/phone-layout.js), which never
// reach the core: panel-frames.js keeps every `shell-ui:` message a panel sends for the layout.

export const SHELL_UI = Object.freeze({
    /** Shell → panel: { form: 'phone' } once the panel loads in the phone layout. */
    form: 'shell-ui:form',
    /** Shell → agent: { expanded } when its sheet opens or closes. */
    agentSheet: 'shell-ui:agent-sheet',
    /** Agent → shell: open the sheet (the text box was tapped). */
    agentExpand: 'shell-ui:agent-expand',
    /** Agent → shell: close the sheet. */
    agentCollapse: 'shell-ui:agent-collapse',
    /** Explorer → shell: close the project menu (a row was chosen). */
    closeMenu: 'shell-ui:close-menu',
});

/** Call `onForm(form)` when the shell says which form this panel is laid out for. */
export function listenForForm(onForm) {
    window.addEventListener('message', (event) => {
        const data = event.data;
        if (data && data.type === SHELL_UI.form && typeof data.form === 'string') onForm(data.form);
    });
}
