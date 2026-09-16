/**
 * The messages the viewer and the extension send each other.
 *
 * DECLARED, because neither side could see the other. Types were string
 * literals in both, related by nothing, so a handler could go on existing for a
 * message nobody sent and a message could be sent that nobody handled -- both
 * of which had happened, and neither of which anything could say.
 *
 * The declaration is not what makes it true; the test beside it is. It reads
 * both sides and reconciles them against this, so a new message has to be
 * written down and a dead one cannot hide.
 */

/** Webview to extension. Handled in frame-view-session's message chain. */
const TO_EXTENSION = Object.freeze([
    'addMeasurement',
    'assemblyFailureLog',
    'deleteMeasurement',
    'findCSGAtPoint',
    'hoverFeatureAtPoint',
    'openKigumiOutput',
    'openOutputChannel',
    'requestCSGByPath',
    'requestCSGTree',
    'requestDebugDrawing',
    'requestDrawingFromSelection',
    'requestDrawings',
    'requestExportFiles',
    'requestExportMember',
    'requestInstallCadqueryOcp',
    'requestRefresh',
    'requestSaveDrawings',
    'requestSaveViewerSettings',
    'saveParameters',
    'setRefreshOptions',
    'updateMeasurement',
    'viewerLog',
]);

/**
 * Webview to extension, answered by a round trip rather than the chain.
 *
 * requestWebviewRoundTrip matches these by `resultType` against the request it
 * sent, so they never reach the `message.type ===` chain and must not be
 * expected there.
 */
const TO_EXTENSION_REPLIES = Object.freeze([
    'capturePanelSnapshotResult',
    'captureScreenshotResult',
]);

module.exports = { TO_EXTENSION, TO_EXTENSION_REPLIES };
