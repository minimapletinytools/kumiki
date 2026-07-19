(function (globalScope) {
    // Package-time feature flags.
    //
    // These gate features that are still under development and should ship
    // "dark": hidden from the UI and inert, regardless of any persisted
    // viewer settings, until a developer flips the flag below and republishes.
    // They are NOT user-facing settings — for those, see the `kigumi.viewer.*`
    // entries in package.json's `contributes.configuration` (VS Code Settings
    // UI, toggleable by anyone who installs the extension).
    //
    // This file is loaded both as a Node module (via require, e.g. from
    // frame-view-session.js) and as a plain <script> in the webview (via
    // viewer.html/viewer.js, exposing window.FEATURE_FLAGS) — the same
    // pattern used by assembly-timeline.js and selection-store.js — so a
    // single committed value gates both the extension host and the webview.
    //
    // To add a flag: add a key below with a short comment, then gate BOTH
    // sides that reference the feature — see assemblyPreview for the pattern:
    //   - extension host: frame-view-session.js calls
    //     applyFeatureFlagsToLayersPayload so gated data never reaches the
    //     webview, even if the flag flips off after the webview loaded.
    //   - webview: viewer-app.js skips rendering the option controls and the
    //     feature itself, and ignores the field in persisted viewer settings.
    const FEATURE_FLAGS = Object.freeze({
        // Assembly preview timeline (kumiki/assembly.py + the bottom timeline
        // bar in the viewer). The flag is the package-time MASTER switch; on
        // top of it the user-facing 'kigumi.viewer.assemblyPreview' VS Code
        // setting (default off) toggles the feature per machine/workspace.
        assemblyPreview: true,
    });

    // Strips payload fields for disabled features before a layers-tree
    // payload reaches the webview (called from frame-view-session.js), so a
    // gated feature is fully inert regardless of any persisted viewer
    // settings or stale in-flight data. Disabled means: the package-time flag
    // is off, OR the caller passes the user setting as false. Pure function —
    // add a strip rule here alongside each new gated payload field.
    function applyFeatureFlagsToLayersPayload(layersPayload, options = {}) {
        if (!layersPayload || typeof layersPayload !== 'object') {
            return layersPayload;
        }
        const assemblyEnabled = FEATURE_FLAGS.assemblyPreview
            && options.assemblyPreviewSetting !== false;
        if (!assemblyEnabled && 'assembly' in layersPayload) {
            const { assembly, ...rest } = layersPayload;
            return rest;
        }
        return layersPayload;
    }

    const exported = { FEATURE_FLAGS, applyFeatureFlagsToLayersPayload };
    if (typeof module !== 'undefined' && module.exports) {
        module.exports = exported;
    }
    globalScope.FEATURE_FLAGS = FEATURE_FLAGS;
})(typeof window !== 'undefined' ? window : globalThis);
