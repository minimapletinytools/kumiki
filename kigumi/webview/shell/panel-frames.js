// The core's panels as iframes, whichever layout shows them: each one made, loaded and removed as
// `shell:state` says, messages to and from it, and the app's shortcuts handed to it. The layout
// says where a panel's iframe goes (`place`) and whether it shows (`shown`).

/**
 * @param {object} options
 * @param {{send: (message: object) => void}} options.core
 * @param {(panel: object, iframe: HTMLIFrameElement) => void} options.place  put a new iframe in the page
 * @param {(type: string, payload: object) => boolean} [options.intercept]  a panel's own message to the
 *   layout (one that starts `shell-ui:`); true if handled, so it doesn't go on to the core
 * @param {(command: string) => void} options.onKeyCommand  a shortcut pressed in a panel
 */
export function createPanelFrames({ core, place, intercept = () => false, onKeyCommand }) {
    const frames = new Map(); // panel id -> { iframe, url, loaded, queue, panel }
    let keyBindings = null;

    function frameSource(panel) {
        const hash = panel.state === undefined ? '' : `#${encodeURIComponent(JSON.stringify(panel.state))}`;
        return panel.url + hash;
    }

    function sendKeysTo(iframe) {
        if (!keyBindings || !iframe.contentWindow) return;
        iframe.contentWindow.postMessage({ kigumiShellKeys: keyBindings }, '*');
    }

    function ensure(panel) {
        let frame = frames.get(panel.id);
        if (!frame) {
            const iframe = document.createElement('iframe');
            iframe.className = 'panel-frame';
            iframe.name = panel.id;
            frame = { iframe, url: null, loaded: false, queue: [], panel };
            iframe.addEventListener('load', () => {
                if (!frame.url) return;
                frame.loaded = true;
                for (const message of frame.queue.splice(0)) {
                    iframe.contentWindow.postMessage(message, '*');
                }
                sendKeysTo(iframe);
                core.send({ type: 'panel:loaded', id: panel.id });
            });
            frames.set(panel.id, frame);
            place(panel, iframe);
        }
        frame.panel = panel;
        if (panel.url && panel.url !== frame.url) {
            frame.url = panel.url;
            frame.loaded = false;
            frame.queue = [];
            frame.iframe.src = frameSource(panel);
        }
        frame.iframe.title = panel.title || panel.type;
        return frame;
    }

    function idForSource(source) {
        for (const [id, frame] of frames) {
            if (frame.iframe.contentWindow === source) return id;
        }
        return null;
    }

    window.addEventListener('message', (event) => {
        const data = event.data;
        if (!data || data.kigumiPanel !== true) return;
        const id = idForSource(event.source);
        if (!id) return;
        if (data.type === 'keyCommand' && typeof data.command === 'string') {
            // A key pressed in a panel (panel-bridge.js), for one of the app's shortcuts.
            onKeyCommand(data.command);
        } else if (data.type === 'message') {
            const message = data.message;
            if (message && typeof message.type === 'string' && message.type.startsWith('shell-ui:')
                && intercept(message.type, { ...message, panelId: id })) {
                return;
            }
            core.send({ type: 'panel:message', id, message });
        } else if (data.type === 'state') {
            core.send({ type: 'panel:state', id, state: data.state });
        }
    });

    return {
        /** Make, update and remove iframes to match `panels`; `shown(panel)` says which are visible. */
        render(panels, shown) {
            const live = new Set(panels.map((panel) => panel.id));
            for (const [id, frame] of frames) {
                if (!live.has(id)) {
                    frame.iframe.remove();
                    frames.delete(id);
                }
            }
            for (const panel of panels) {
                ensure(panel).iframe.hidden = !shown(panel);
            }
        },

        /** Send a message to a panel, once it has loaded. */
        send(id, message) {
            const frame = frames.get(id);
            if (!frame) return;
            if (frame.loaded) {
                frame.iframe.contentWindow.postMessage(message, '*');
            } else {
                frame.queue.push(message);
            }
        },

        /** The app's shortcuts for panels to match (null: the panels keep their keys). */
        setKeyBindings(bindings) {
            const sent = JSON.stringify(bindings);
            if (sent === JSON.stringify(keyBindings)) return;
            keyBindings = bindings;
            for (const frame of frames.values()) {
                if (frame.loaded) sendKeysTo(frame.iframe);
            }
        },

        iframe(id) {
            const frame = frames.get(id);
            return frame ? frame.iframe : null;
        },
    };
}
