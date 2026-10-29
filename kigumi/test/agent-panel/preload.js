// Records what the agent panel page posts to its shell (webview/shell/panel-bridge.js).
window.__posted = [];
window.addEventListener('message', (event) => {
    if (event.data && event.data.kigumiPanel && event.data.type === 'message') window.__posted.push(event.data.message);
});
