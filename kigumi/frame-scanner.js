const fs = require('fs');
const path = require('path');
const { spawn } = require('child_process');

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

// ---------------------------------------------------------------------------
// Phase 1: static pre-filter — same criteria as librarian.might_contain_kumiki_frame
// No Python import; pure text/regex check to identify candidate files quickly.
// ---------------------------------------------------------------------------

function mightContainKumiFrame(fileContent) {
    // Module-level patternbook or example assignment
    if (/^\s*patternbook\s*=/m.test(fileContent)) return true;
    if (/^\s*example\s*=/m.test(fileContent)) return true;

    // build_frame function definition
    if (/^\s*def\s+build_frame\s*\(/m.test(fileContent)) return true;

    // create_*_patternbook factory function definition
    if (/^\s*def\s+create_\w+_patternbook\s*\(/m.test(fileContent)) return true;

    return false;
}

// ---------------------------------------------------------------------------
// Phase 2: Python confirmation via kumiki.librarian.scan_specific_files
// ---------------------------------------------------------------------------

const PYTHON_CONFIRM_SCRIPT = `
import json, sys, os, contextlib

ws = sys.argv[1] if len(sys.argv) > 1 else '.'
if os.path.isdir(os.path.join(ws, 'kumiki')) and ws not in sys.path:
    sys.path.insert(0, ws)

try:
    data = json.loads(sys.stdin.read())
    files = data.get('files', [])
    from kumiki.librarian import scan_specific_files
    with contextlib.redirect_stdout(sys.stderr):
        result = scan_specific_files(files, ws)
    modules = []
    for rec in result.modules:
        fp = os.path.join(result.root_folder, rec.relative_path)
        modules.append({
            'filePath': fp,
            'relativePath': rec.relative_path,
            'hasPatternbook': rec.patternbook is not None,
            'hasExample': rec.example is not None,
            'loadError': rec.load_error,
        })
    print(json.dumps({'ok': True, 'modules': modules}))
except Exception as e:
    print(json.dumps({'ok': False, 'error': str(e)}))
`.trim();

function getPythonCandidates(workspaceRoot) {
    if (process.platform === 'win32') {
        return [
            path.join(workspaceRoot, '.venv', 'Scripts', 'python.exe'),
            path.join(workspaceRoot, 'venv', 'Scripts', 'python.exe'),
            'python',
        ];
    }
    return [
        path.join(workspaceRoot, '.venv', 'bin', 'python3'),
        path.join(workspaceRoot, '.venv', 'bin', 'python'),
        path.join(workspaceRoot, 'venv', 'bin', 'python3'),
        path.join(workspaceRoot, 'venv', 'bin', 'python'),
        'python3',
        'python',
    ];
}

async function confirmCandidatesWithPython(candidates, workspaceRoot, timeoutMs, pythonCommand) {
    const pythonCandidates = pythonCommand ? [pythonCommand] : getPythonCandidates(workspaceRoot);

    let lastError = null;
    for (const py of pythonCandidates) {
        if (py.includes(path.sep) && !fs.existsSync(py)) {
            continue;
        }
        try {
            return await runPythonConfirmation(py, candidates, workspaceRoot, timeoutMs);
        } catch (error) {
            lastError = error;
        }
    }
    throw lastError || new Error('No Python interpreter found for frame confirmation');
}

function runPythonConfirmation(pythonCommand, candidates, workspaceRoot, timeoutMs) {
    return new Promise((resolve, reject) => {
        const child = spawn(pythonCommand, ['-c', PYTHON_CONFIRM_SCRIPT, workspaceRoot], {
            cwd: workspaceRoot,
            stdio: ['pipe', 'pipe', 'pipe'],
        });

        let stdout = '';
        let stderr = '';
        let finished = false;

        const timer = setTimeout(() => {
            if (finished) return;
            finished = true;
            child.kill('SIGKILL');
            reject(new Error(`Python frame confirmation timed out after ${timeoutMs}ms`));
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
                reject(new Error(`Python frame confirmation failed (exit ${code}): ${stderr.trim()}`));
                return;
            }

            let parsed;
            try {
                parsed = JSON.parse(stdout.trim() || '{}');
            } catch (error) {
                reject(new Error(`Invalid JSON from Python frame confirmation: ${error.message}`));
                return;
            }

            if (!parsed.ok) {
                reject(new Error(`Python frame confirmation error: ${parsed.error || 'unknown'}`));
                return;
            }

            resolve(parsed.modules || []);
        });

        child.stdin.write(JSON.stringify({ files: candidates }));
        child.stdin.end();
    });
}

// ---------------------------------------------------------------------------
// Directory traversal helpers
// ---------------------------------------------------------------------------

async function readFileWithTimeout(filePath, timeoutMs) {
    let timer = null;
    const timeoutPromise = new Promise((_, reject) => {
        timer = setTimeout(() => reject(new Error('scan timeout')), timeoutMs);
    });
    try {
        return await Promise.race([fs.promises.readFile(filePath, 'utf8'), timeoutPromise]);
    } finally {
        if (timer) clearTimeout(timer);
    }
}

function shouldSkipDirectoryName(name, extraIgnoreFolders) {
    if (!name) return true;
    if (DEFAULT_IGNORE_FOLDERS.has(name)) return true;
    if (extraIgnoreFolders && extraIgnoreFolders.has(name)) return true;
    if (name.endsWith('.egg-info') || name.endsWith('.dist-info')) return true;
    return false;
}

function shouldSkipDirectoryPath(dirPath) {
    const normalized = dirPath.replace(/\\/g, '/');
    return SKIP_SEGMENT_MATCH.some((segment) => normalized.includes(`/${segment}/`) || normalized.endsWith(`/${segment}`));
}

// ---------------------------------------------------------------------------
// Main export: two-phase BFS scan
//   Phase 1 — fast static pre-filter (no Python) to collect candidates
//   Phase 2 — Python subprocess uses librarian.scan_specific_files to confirm
// ---------------------------------------------------------------------------

async function scanWorkspaceForFrames(workspaceRoot, options = {}) {
    const timeoutMs = Number.isFinite(options.timeoutMs) ? options.timeoutMs : 5000;
    const extraIgnoreFolders = new Set(Array.isArray(options.ignoreFolders) ? options.ignoreFolders : []);
    const pythonCommand = options.pythonCommand || null;

    // --- Phase 1: breadth-first static pre-filter ---
    const queue = [workspaceRoot];
    const candidates = [];
    const scanErrors = [];

    while (queue.length > 0) {
        const nextDir = queue.shift();
        if (!nextDir || shouldSkipDirectoryPath(nextDir)) continue;

        let dirEntries = [];
        try {
            dirEntries = await fs.promises.readdir(nextDir, { withFileTypes: true });
            dirEntries.sort((a, b) => a.name.localeCompare(b.name));
        } catch (error) {
            scanErrors.push({ filePath: nextDir, reason: `Unable to read directory: ${error.message || error}` });
            continue;
        }

        for (const entry of dirEntries) {
            const fullPath = path.join(nextDir, entry.name);

            if (entry.isDirectory()) {
                if (!shouldSkipDirectoryName(entry.name, extraIgnoreFolders) && !shouldSkipDirectoryPath(fullPath)) {
                    queue.push(fullPath);
                }
                continue;
            }

            if (!entry.isFile() || !entry.name.endsWith('.py') || entry.name === '__init__.py') {
                continue;
            }

            let fileContent = '';
            try {
                fileContent = await readFileWithTimeout(fullPath, timeoutMs);
            } catch (error) {
                scanErrors.push({ filePath: fullPath, reason: `Timed out or failed reading file: ${error.message || error}` });
                continue;
            }

            if (mightContainKumiFrame(fileContent)) {
                candidates.push(fullPath);
            }
        }
    }

    if (candidates.length === 0) {
        return { frameFiles: [], scanErrors };
    }

    // --- Phase 2: Python librarian confirmation ---
    let confirmedModules = [];
    try {
        confirmedModules = await confirmCandidatesWithPython(candidates, workspaceRoot, timeoutMs * 4, pythonCommand);
    } catch (error) {
        scanErrors.push({ filePath: workspaceRoot, reason: `Python scan failed, showing pre-filter candidates: ${error.message || error}` });
        // Fallback: return pre-filter candidates with basic entry info
        const fallback = candidates.map((fp) => ({
            filePath: fp,
            relativePath: path.relative(workspaceRoot, fp),
            frameEntries: ['(unconfirmed)'],
        }));
        fallback.sort((a, b) => a.relativePath.localeCompare(b.relativePath));
        return { frameFiles: fallback, scanErrors };
    }

    const frameFiles = confirmedModules
        .filter((mod) => mod.hasPatternbook || mod.hasExample)
        .map((mod) => {
            const entries = [];
            if (mod.hasPatternbook) entries.push('patternbook');
            if (mod.hasExample) entries.push('example');
            return {
                filePath: mod.filePath,
                relativePath: mod.relativePath || path.relative(workspaceRoot, mod.filePath),
                frameEntries: entries,
            };
        });

    frameFiles.sort((a, b) => a.relativePath.localeCompare(b.relativePath));

    return { frameFiles, scanErrors };
}

module.exports = {
    scanWorkspaceForFrames,
};
