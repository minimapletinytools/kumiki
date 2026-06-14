const fs = require('fs');
const path = require('path');

const KUMIKI_YAML_RELATIVE_PATH = path.join('.kigumi', 'kumiki.yaml');
const LEGACY_KIGUMI_YAML_NAME = '.kigumi.yaml';

function findMarkerRoot(startDir) {
    let candidate = path.resolve(startDir);

    while (true) {
        // Local-dev mode should only match an actual repository root.
        if (
            fs.existsSync(path.join(candidate, 'kumiki'))
            && fs.existsSync(path.join(candidate, 'pyproject.toml'))
        ) {
            return { projectRoot: candidate, isLocalDev: true, marker: 'kumiki' };
        }
        if (fs.existsSync(path.join(candidate, KUMIKI_YAML_RELATIVE_PATH))) {
            return { projectRoot: candidate, isLocalDev: false, marker: KUMIKI_YAML_RELATIVE_PATH };
        }
        if (fs.existsSync(path.join(candidate, LEGACY_KIGUMI_YAML_NAME))) {
            return { projectRoot: candidate, isLocalDev: false, marker: LEGACY_KIGUMI_YAML_NAME };
        }

        const parent = path.dirname(candidate);
        if (parent === candidate) {
            return null;
        }
        candidate = parent;
    }
}

function ensureKigumiYaml(projectRoot) {
    const kumikiYamlPath = path.join(projectRoot, KUMIKI_YAML_RELATIVE_PATH);
    if (fs.existsSync(kumikiYamlPath)) {
        return;
    }
    // Honor a legacy root-level .kigumi.yaml without rewriting it.
    if (fs.existsSync(path.join(projectRoot, LEGACY_KIGUMI_YAML_NAME))) {
        return;
    }
    fs.mkdirSync(path.dirname(kumikiYamlPath), { recursive: true });
    fs.writeFileSync(kumikiYamlPath, 'kumiki_version: latest\n', 'utf8');
}

function resolveProjectEnvironment(options = {}) {
    const filePath = options.filePath ? path.resolve(options.filePath) : null;
    const workspaceRoot = options.workspaceRoot ? path.resolve(options.workspaceRoot) : null;
    const createMarkerIfMissing = options.createMarkerIfMissing !== false;

    if (workspaceRoot && filePath) {
        const normalizedRoot = workspaceRoot.endsWith(path.sep)
            ? workspaceRoot
            : `${workspaceRoot}${path.sep}`;
        const fileInsideWorkspace = filePath === workspaceRoot || filePath.startsWith(normalizedRoot);

        // For shipped/dependency files outside the workspace, always anchor
        // environment resolution to the workspace project.
        if (!fileInsideWorkspace) {
            const fromWorkspace = findMarkerRoot(workspaceRoot);
            if (fromWorkspace) {
                return {
                    ...fromWorkspace,
                    source: 'workspace-preferred',
                };
            }

            if (createMarkerIfMissing) {
                ensureKigumiYaml(workspaceRoot);
            }

            return {
                projectRoot: workspaceRoot,
                isLocalDev: false,
                marker: null,
                source: 'workspace-preferred-fallback',
            };
        }
    }

    if (filePath) {
        const fromFile = findMarkerRoot(path.dirname(filePath));
        if (fromFile) {
            return {
                ...fromFile,
                source: 'file',
            };
        }
    }

    if (workspaceRoot) {
        const fromWorkspace = findMarkerRoot(workspaceRoot);
        if (fromWorkspace) {
            return {
                ...fromWorkspace,
                source: 'workspace',
            };
        }

        if (createMarkerIfMissing) {
            ensureKigumiYaml(workspaceRoot);
        }

        return {
            projectRoot: workspaceRoot,
            isLocalDev: false,
            marker: null,
            source: 'workspace-fallback',
        };
    }

    if (filePath) {
        const fallbackRoot = path.dirname(filePath);
        if (createMarkerIfMissing) {
            ensureKigumiYaml(fallbackRoot);
        }
        return {
            projectRoot: fallbackRoot,
            isLocalDev: false,
            marker: null,
            source: 'file-fallback',
        };
    }

    return {
        projectRoot: null,
        isLocalDev: false,
        marker: null,
        source: 'none',
    };
}

module.exports = {
    ensureKigumiYaml,
    resolveProjectEnvironment,
    KUMIKI_YAML_RELATIVE_PATH,
    LEGACY_KIGUMI_YAML_NAME,
};
