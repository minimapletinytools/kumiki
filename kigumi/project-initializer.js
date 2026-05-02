const fs = require('fs');
const path = require('path');
const { spawn } = require('child_process');

function getVenvPython(workspaceRoot) {
    if (process.platform === 'win32') {
        return path.join(workspaceRoot, '.venv', 'Scripts', 'python.exe');
    }
    return path.join(workspaceRoot, '.venv', 'bin', 'python3');
}

function runCommand(command, args, cwd) {
    return new Promise((resolve, reject) => {
        const child = spawn(command, args, {
            cwd,
            stdio: ['ignore', 'pipe', 'pipe'],
        });

        let stdout = '';
        let stderr = '';

        child.stdout.on('data', (chunk) => {
            stdout += chunk.toString();
        });

        child.stderr.on('data', (chunk) => {
            stderr += chunk.toString();
        });

        child.on('error', (error) => {
            reject(error);
        });

        child.on('close', (code) => {
            if (code === 0) {
                resolve({ stdout, stderr });
                return;
            }
            reject(new Error(`${command} ${args.join(' ')} failed with exit code ${code}: ${stderr.trim()}`));
        });
    });
}

function ensureKigumiYaml(workspaceRoot) {
    const filePath = path.join(workspaceRoot, '.kigumi.yaml');
    if (!fs.existsSync(filePath)) {
        fs.writeFileSync(filePath, 'kumiki_version: latest\n', 'utf8');
    }
    return filePath;
}

function writeProjectYaml(workspaceRoot, pythonPath, metadata) {
    const folder = path.join(workspaceRoot, '.kigumi');
    fs.mkdirSync(folder, { recursive: true });

    const lines = [
        'schema_version: 1',
        `project_root: '${workspaceRoot.replace(/'/g, "''")}'`,
        `python_path: '${pythonPath.replace(/'/g, "''")}'`,
        `venv_path: '${path.join(workspaceRoot, '.venv').replace(/'/g, "''")}'`,
        `last_setup_at: '${new Date().toISOString()}'`,
        `created_venv: ${metadata.createdVenv ? 'true' : 'false'}`,
    ];

    fs.writeFileSync(path.join(folder, 'project.yaml'), `${lines.join('\n')}\n`, 'utf8');
}

function ensureExampleFrame(workspaceRoot) {
    const filePath = path.join(workspaceRoot, 'my_cute_frame.py');
    if (fs.existsSync(filePath)) {
        return { filePath, created: false };
    }

    const content = [
        '"""Starter Kigumi frame example."""',
        '',
        'from kumiki.construction import build_cube_frame',
        '',
        '',
        'def build_frame():',
        '    # Keep this example tiny and quick to render.',
        '    return build_cube_frame(120, 80, 100, 12)',
        '',
        '',
        'example = build_frame',
        '',
    ].join('\n');

    fs.writeFileSync(filePath, content, 'utf8');
    return { filePath, created: true };
}

async function createVenv(workspaceRoot) {
    const venvPython = getVenvPython(workspaceRoot);
    if (fs.existsSync(venvPython)) {
        return { createdVenv: false, pythonPath: venvPython };
    }

    const launchers = process.platform === 'win32'
        ? [
            { command: 'py', args: ['-3', '-m', 'venv', '.venv'] },
            { command: 'python', args: ['-m', 'venv', '.venv'] },
        ]
        : [
            { command: 'python3', args: ['-m', 'venv', '.venv'] },
            { command: 'python', args: ['-m', 'venv', '.venv'] },
        ];

    let lastError = null;
    for (const launcher of launchers) {
        try {
            await runCommand(launcher.command, launcher.args, workspaceRoot);
            return { createdVenv: true, pythonPath: venvPython };
        } catch (error) {
            lastError = error;
        }
    }

    throw lastError || new Error('Unable to create virtual environment');
}

async function installBasePackages(workspaceRoot, pythonPath) {
    await runCommand(pythonPath, ['-m', 'pip', 'install', '--upgrade', 'pip'], workspaceRoot);

    const localDevInstall = fs.existsSync(path.join(workspaceRoot, 'pyproject.toml'))
        && fs.existsSync(path.join(workspaceRoot, 'kumiki'));

    if (localDevInstall) {
        await runCommand(pythonPath, ['-m', 'pip', 'install', '-e', workspaceRoot], workspaceRoot);
    } else {
        await runCommand(pythonPath, ['-m', 'pip', 'install', 'kumiki'], workspaceRoot);
    }

    await runCommand(pythonPath, ['-m', 'pip', 'install', 'sympy', 'numpy', 'trimesh', 'manifold3d'], workspaceRoot);
}

function getInitializationStatus(workspaceRoot) {
    const isLocalDev = fs.existsSync(path.join(workspaceRoot, 'pyproject.toml'))
        && fs.existsSync(path.join(workspaceRoot, 'kumiki'));
    const hasKigumiYaml = fs.existsSync(path.join(workspaceRoot, '.kigumi.yaml'));
    const hasProjectYaml = fs.existsSync(path.join(workspaceRoot, '.kigumi', 'project.yaml'));
    const hasVenvPython = fs.existsSync(getVenvPython(workspaceRoot));
    const hasExampleFile = fs.existsSync(path.join(workspaceRoot, 'my_cute_frame.py'));
    const hasExistingProject = hasKigumiYaml || hasProjectYaml || hasVenvPython || hasExampleFile;

    let projectStatus = 'no-project';
    if (isLocalDev) {
        projectStatus = 'local-dev';
    } else if (hasExistingProject) {
        projectStatus = 'existing-project';
    }

    return {
        projectStatus,
        isLocalDev,
        hasExistingProject,
        hasKigumiYaml,
        hasProjectYaml,
        hasVenvPython,
        hasExampleFile,
        isInitialized: projectStatus === 'existing-project' && hasKigumiYaml && hasProjectYaml && hasVenvPython && hasExampleFile,
    };
}

async function initializeWorkspaceProject(workspaceRoot) {
    ensureKigumiYaml(workspaceRoot);
    const envResult = await createVenv(workspaceRoot);
    await installBasePackages(workspaceRoot, envResult.pythonPath);

    writeProjectYaml(workspaceRoot, envResult.pythonPath, {
        createdVenv: envResult.createdVenv,
    });

    const exampleResult = ensureExampleFrame(workspaceRoot);

    return {
        pythonPath: envResult.pythonPath,
        createdVenv: envResult.createdVenv,
        exampleFilePath: exampleResult.filePath,
        createdExampleFile: exampleResult.created,
    };
}

module.exports = {
    getInitializationStatus,
    initializeWorkspaceProject,
};
