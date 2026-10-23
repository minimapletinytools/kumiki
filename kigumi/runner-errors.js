/**
 * What a runner error says, as data: its message, traceback and type, where in the user's code it
 * happened, and the line a view shows for it.
 */

const fs = require('fs');

/** Returns `{ message, traceback, type }` from an error a runner request threw. */
function extractRunnerErrorDetails(error) {
    const payload = error && error.runnerError && typeof error.runnerError === 'object'
        ? error.runnerError
        : null;
    const message = payload && typeof payload.message === 'string'
        ? payload.message
        : (error && error.message ? error.message : String(error));
    const traceback = payload && typeof payload.traceback === 'string'
        ? payload.traceback
        : (error && typeof error.runnerTraceback === 'string' ? error.runnerTraceback : null);
    const type = payload && typeof payload.type === 'string'
        ? payload.type
        : (error && typeof error.runnerErrorType === 'string' ? error.runnerErrorType : null);
    return { message, traceback, type };
}

/** Returns the innermost `{ filePath, lineNumber }` of a traceback that exists on disk, or null. */
function parseTracebackLocation(traceback) {
    if (!traceback || typeof traceback !== 'string') {
        return null;
    }
    const fileLineRegex = /File "([^"]+)", line (\d+)/g;
    const candidates = [];
    let match = fileLineRegex.exec(traceback);
    while (match) {
        candidates.push({ filePath: match[1], lineNumber: Number(match[2]) });
        match = fileLineRegex.exec(traceback);
    }
    for (let index = candidates.length - 1; index >= 0; index -= 1) {
        const candidate = candidates[index];
        if (candidate.filePath && fs.existsSync(candidate.filePath) && Number.isFinite(candidate.lineNumber)) {
            return candidate;
        }
    }
    return null;
}

/** Returns the line a view shows for a runner error (extractRunnerErrorDetails's result). */
function deriveViewerErrorMessage(details) {
    const message = details && typeof details.message === 'string' ? details.message : '';
    if (!message) {
        return 'Unable to render this file in Kigumi viewer.';
    }

    if (message.includes("Module must expose a module-level 'example' Frame, a 'patternbook', or a build_frame() function")) {
        return "This file is not a valid Kigumi frame/example/pattern. Add module-level 'example', 'patternbook', or build_frame().";
    }

    if (message.includes('No patternbook found in')) {
        return 'This file does not define a patternbook that Kigumi can open.';
    }

    return `Kigumi failed to render this file: ${message}`;
}

module.exports = { extractRunnerErrorDetails, parseTracebackLocation, deriveViewerErrorMessage };
