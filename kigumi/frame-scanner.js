const fs = require('fs');
const path = require('path');

const DEFAULT_IGNORE_FOLDERS = new Set([
    '.git',
    '.hg',
    '.svn',
    '.venv',
    'venv',
    'node_modules',
    '__pycache__',
    'dist',
    'build',
    '.mypy_cache',
    '.pytest_cache',
    '.ruff_cache',
    '.tox',
    '.nox',
    '.eggs',
    '.idea',
    '.vscode',
]);

const SKIP_SEGMENT_MATCH = [
    'site-packages',
    '.egg-info',
    '.dist-info',
    'htmlcov',
    'coverage',
    'step_test_output',
];

async function readFileWithTimeout(filePath, timeoutMs) {
    let timer = null;
    const timeoutPromise = new Promise((_, reject) => {
        timer = setTimeout(() => {
            reject(new Error('scan timeout'));
        }, timeoutMs);
    });

    try {
        const filePromise = fs.promises.readFile(filePath, 'utf8');
        return await Promise.race([filePromise, timeoutPromise]);
    } finally {
        if (timer) {
            clearTimeout(timer);
        }
    }
}

function shouldSkipDirectoryName(name, extraIgnoreFolders) {
    if (!name) {
        return true;
    }

    if (DEFAULT_IGNORE_FOLDERS.has(name)) {
        return true;
    }

    if (extraIgnoreFolders && extraIgnoreFolders.has(name)) {
        return true;
    }

    if (name.endsWith('.egg-info') || name.endsWith('.dist-info')) {
        return true;
    }

    return false;
}

function shouldSkipDirectoryPath(dirPath) {
    const normalized = dirPath.replace(/\\/g, '/');
    return SKIP_SEGMENT_MATCH.some((segment) => normalized.includes(`/${segment}/`) || normalized.endsWith(`/${segment}`));
}

function detectFrameEntries(fileContent) {
    const entries = [];

    if (/^\s*example\s*=\s*/m.test(fileContent)) {
        entries.push('example');
    }

    if (/^\s*patternbook\s*=\s*/m.test(fileContent)) {
        entries.push('patternbook');
    }

    if (/^\s*def\s+build_frame\s*\(/m.test(fileContent)) {
        entries.push('build_frame()');
    }

    const fnRe = /^\s*def\s+([A-Za-z_][A-Za-z0-9_]*)\s*\(/gm;
    let fnMatch = fnRe.exec(fileContent);
    while (fnMatch) {
        const fnName = fnMatch[1];
        const lowered = fnName.toLowerCase();
        if (
            lowered.includes('frame')
            || lowered.includes('pattern')
            || lowered.includes('example')
        ) {
            entries.push(`${fnName}()`);
        }
        fnMatch = fnRe.exec(fileContent);
    }

    if (entries.length === 0 && /\bFrame\s*\(/.test(fileContent)) {
        entries.push('frame definition');
    }

    return Array.from(new Set(entries));
}

async function scanWorkspaceForFrames(workspaceRoot, options = {}) {
    const timeoutMs = Number.isFinite(options.timeoutMs) ? options.timeoutMs : 5000;
    const extraIgnoreFolders = new Set(Array.isArray(options.ignoreFolders) ? options.ignoreFolders : []);

    const queue = [workspaceRoot];
    const frameFiles = [];
    const scanErrors = [];

    while (queue.length > 0) {
        const nextDir = queue.shift();
        if (!nextDir || shouldSkipDirectoryPath(nextDir)) {
            continue;
        }

        let dirEntries = [];
        try {
            dirEntries = await fs.promises.readdir(nextDir, { withFileTypes: true });
            dirEntries.sort((a, b) => a.name.localeCompare(b.name));
        } catch (error) {
            scanErrors.push({
                filePath: nextDir,
                reason: `Unable to read directory: ${error.message || error}`,
            });
            continue;
        }

        for (const entry of dirEntries) {
            const fullPath = path.join(nextDir, entry.name);

            if (entry.isDirectory()) {
                if (shouldSkipDirectoryName(entry.name, extraIgnoreFolders)) {
                    continue;
                }
                if (shouldSkipDirectoryPath(fullPath)) {
                    continue;
                }
                queue.push(fullPath);
                continue;
            }

            if (!entry.isFile()) {
                continue;
            }

            if (!entry.name.endsWith('.py') || entry.name === '__init__.py') {
                continue;
            }

            let fileContent = '';
            try {
                fileContent = await readFileWithTimeout(fullPath, timeoutMs);
            } catch (error) {
                scanErrors.push({
                    filePath: fullPath,
                    reason: `Timed out or failed reading file: ${error.message || error}`,
                });
                continue;
            }

            const entries = detectFrameEntries(fileContent);
            if (entries.length === 0) {
                continue;
            }

            frameFiles.push({
                filePath: fullPath,
                relativePath: path.relative(workspaceRoot, fullPath),
                frameEntries: entries,
            });
        }
    }

    frameFiles.sort((a, b) => a.relativePath.localeCompare(b.relativePath));

    return {
        frameFiles,
        scanErrors,
    };
}

module.exports = {
    scanWorkspaceForFrames,
};
