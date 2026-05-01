const fs = require('fs');
const path = require('path');
const { spawn } = require('child_process');

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
    if (process.platform === 'win32') {
        return [
            path.join(workspaceRoot, '.venv', 'Scripts', 'python.exe'),
            path.join(workspaceRoot, 'venv', 'Scripts', 'python.exe'),
            'python',
            'py',
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

function runPythonJson(pythonCommand, script, workspaceRoot, timeoutMs) {
    return new Promise((resolve, reject) => {
        const child = spawn(pythonCommand, ['-c', script], {
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

    const script = [
        'import json',
        'import os',
        'import site',
        'import sysconfig',
        '',
        'def list_py_files(root):',
        '    out = []',
        '    if not root or not os.path.isdir(root):',
        '        return out',
        '    for current, dirs, files in os.walk(root):',
        "        dirs[:] = [d for d in dirs if d not in {'__pycache__', '.git', '.venv', 'venv', 'node_modules', 'dist', 'build'} and not d.endswith('.dist-info') and not d.endswith('.egg-info')]",
        "        for name in files:",
        "            if name.endswith('.py') and name != '__init__.py':",
        '                out.append(os.path.join(current, name))',
        '    return out',
        '',
        'site_roots = set()',
        "for key in ('purelib', 'platlib'):",
        '    path = sysconfig.get_paths().get(key)',
        '    if path:',
        '        site_roots.add(path)',
        'try:',
        '    for candidate in site.getsitepackages():',
        '        site_roots.add(candidate)',
        'except Exception:',
        '    pass',
        'try:',
        '    usersite = site.getusersitepackages()',
        '    if usersite:',
        '        site_roots.add(usersite)',
        'except Exception:',
        '    pass',
        '',
        'kumiki_patterns = []',
        'kumiki_examples = []',
        'dependency_patterns = []',
        'dependency_examples = []',
        '',
        'for site_root in list(site_roots):',
        '    if not os.path.isdir(site_root):',
        '        continue',
        '    try:',
        '        entries = list(os.scandir(site_root))',
        '    except Exception:',
        '        continue',
        '    for entry in entries:',
        '        if not entry.is_dir():',
        '            continue',
        '        name = entry.name',
        '        if name == "kumiki":',
        '            kumiki_patterns.extend(list_py_files(os.path.join(entry.path, "patterns")))',
        '            continue',
        '        if name.startswith("_"):',
        '            continue',
        '        dependency_patterns.extend(list_py_files(os.path.join(entry.path, "patterns")))',
        '        dependency_examples.extend(list_py_files(os.path.join(entry.path, "examples")))',
        '',
        'print(json.dumps({',
        '    "kumikiPatterns": sorted(set(kumiki_patterns)),',
        '    "kumikiExamples": sorted(set(kumiki_examples)),',
        '    "dependencyPatterns": sorted(set(dependency_patterns)),',
        '    "dependencyExamples": sorted(set(dependency_examples)),',
        '}))',
    ].join('\n');

    let lastError = null;
    for (const candidate of candidates) {
        try {
            if (candidate.includes(path.sep) && !fs.existsSync(candidate)) {
                continue;
            }
            return await runPythonJson(candidate, script, workspaceRoot, timeoutMs);
        } catch (error) {
            lastError = error;
        }
    }

    throw lastError || new Error('No valid Python interpreter found for dependency discovery');
}

async function discoverWorkspaceContent(workspaceRoot) {
    const result = {
        workspacePatterns: [],
    };

    const workspacePatternsDir = path.join(workspaceRoot, 'patterns');
    if (fs.existsSync(workspacePatternsDir) && fs.statSync(workspacePatternsDir).isDirectory()) {
        result.workspacePatterns = await listPythonFiles(workspacePatternsDir);
    }

    return result;
}

function normalizeRunnerPatterns(result) {
    const output = {
        workspacePatterns: [],
        kumikiShippedPatterns: [],
    };

    if (!result || !Array.isArray(result.sources)) {
        return output;
    }

    for (const source of result.sources) {
        const list = Array.isArray(source.patterns) ? source.patterns : [];
        const mapped = list.map((item) => ({
            name: item.name,
            groups: Array.isArray(item.groups) ? item.groups : [],
            sourceFile: item.source_file,
        }));

        if (source.source === 'local') {
            output.workspacePatterns = output.workspacePatterns.concat(mapped);
        } else if (source.source === 'shipped') {
            output.kumikiShippedPatterns = output.kumikiShippedPatterns.concat(mapped);
        }
    }

    output.workspacePatterns.sort((a, b) => `${a.sourceFile}:${a.name}`.localeCompare(`${b.sourceFile}:${b.name}`));
    output.kumikiShippedPatterns.sort((a, b) => `${a.sourceFile}:${a.name}`.localeCompare(`${b.sourceFile}:${b.name}`));
    return output;
}

module.exports = {
    discoverDependencyContent,
    discoverWorkspaceContent,
    normalizeRunnerPatterns,
};
