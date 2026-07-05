const fs = require('fs');
const path = require('path');
const { spawn } = require('child_process');
const { getVenvPythonCandidates } = require('./python-env');

const DISCOVERY_SCRIPT_PATH = path.join(__dirname, 'dependency-discovery.py');

const SKIP_FOLDER_NAMES = new Set([
    '__pycache__',
    '.git',
    '.venv',
    'venv',
    'node_modules',
    'dist',
    'build',
]);

function dedupeAndSortPaths(pathsList) {
    return Array.from(new Set(pathsList || [])).sort((a, b) => a.localeCompare(b));
}

function normalizePatternbookRecords(records, fallbackPaths) {
    const normalized = [];
    const seen = new Set();

    for (const record of Array.isArray(records) ? records : []) {
        const sourceFile = record && (record.sourceFile || record.filePath || record.file_path);
        if (!sourceFile || seen.has(sourceFile)) {
            continue;
        }
        seen.add(sourceFile);

        const fallbackName = path.basename(sourceFile, '.py');
        const patternNames = Array.isArray(record.patternNames)
            ? record.patternNames
            : (Array.isArray(record.pattern_names) ? record.pattern_names : []);
        const groupNames = Array.isArray(record.groupNames)
            ? record.groupNames
            : (Array.isArray(record.group_names) ? record.group_names : []);

        normalized.push({
            sourceFile,
            patternbookName: record.patternbookName || fallbackName,
            patternNames: Array.from(new Set(patternNames)).sort((a, b) => a.localeCompare(b)),
            groupNames: Array.from(new Set(groupNames)).sort((a, b) => a.localeCompare(b)),
        });
    }

    for (const sourceFile of dedupeAndSortPaths(fallbackPaths || [])) {
        if (seen.has(sourceFile)) {
            continue;
        }
        const fallbackName = path.basename(sourceFile, '.py');
        normalized.push({
            sourceFile,
            patternbookName: fallbackName,
            patternNames: [fallbackName],
            groupNames: [],
        });
    }

    normalized.sort((a, b) => a.sourceFile.localeCompare(b.sourceFile));
    return normalized;
}

async function listPythonFiles(rootDir) {
    const results = [];
    const queue = [rootDir];

    while (queue.length > 0) {
        const current = queue.shift();
        let entries = [];
        try {
            entries = await fs.promises.readdir(current, { withFileTypes: true });
        } catch (_error) {
            continue;
        }

        for (const entry of entries) {
            const fullPath = path.join(current, entry.name);
            if (entry.isDirectory()) {
                if (SKIP_FOLDER_NAMES.has(entry.name) || entry.name.endsWith('.dist-info') || entry.name.endsWith('.egg-info')) {
                    continue;
                }
                queue.push(fullPath);
                continue;
            }
            if (entry.isFile() && entry.name.endsWith('.py') && entry.name !== '__init__.py') {
                results.push(fullPath);
            }
        }
    }

    return dedupeAndSortPaths(results);
}

function getPythonCandidates(workspaceRoot) {
    const fallbacks = process.platform === 'win32' ? ['python', 'py'] : ['python3', 'python'];
    return [...getVenvPythonCandidates(workspaceRoot), ...fallbacks];
}

function runPythonJson(pythonCommand, scriptPath, workspaceRoot, timeoutMs) {
    return new Promise((resolve, reject) => {
        const child = spawn(pythonCommand, [scriptPath], {
            cwd: workspaceRoot,
            stdio: ['ignore', 'pipe', 'pipe'],
        });

        let stdout = '';
        let stderr = '';
        let finished = false;

        const timer = setTimeout(() => {
            if (finished) {
                return;
            }
            finished = true;
            child.kill('SIGKILL');
            reject(new Error(`Python discovery timed out after ${timeoutMs}ms`));
        }, timeoutMs);

        child.stdout.on('data', (chunk) => {
            stdout += chunk.toString();
        });

        child.stderr.on('data', (chunk) => {
            stderr += chunk.toString();
        });

        child.on('error', (error) => {
            if (finished) {
                return;
            }
            finished = true;
            clearTimeout(timer);
            reject(error);
        });

        child.on('close', (code) => {
            if (finished) {
                return;
            }
            finished = true;
            clearTimeout(timer);

            if (code !== 0) {
                reject(new Error(`Python discovery failed with exit code ${code}: ${stderr.trim()}`));
                return;
            }

            let parsed = null;
            try {
                parsed = JSON.parse(stdout.trim() || '{}');
            } catch (error) {
                reject(new Error(`Invalid JSON from python discovery: ${error.message}; stderr=${stderr.trim()}`));
                return;
            }

            resolve(parsed);
        });
    });
}

async function discoverDependencyContent(workspaceRoot, options = {}) {
    const timeoutMs = Number.isFinite(options.timeoutMs) ? options.timeoutMs : 10000;
    const candidates = options.pythonCommand ? [options.pythonCommand] : getPythonCandidates(workspaceRoot);
    const attemptErrors = [];

    let lastError = null;
    for (const candidate of candidates) {
        try {
            if (candidate.includes(path.sep) && !fs.existsSync(candidate)) {
                continue;
            }
            const raw = await runPythonJson(candidate, DISCOVERY_SCRIPT_PATH, workspaceRoot, timeoutMs);

            const kumikiPatternPaths = dedupeAndSortPaths(raw.kumikiPatterns || []);
            const dependencyPatternPaths = dedupeAndSortPaths(raw.dependencyPatterns || []);

            return {
                kumikiPatterns: kumikiPatternPaths,
                kumikiPatternbooks: normalizePatternbookRecords(raw.kumikiPatternbooks, kumikiPatternPaths),
                kumikiExamples: dedupeAndSortPaths(raw.kumikiExamples || []),
                dependencyPatterns: dependencyPatternPaths,
                dependencyPatternbooks: normalizePatternbookRecords(raw.dependencyPatternbooks, dependencyPatternPaths),
                dependencyExamples: dedupeAndSortPaths(raw.dependencyExamples || []),
            };
        } catch (error) {
            const wrappedError = new Error(`Python candidate '${candidate}' failed: ${error.message || error}`);
            lastError = wrappedError;
            attemptErrors.push(wrappedError.message);
        }
    }

    if (lastError) {
        throw new Error(`Dependency discovery failed after trying ${candidates.length} Python candidate(s):\n${attemptErrors.join('\n')}`);
    }
    throw new Error('No valid Python interpreter found for dependency discovery');
}

module.exports = {
    discoverDependencyContent,
};
