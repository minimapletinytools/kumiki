/**
 * A view's exports (frame or member, as STL, 3MF, OBJ or STEP) and the cadquery-ocp install STEP
 * needs, run for the view's session (frame-view-session.js): its runner, page, log and output.
 */

const path = require('path');
const fs = require('fs');
const { getHost } = require('./host');
const { createTranslator } = require('./i18n');
const { extractRunnerErrorDetails } = require('./runner-errors');

const t = (key, params) => createTranslator(getHost().locale)(key, params);

/** Returns where a session's exports go: kigumi_exports/<file name> in the project. */
function exportDirectory(session) {
    const projectRoot = session.projectRoot;
    const baseName = path.basename(session.filePath, path.extname(session.filePath));
    const safeBaseName = (baseName || 'frame')
        .replace(/[^a-zA-Z0-9._-]+/g, '_')
        .replace(/^_+|_+$/g, '') || 'frame';
    return path.join(projectRoot, 'kigumi_exports', safeBaseName);
}

/** Exports the frame in one format; returns `{ format, writtenFiles, outputDir }`, or throws after saying so. */
async function exportFrame(session, format, includeCombined = true, includeIndividuals = true, includeAccessories = true) {
    if (!session.runnerSession) {
        return;
    }

    await session.ensureRunnerSession();

    const normalizedFormat = format === 'step'
        ? 'step'
        : format === '3mf'
            ? '3mf'
            : format === 'obj'
                ? 'obj'
                : 'stl';
    const outputDir = exportDirectory(session);
    fs.mkdirSync(outputDir, { recursive: true });

    try {
        const result = await session.runnerSession.slotRequest('export_frame', session.slotName, {
            format: normalizedFormat,
            outputDir,
            includeCombined: Boolean(includeCombined),
            includeIndividuals: Boolean(includeIndividuals),
            includeAccessories: Boolean(includeAccessories),
        });

        const writtenFiles = Array.isArray(result && result.files) ? result.files : [];
        const formatLabel = normalizedFormat.toUpperCase();
        session.log(`[export] Wrote ${writtenFiles.length} ${formatLabel} file(s) to ${outputDir}`);
        return { format: normalizedFormat, writtenFiles, outputDir };
    } catch (error) {
        const details = extractRunnerErrorDetails(error);
        const formatLabel = normalizedFormat.toUpperCase();
        session.log(`[export] ${formatLabel} export failed: ${details.message}`);

        const openOutputAction = t('message.action.openKigumiOutput');
        const installHint = normalizedFormat === 'step' && details.message.includes('cadquery-ocp')
            ? ' Install STEP support with: pip install cadquery-ocp'
            : normalizedFormat === '3mf' && details.message.includes('3MF export requires')
                ? ' Install 3MF support with: pip install lxml networkx'
            : '';
        const choice = await getHost().showMessage(
            'error',
            `Kigumi ${formatLabel} export failed: ${details.message}${installHint}`,
            openOutputAction
        );
        if (choice === openOutputAction) {
            session.channel.show(true);
        }
        throw error;
    }
}

/** Exports the frame in every format a view's export request asks for, and says how it went. */
async function exportFormats(session, message) {
    const formatsRaw = Array.isArray(message && message.formats) ? message.formats : [];
    const formats = [...new Set(formatsRaw
        .map((entry) => (typeof entry === 'string' ? entry.toLowerCase() : ''))
        .filter((entry) => entry === 'stl' || entry === '3mf' || entry === 'obj' || entry === 'step'))];

    if (formats.length === 0) {
        void getHost().showMessage('warning', t('message.selectExportFormat'));
        return;
    }

    const includeCombined = message.includeCombined !== false;
    const includeIndividuals = message.includeIndividuals === true;
    const includeAccessories = message.includeAccessories !== false;

    if (!includeCombined && !includeIndividuals) {
        void getHost().showMessage('warning', t('message.enableExportMode'));
        return;
    }

    const allWrittenFiles = [];
    const failedFormats = [];
    let outputDir = exportDirectory(session);

    for (const format of formats) {
        try {
            const result = await exportFrame(
                session,
                format,
                includeCombined,
                includeIndividuals,
                includeAccessories,
            );
            if (result && Array.isArray(result.writtenFiles)) {
                allWrittenFiles.push(...result.writtenFiles);
                outputDir = result.outputDir || outputDir;
            }
        } catch (_error) {
            failedFormats.push(format.toUpperCase());
        }
    }

    const formatLabel = formats.map((entry) => entry.toUpperCase()).join(', ');
    const summary = `Kigumi exported ${allWrittenFiles.length} file(s) across ${formatLabel} to ${outputDir}`;
    session.log(`[export] ${summary}`);

    if (failedFormats.length > 0) {
        void getHost().showMessage('warning', `${summary}. Failed: ${failedFormats.join(', ')}`);
    } else {
        void getHost().showMessage('info', summary);
    }
}

/** Exports one member (a view's context menu), as STL or STEP. */
async function exportMember(session, message) {
    const memberKey = (message && typeof message.memberKey === 'string') ? message.memberKey : '';
    const format = (message && typeof message.format === 'string') ? message.format.toLowerCase() : '';

    // memberKey/format always come from the context-menu UI (hardcoded 'stl'/'step'
    // buttons plus whichever member was right-clicked), so a malformed message here
    // indicates a webview bug, not a user mistake -- log rather than prompt.
    if (!memberKey || (format !== 'stl' && format !== 'step')) {
        session.log(`[export] requestExportMember ignored malformed message: ${JSON.stringify(message)}`);
        return;
    }

    if (!session.runnerSession) {
        return;
    }
    await session.ensureRunnerSession();

    const outputDir = exportDirectory(session);
    fs.mkdirSync(outputDir, { recursive: true });

    const formatLabel = format.toUpperCase();
    try {
        const result = await session.runnerSession.slotRequest('export_member', session.slotName, {
            memberKey,
            format,
            outputDir,
        });
        const writtenFiles = Array.isArray(result && result.files) ? result.files : [];
        const summary = `Kigumi exported ${formatLabel} for '${memberKey}' to ${writtenFiles[0] || outputDir}`;
        session.log(`[export] ${summary}`);
        void getHost().showMessage('info', summary);
        return { format, memberKey, writtenFiles, outputDir };
    } catch (error) {
        const details = extractRunnerErrorDetails(error);
        session.log(`[export] ${formatLabel} export of '${memberKey}' failed: ${details.message}`);

        const openOutputAction = t('message.action.openKigumiOutput');
        const installHint = format === 'step' && details.message.includes('cadquery-ocp')
            ? ' Install STEP support with: pip install cadquery-ocp'
            : '';
        const choice = await getHost().showMessage(
            'error',
            `Kigumi ${formatLabel} export of '${memberKey}' failed: ${details.message}${installHint}`,
            openOutputAction
        );
        if (choice === openOutputAction) {
            session.channel.show(true);
        }
        throw error;
    }
}

/** Tells the view whether cadquery-ocp (STEP export) is installed. */
async function pushCadqueryStatus(session) {
    if (!session.panel || !session.runnerSession) {
        return;
    }

    let installed = false;
    try {
        installed = await session.runnerSession.isCadqueryOcpInstalled();
    } catch (error) {
        session.log(`[export] Failed to detect cadquery-ocp: ${error.message || error}`);
    }

    session.panel.postMessage({
        type: 'dependencyStatus',
        payload: {
            cadqueryOcpInstalled: installed,
        },
    }).catch((error) => {
        session.log(`[webview] Failed to post dependency status: ${error.message || error}`);
    });
}

/** Installs cadquery-ocp, restarting the runner the session owns so it can import it. */
async function installCadqueryOcp(session) {
    if (!session.runnerSession) {
        return;
    }

    postCadqueryInstallStatus(session, true);
    try {
        await session.runnerSession.installCadqueryOcp();

        if (session.ownsRunner) {
            await session.runnerSession.dispose();
            session.runnerSession = null;
            await session.ensureRunnerSession();
        } else {
            session.log('[export] cadquery-ocp installed. Restart the main Kigumi viewer session if STEP export was attempted before install.');
        }

        await pushCadqueryStatus(session);
        void getHost().showMessage('info', t('message.cadqueryInstalled'));
    } catch (error) {
        const details = extractRunnerErrorDetails(error);
        session.log(`[export] cadquery-ocp install failed: ${details.message}`);
        const openOutputAction = t('message.action.openKigumiOutput');
        const choice = await getHost().showMessage(
            'error',
            `Failed to install cadquery-ocp: ${details.message}`,
            openOutputAction
        );
        if (choice === openOutputAction) {
            session.channel.show(true);
        }
    } finally {
        postCadqueryInstallStatus(session, false);
    }
}

function postCadqueryInstallStatus(session, isInstalling) {
    if (!session.panel) {
        return;
    }

    session.panel.postMessage({
        type: 'dependencyInstallStatus',
        payload: {
            installingCadqueryOcp: Boolean(isInstalling),
        },
    }).catch((error) => {
        session.log(`[webview] Failed to post dependency install status: ${error.message || error}`);
    });
}

module.exports = { exportDirectory, exportFrame, exportFormats, exportMember, pushCadqueryStatus, installCadqueryOcp };
