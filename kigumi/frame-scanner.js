/**
 * Thin bridge to kumiki.librarian — the JS side owns NO scanning logic.
 *
 * All discovery, AST analysis, traversal, and patternbook loading happens in
 * Python via `python -m kumiki.librarian_cli scan-workspace <root>`.  This
 * file only spawns that process and parses its JSON output.
 */

const fs = require('fs');
const path = require('path');
const { spawn } = require('child_process');
const { getVenvPythonCandidates } = require('./python-env');

function getPythonCandidates(workspaceRoot) {
    const fallbacks = process.platform === 'win32' ? ['python'] : ['python3', 'python'];
    return [...getVenvPythonCandidates(workspaceRoot), ...fallbacks];
}

function runLibrarianCli(pythonCommand, workspaceRoot, timeoutMs) {
    return new Promise((resolve, reject) => {
        const args = ['-m', 'kumiki.librarian_cli', 'scan-workspace', workspaceRoot];
        const child = spawn(pythonCommand, args, {
            cwd: workspaceRoot,
            stdio: ['ignore', 'pipe', 'pipe'],
        });

        let stdout = '';
        let stderr = '';
        let finished = false;

        const timer = setTimeout(() => {
            if (finished) return;
            finished = true;
            child.kill('SIGKILL');
            reject(new Error(`librarian_cli timed out after ${timeoutMs}ms`));
        }, timeoutMs);

        child.stdout.on('data', (chunk) => { stdout += chunk.toString(); });
        child.stderr.on('data', (chunk) => { stderr += chunk.toString(); });

        child.on('error', (error) => {
            if (finished) return;
            finished = true;
            clearTimeout(timer);
            reject(error);
        });

        child.on('close', (code) => {
            if (finished) return;
            finished = true;
            clearTimeout(timer);

            if (code !== 0) {
                reject(new Error(`librarian_cli exited ${code}: ${stderr.trim()}`));
                return;
            }
            let parsed;
            try {
                parsed = JSON.parse((stdout || '').trim() || '{}');
            } catch (error) {
                reject(new Error(`librarian_cli produced invalid JSON: ${error.message}`));
                return;
            }
            if (!parsed.ok) {
                reject(new Error(
                    `librarian_cli error: ${parsed.error || 'unknown'}` +
                    (parsed.traceback ? `\n${parsed.traceback}` : '')
                ));
                return;
            }
            resolve(parsed.result || {});
        });
    });
}

async function callLibrarian(workspaceRoot, options) {
    const timeoutMs = Number.isFinite(options.timeoutMs) ? options.timeoutMs : 20000;
    const pythonCandidates = options.pythonCommand
        ? [options.pythonCommand]
        : getPythonCandidates(workspaceRoot);

    const errors = [];
    let sawModuleMissing = false;
    for (const py of pythonCandidates) {
        if (py.includes(path.sep) && !fs.existsSync(py)) continue;
        try {
            return await runLibrarianCli(py, workspaceRoot, timeoutMs);
        } catch (error) {
            const msg = (error && error.message) ? error.message : String(error);
            errors.push(`'${py}' failed: ${msg}`);
            // Continue probing other interpreters when:
            //  - the binary itself is missing (ENOENT), or
            //  - the chosen interpreter has no (new enough) kumiki installed.
            const isModuleMissing = /No module named ['"]?kumiki/i.test(msg);
            const isEnoent = /ENOENT/.test(msg) || (error && error.code === 'ENOENT');
            if (isModuleMissing) sawModuleMissing = true;
            if (!isEnoent && !isModuleMissing) {
                throw error;
            }
        }
    }
    const hint = sawModuleMissing
        ? ' (kumiki is not installed, or is too old — needs `librarian_cli`; try `pip install -U kumiki` in your workspace venv)'
        : '';
    throw new Error(
        `No Python interpreter could run librarian_cli${hint}` +
        ` (tried ${pythonCandidates.length}):\n${errors.join('\n')}`
    );
}

async function scanWorkspaceForFrames(workspaceRoot, options = {}) {
    const logLine = typeof options.logLine === 'function' ? options.logLine : null;
    if (logLine) {
        logLine(`[workspace-scan] delegating to librarian_cli root=${workspaceRoot}`);
    }

    const scanErrors = [];
    let index;
    try {
        index = await callLibrarian(workspaceRoot, options);
    } catch (error) {
        const msg = (error && error.message) ? error.message : String(error);
        scanErrors.push({ filePath: workspaceRoot, reason: `librarian scan failed: ${msg}` });
        if (logLine) logLine(`[workspace-scan] failed: ${msg}`);
        return { frameFiles: [], patternbookFiles: [], scanErrors };
    }

    const patternbookFiles = [];
    for (const rec of (index.patternbooks || [])) {
        const relPath = rec.relative_path || path.relative(workspaceRoot, rec.file_path);
        const allPatterns = Array.isArray(rec.patterns) ? rec.patterns : [];
        const sidebarPatterns = allPatterns.filter(
            (p) => !Array.isArray(p.tags) || !p.tags.includes('poop')
        );
        patternbookFiles.push({
            filePath: rec.file_path,
            relativePath: relPath,
            patternbookName: path.basename(rec.file_path || '', '.py'),
            patterns: sidebarPatterns,
            loadError: rec.load_error || null,
        });
        if (logLine) {
            logLine(`[workspace-scan] patternbook=${relPath} patterns=${sidebarPatterns.length}`);
        }
    }

    const frameFiles = [];
    for (const rec of (index.frame_examples || [])) {
        const relPath = rec.relative_path || path.relative(workspaceRoot, rec.file_path);
        frameFiles.push({
            filePath: rec.file_path,
            relativePath: relPath,
            chosenFrameName: rec.chosen_frame_name || null,
            chosenFrameKind: rec.chosen_frame_kind || null,
            allFrameNames: Array.isArray(rec.all_frame_names) ? rec.all_frame_names : [],
            multipleFrames: !!rec.multiple_frames,
            loadError: rec.load_error || null,
        });
        if (logLine) {
            logLine(
                `[workspace-scan] frame=${relPath} chosen=${rec.chosen_frame_name}` +
                ` kind=${rec.chosen_frame_kind} multiple=${!!rec.multiple_frames}`
            );
        }
    }

    patternbookFiles.sort((a, b) => a.relativePath.localeCompare(b.relativePath));
    frameFiles.sort((a, b) => a.relativePath.localeCompare(b.relativePath));

    if (logLine) {
        logLine(`[workspace-scan] done patternbooks=${patternbookFiles.length} frames=${frameFiles.length}`);
    }
    return { frameFiles, patternbookFiles, scanErrors };
}

module.exports = {
    scanWorkspaceForFrames,
};
