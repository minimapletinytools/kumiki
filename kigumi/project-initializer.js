const fs = require('fs');
const { isPythonAvailable, managedEnvironment } = require('./python-runtime');
const path = require('path');
const https = require('https');
const {
    ensureKigumiYaml,
    resolveProjectEnvironment,
    KUMIKI_YAML_RELATIVE_PATH,
    LEGACY_KIGUMI_YAML_NAME,
} = require('./project-root');
const {
    runCommand: spawnProcess,
    getVenvPython,
    getKigumiVersion,
    getKumikiMinimumVersion,
    isLocalDevKigumiVersion,
    kumikiCompatiblePipSpec,
    getMissingDependencies,
} = require('./python-env');
const { ensureProjectVenv, pipInstall } = require('./python-toolchain');
const { PROJECT_DOCS_DIR, removeLegacyDocs, syncProjectDocs, updateAgentsFile } = require('./project-docs');

function writeFileIfMissing(filePath, content) {
    if (fs.existsSync(filePath)) {
        return false;
    }

    fs.mkdirSync(path.dirname(filePath), { recursive: true });
    fs.writeFileSync(filePath, content, 'utf8');
    return true;
}

/**
 * The agent docs in .kigumi/docs/ (from the installed kumiki), AGENTS.md's Kigumi block,
 * and the pointer files other agents read. Old copies in docs/ are removed if untouched.
 * A local dev checkout is the source of the docs, so nothing is written into it.
 */
async function ensureAgentInstructionFiles(workspaceRoot, pythonPath, kumikiVersion, { isLocalDev = false } = {}) {
    const pointerContent = [
        '# Agent Instructions',
        '',
        'Primary instructions live in AGENTS.md at the repository root.',
        '',
        'Always read and follow:',
        '',
        '- AGENTS.md',
        '',
    ].join('\n');
    const pointers = {
        createdCopilotInstructionsFile: writeFileIfMissing(path.join(workspaceRoot, '.github', 'copilot-instructions.md'), pointerContent),
        createdClaudeInstructionsFile: writeFileIfMissing(path.join(workspaceRoot, 'CLAUDE.md'), pointerContent),
        createdCursorRulesFile: writeFileIfMissing(path.join(workspaceRoot, '.cursorrules'), pointerContent),
    };
    if (isLocalDev) {
        return { ...pointers, createdAgentsFile: false, updatedAgentsFile: false, docsSource: null,
            removedLegacyDocs: [], keptLegacyDocs: [], instructionWarnings: [] };
    }

    const { source } = await syncProjectDocs(workspaceRoot, pythonPath, kumikiVersion);
    const legacy = removeLegacyDocs(workspaceRoot);
    const agents = updateAgentsFile(workspaceRoot);
    const instructionWarnings = legacy.kept.length > 0
        ? [`The Kumiki docs moved to ${PROJECT_DOCS_DIR}. These copies in docs/ were changed, so they were kept; `
            + `delete them once you no longer need them: ${legacy.kept.join(', ')}`]
        : [];
    return {
        ...pointers,
        createdAgentsFile: agents.created,
        updatedAgentsFile: agents.changed,
        docsSource: source,
        removedLegacyDocs: legacy.removed,
        keptLegacyDocs: legacy.kept,
        instructionWarnings,
    };
}


function ensureGitignore(workspaceRoot) {
    const gitignorePath = path.join(workspaceRoot, '.gitignore');
    const requiredEntries = [
        '.venv/',
        'kigumi_exports/',
        '.kigumi/logs/',
    ];

    if (!fs.existsSync(gitignorePath)) {
        fs.writeFileSync(gitignorePath, `${requiredEntries.join('\n')}\n`, 'utf8');
        return {
            created: true,
            addedEntries: requiredEntries,
        };
    }

    const existingLines = new Set(
        fs.readFileSync(gitignorePath, 'utf8')
            .split(/\r?\n/)
            .map((line) => line.trim())
            .filter((line) => line.length > 0)
    );

    const missingEntries = requiredEntries.filter((entry) => !existingLines.has(entry));
    if (missingEntries.length === 0) {
        return {
            created: false,
            addedEntries: [],
        };
    }

    const existingContent = fs.readFileSync(gitignorePath, 'utf8');
    const needsNewline = existingContent.length > 0 && !existingContent.endsWith('\n');
    const appendPrefix = needsNewline ? '\n' : '';
    fs.appendFileSync(gitignorePath, `${appendPrefix}${missingEntries.join('\n')}\n`, 'utf8');

    return {
        created: false,
        addedEntries: missingEntries,
    };
}

function runCommand(command, args, cwd) {
    return spawnProcess(command, args, { cwd });
}

function yamlQuote(value) {
    return `'${String(value).replace(/'/g, "''")}'`;
}

function writeProjectYaml(workspaceRoot, pythonPath, metadata) {
    const folder = path.join(workspaceRoot, '.kigumi');
    fs.mkdirSync(folder, { recursive: true });

    const lines = [
        'schema_version: 1',
        `project_root: ${yamlQuote(workspaceRoot)}`,
        `python_path: ${yamlQuote(pythonPath)}`,
        `venv_path: ${yamlQuote(path.join(workspaceRoot, '.venv'))}`,
        `local_dev: ${metadata.isLocalDev ? 'true' : 'false'}`,
        `last_setup_at: ${yamlQuote(new Date().toISOString())}`,
        `created_venv: ${metadata.createdVenv ? 'true' : 'false'}`,
        `installed_viewer_deps: ${metadata.installedViewerDeps ? 'true' : 'false'}`,
    ];

    if (metadata.missingBefore.length > 0) {
        lines.push('missing_before_setup:');
        for (const pkg of metadata.missingBefore) {
            lines.push(`  - ${pkg}`);
        }
    }

    fs.writeFileSync(path.join(folder, 'kigumi.yaml'), `${lines.join('\n')}\n`, 'utf8');
}

function getBundledExampleFrameContent() {
    const canonicalExamplePath = path.resolve(__dirname, '..', 'patterns', 'structures', 'my_cute_frame.py');
    if (fs.existsSync(canonicalExamplePath)) {
        return fs.readFileSync(canonicalExamplePath, 'utf8');
    }

    return getInlineExampleFrameContent();
}

// A copy of patterns/structures/my_cute_frame.py, for an install that ships
// without patterns/. A unit test keeps the two identical.
function getInlineExampleFrameContent() {
    return [
        '# Last checked on kumiki 0.9.0',
        '"""Purpose',
        '-------',
        'Start with a small four-member frame to learn the arrange, cut, and assemble workflow.',
        '',
        'Concepts demonstrated — overview',
        '-------------------------------',
        'Simple example; small structure; face-aligned, axis-oriented construction.',
        '',
        'Concepts demonstrated — details',
        '------------------------------',
        'Two side members and two cross members use pegged mortise-and-tenon joints. Reference features',
        'identify the edges used for measurements. Dimensions are source constants; there are no Kiwari',
        'controls. Three drawings (a plan, a side and a cross) place their dimensions by hand.',
        'Recipe notes',
        '------------',
        'Starter Kigumi frame: a simple H-shaped frame made of four 90x90mm timbers.',
        '',
        'Two side timbers run in the +Y direction. Two cross timbers join them with',
        'mortise-and-tenon joints (with 15mm draw-bore pegs), inset from the ends so',
        'the mortises sit safely away from the timber ends.',
        '"""',
        '',
        '__title__ = {"en": "My cute frame", "ja": "かわいい架構"}',
        '',
        'from dataclasses import replace',
        '',
        'from kumiki import *',
        '',
        '',
        '# --- Dimensions -------------------------------------------------------------',
        '',
        'timber_size = Matrix([mm(90), mm(90)])  # 90x90mm cross section',
        '',
        'side_length = mm(600)            # length of each side timber (along Y)',
        'side_spacing = mm(500)           # center-to-center spacing of side timbers (along X)',
        'end_inset = mm(100)              # cross-timber inset from the side-timber ends',
        '',
        '# Tenon dimensions relative to joint plane (shared XY plane):',
        '# 80mm wide parallel to joint plane (along Y), 40mm tall perpendicular to joint plane (along Z).',
        'tenon_width_relative_to_joint = mm(80)',
        'tenon_height_relative_to_joint = mm(40)',
        'tenon_length = mm(75)',
        'mortise_depth = tenon_length + mm(6)',
        '',
        '# 15mm round draw-bore peg, slightly offset so the joint draws tight.',
        'peg_diameter = mm(15)',
        'peg_draw_bore_offset = mm(2)',
        '',
        '',
        '@frame',
        'def my_cute_frame(k: Optional[Kiwari] = None) -> Frame:',
        '    # Side timbers run in +Y, at x = +/- side_spacing/2.',
        '    # Each timber is measured from its bottom outside edge, its reference feature.',
        '    left_side = create_axis_aligned_timber(',
        '        bottom_position=create_v3(-side_spacing / 2, -side_length / 2, scalar(0)),',
        '        length=side_length,',
        '        size=timber_size,',
        '        length_direction=TimberFace.FRONT,',
        '        width_direction=TimberFace.RIGHT,',
        '        ticket=TimberTicket(path="Left Side", reference_features=(TimberFeature.FRONT_LEFT_EDGE,)),',
        '    )',
        '    right_side = create_axis_aligned_timber(',
        '        bottom_position=create_v3(side_spacing / 2, -side_length / 2, scalar(0)),',
        '        length=side_length,',
        '        size=timber_size,',
        '        length_direction=TimberFace.FRONT,',
        '        width_direction=TimberFace.RIGHT,',
        '        ticket=TimberTicket(path="Right Side", reference_features=(TimberFeature.RIGHT_FRONT_EDGE,)),',
        '    )',
        '',
        '    # Cross timbers run in +X, inset from the ends of the side timbers.',
        '    # Their length spans center-to-center so the tenons land inside the sides.',
        '    cross_length = side_spacing',
        '    cross_y_front = side_length / 2 - end_inset',
        '    cross_y_back = -cross_y_front',
        '',
        '    back_cross = create_axis_aligned_timber(',
        '        bottom_position=create_v3(-cross_length / 2, cross_y_back, scalar(0)),',
        '        length=cross_length,',
        '        size=timber_size,',
        '        length_direction=TimberFace.RIGHT,',
        '        width_direction=TimberFace.FRONT,',
        '        ticket=TimberTicket(path="Back Cross", reference_features=(TimberFeature.LEFT_BACK_EDGE,)),',
        '    )',
        '    front_cross = create_axis_aligned_timber(',
        '        bottom_position=create_v3(-cross_length / 2, cross_y_front, scalar(0)),',
        '        length=cross_length,',
        '        size=timber_size,',
        '        length_direction=TimberFace.RIGHT,',
        '        width_direction=TimberFace.FRONT,',
        '        ticket=TimberTicket(path="Front Cross", reference_features=(TimberFeature.BACK_RIGHT_EDGE,)),',
        '    )',
        '',
        '    # Round draw-bore peg, one per joint, centered on the tenon.',
        '    # Peg axis is perpendicular to the cross timber\'s FRONT face (i.e. through',
        '    # the side timber from the front, in global +Y on the back cross and -Y on the front cross).',
        '    peg_params = SimplePegParameters(',
        '        shape=PegShape.ROUND,',
        '        peg_positions=[(tenon_length / 2, scalar(0))],',
        '        size=peg_diameter,',
        '        depth=None,                                # through peg',
        '        tenon_hole_offset=peg_draw_bore_offset,    # draw-bore offset pulls the joint tight',
        '    )',
        '',
        '    def mortise_into_side(cross, cross_end, side):',
        '        return cut_mortise_and_tenon_joint_on_face_aligned_timbers(',
        '            arrangement=ButtJointTimberArrangement(',
        '                receiving_timber=side,',
        '                butt_timber=cross,',
        '                butt_timber_end=cross_end,',
        '                front_face_on_butt_timber=TimberLongFace.FRONT,',
        '            ),',
        '            tenon_width_relative_to_joint=tenon_width_relative_to_joint,',
        '            tenon_height_relative_to_joint=tenon_height_relative_to_joint,',
        '            tenon_length=tenon_length,',
        '            mortise_depth=mortise_depth,',
        '            peg_parameters=peg_params,',
        '        )',
        '',
        '    back_left = mortise_into_side(back_cross, TimberEnd.BOTTOM, left_side)',
        '    back_right = mortise_into_side(back_cross, TimberEnd.TOP, right_side)',
        '    front_left = mortise_into_side(front_cross, TimberEnd.BOTTOM, left_side)',
        '    front_right = mortise_into_side(front_cross, TimberEnd.TOP, right_side)',
        '    frame = Frame.from_joints([back_left, back_right, front_left, front_right], name="My Cute Frame")',
        '',
        '    return replace(frame, drawings=[',
        '        plan_drawing(frame, left_side, right_side, back_cross, front_cross),',
        '        side_drawing(frame, left_side, back_left, front_left),',
        '        cross_drawing(frame, back_cross, back_left, back_right),',
        '    ])',
        '',
        '',
        '# --- Drawings ---------------------------------------------------------------',
        '# Each dimension is placed by hand: Beside(side, lane) puts it on that side of the',
        '# work, lane 1 nearest. Features come from the timbers (face) and joints (feature).',
        '',
        'MT = MortiseAndTenonFeatures',
        '',
        '',
        'def plan_drawing(frame, left_side, right_side, back_cross, front_cross):',
        '    """The frame seen from above: its overall size and where the cross timbers sit."""',
        '    left, right = frame.cut_timber_of(left_side), frame.cut_timber_of(right_side)',
        '    back, front = frame.cut_timber_of(back_cross), frame.cut_timber_of(front_cross)',
        '    above = Viewport(label="Plan", camera=View.world("top", scale=1 / 3), measurements=[',
        '        Measure(left.face(TimberFace.LEFT), right.face(TimberFace.RIGHT), placement=Beside(DimensionSide.ABOVE)),',
        '        Measure(left.face(TimberFace.RIGHT), right.face(TimberFace.LEFT), placement=Beside(DimensionSide.BELOW)),',
        '        Measure(left.face(TimberFace.BOTTOM), left.face(TimberFace.TOP), placement=Beside(DimensionSide.LEFT, 2)),',
        '        Measure(left.face(TimberFace.BOTTOM), back.face(TimberFace.LEFT), placement=Beside(DimensionSide.LEFT)),',
        '        Measure(back.face(TimberFace.RIGHT), front.face(TimberFace.LEFT), placement=Beside(DimensionSide.LEFT)),',
        '    ])',
        '    return Drawing(name="Plan", timbers=[cut.timber for cut in (left, right, back, front)],',
        '                   viewports=[covering_page(columns(above.taking(Share(2)), Viewport(label="Preview")))])',
        '',
        '',
        'def side_drawing(frame, side, back_joint, front_joint):',
        '    """A side timber: where its two mortises and peg holes are, from its bottom end."""',
        '    cut = frame.cut_timber_of(side)',
        '    end = cut.face(TimberFace.BOTTOM)',
        '    inside = Viewport(label="Inside face", camera=View.of_face(side, TimberFace.RIGHT, scale=1 / 3), measurements=[',
        '        Measure(end, back_joint.feature(MT.MORTISE_LEFT), placement=Beside(DimensionSide.BELOW)),',
        '        Measure(back_joint.feature(MT.MORTISE_LEFT), back_joint.feature(MT.MORTISE_RIGHT),',
        '                placement=Beside(DimensionSide.BELOW)),',
        '        Measure(end, front_joint.feature(MT.MORTISE_LEFT), placement=Beside(DimensionSide.BELOW, 2)),',
        '        Measure(back_joint.feature(MT.MORTISE_FRONT), back_joint.feature(MT.MORTISE_BACK),',
        '                placement=Beside(DimensionSide.LEFT)),',
        '    ])',
        '    top = Viewport(label="Top face", camera=View.of_face(side, TimberFace.BACK, scale=1 / 3), measurements=[',
        '        Measure(end, back_joint.feature(MT.PEG_HOLE_AXIS, on=side), placement=Beside(DimensionSide.ABOVE)),',
        '        Measure(end, front_joint.feature(MT.PEG_HOLE_AXIS, on=side), placement=Beside(DimensionSide.ABOVE, 2)),',
        '    ])',
        '    return Drawing(name=f"{side.ticket.path} ×2", timbers=[side],',
        '                   viewports=[covering_page(columns(rows(inside, top).taking(Share(2)), Viewport(label="Preview")))])',
        '',
        '',
        'def cross_drawing(frame, cross, start_joint, end_joint):',
        '    """A cross timber: its length between shoulders, and each tenon and its peg hole."""',
        '    top = Viewport(label="Top face", camera=View.of_face(cross, TimberFace.FRONT, scale=1 / 3), measurements=[',
        '        Measure(start_joint.feature(MT.SHOULDER), end_joint.feature(MT.SHOULDER), placement=Beside(DimensionSide.ABOVE)),',
        '        Measure(start_joint.feature(MT.SHOULDER), start_joint.feature(MT.TENON_BOTTOM), placement=Beside(DimensionSide.BELOW)),',
        '        Measure(start_joint.feature(MT.PEG_HOLE_AXIS, on=cross), start_joint.feature(MT.SHOULDER), placement=Beside(DimensionSide.ABOVE)),',
        '        Measure(start_joint.feature(MT.TENON_RIGHT), start_joint.feature(MT.TENON_LEFT), placement=Beside(DimensionSide.LEFT)),',
        '    ])',
        '    side = Viewport(label="Side face", camera=View.of_face(cross, TimberFace.RIGHT, scale=1 / 3), measurements=[',
        '        Measure(start_joint.feature(MT.TENON_FRONT), start_joint.feature(MT.TENON_BACK), placement=Beside(DimensionSide.LEFT)),',
        '    ])',
        '    return Drawing(name=f"{cross.ticket.path} ×2", timbers=[cross],',
        '                   viewports=[covering_page(columns(rows(top, side).taking(Share(2)), Viewport(label="Preview")))])',
        '',
    ].join('\n');
}

function ensureExampleFrame(workspaceRoot) {
    const filePath = path.join(workspaceRoot, 'my_cute_frame.py');
    if (fs.existsSync(filePath)) {
        return { filePath, created: false };
    }

    const content = getBundledExampleFrameContent();

    fs.writeFileSync(filePath, content, 'utf8');
    return { filePath, created: true };
}

async function getMissingViewerDependencies(workspaceRoot, pythonPath) {
    // The initializer omits "kumiki" from the required list (it is installed
    // separately in installOrUpdateKumiki); see python-env.js.
    return getMissingDependencies(pythonPath, {
        cwd: workspaceRoot,
        required: ['sympy', 'numpy', 'trimesh', 'manifold3d'],
    });
}

async function getInstalledKumikiVersion(workspaceRoot, pythonPath) {
    const snippet = [
        'import importlib.metadata as m',
        'try:',
        '    print(m.version("kumiki"))',
        'except Exception:',
        '    print("unknown")',
    ].join('\n');

    const { stdout } = await runCommand(pythonPath, ['-c', snippet], workspaceRoot);
    return (stdout || '').trim() || 'unknown';
}

async function getLatestKumikiVersionFromPyPI() {
    return new Promise((resolve) => {
        const req = https.get('https://pypi.org/pypi/kumiki/json', (res) => {
            if (res.statusCode !== 200) {
                resolve('unknown');
                res.resume();
                return;
            }

            let data = '';
            res.on('data', (chunk) => {
                data += chunk.toString();
            });
            res.on('end', () => {
                try {
                    const payload = JSON.parse(data);
                    const version = payload && payload.info && payload.info.version;
                    resolve(version ? String(version) : 'unknown');
                } catch (_error) {
                    resolve('unknown');
                }
            });
        });

        req.on('error', () => resolve('unknown'));
        req.setTimeout(4000, () => {
            req.destroy();
            resolve('unknown');
        });
    });
}

async function getWorkspaceKumikiVersionInfo(workspaceRoot, filePath) {
    const env = resolveProjectEnvironment({
        workspaceRoot,
        filePath,
        createMarkerIfMissing: false,
    });
    const resolvedRoot = env.projectRoot || workspaceRoot;
    const pythonPath = getVenvPython(resolvedRoot);

    let installedVersion = 'unknown';
    if (isPythonAvailable(pythonPath)) {
        try {
            installedVersion = await getInstalledKumikiVersion(resolvedRoot, pythonPath);
        } catch (_error) {
            installedVersion = 'unknown';
        }
    }

    const latestVersion = await getLatestKumikiVersionFromPyPI();
    return {
        installedVersion,
        latestVersion,
    };
}

async function installOrUpdateKumiki(workspaceRoot, pythonPath, isLocalDev) {
    const missingBefore = await getMissingViewerDependencies(workspaceRoot, pythonPath);
    const summary = [];

    const pipSpec = kumikiCompatiblePipSpec(getKigumiVersion(), getKumikiMinimumVersion());
    if (isLocalDev && fs.existsSync(path.join(workspaceRoot, 'pyproject.toml'))) {
        await pipInstall(workspaceRoot, pythonPath, ['--upgrade', '-e', workspaceRoot]);
        summary.push('Installed local editable Kumiki package from workspace source.');
    } else {
        await pipInstall(workspaceRoot, pythonPath, ['--upgrade', pipSpec]);
        summary.push(`Installed/upgraded Kumiki from PyPI (${pipSpec}).`);
    }

    const missingAfter = await getMissingViewerDependencies(workspaceRoot, pythonPath);
    if (missingBefore.length > 0) {
        summary.push(`Missing viewer deps before install: ${missingBefore.join(', ')}`);
    } else {
        summary.push('No viewer dependencies were missing before install.');
    }
    if (missingAfter.length > 0) {
        summary.push(`Still missing after install: ${missingAfter.join(', ')}`);
        throw new Error(
            `Installation incomplete — the following required packages are still missing after install: ${missingAfter.join(', ')}. ` +
            `Check the Kigumi output channel for details.`
        );
    } else {
        summary.push('All required viewer dependencies are available after install.');
    }

    const kumikiVersion = await getInstalledKumikiVersion(workspaceRoot, pythonPath);
    summary.push(`Installed Kumiki version: ${kumikiVersion}`);

    const kigumiVersion = getKigumiVersion();
    const [kMajor, kMinor] = kigumiVersion.split('.').map(Number);
    if (isLocalDevKigumiVersion(kigumiVersion)) {
        summary.push(`Local dev kigumi build (${kigumiVersion}); skipping kumiki version compatibility check.`);
    } else if (kumikiVersion !== 'unknown') {
        const [iMajor, iMinor] = kumikiVersion.split('.').map(Number);
        if (iMajor !== kMajor || iMinor !== kMinor) {
            throw new Error(
                `kumiki version mismatch after install: installed ${kumikiVersion} but kigumi ${kigumiVersion} requires ${kMajor}.${kMinor}.x. ` +
                `This should not happen — please report it.`
            );
        }
    }

    return {
        installedViewerDeps: missingBefore.length > 0,
        missingBefore,
        missingAfter,
        kumikiVersion,
        summary,
    };
}

function getInitializationStatus(workspaceRoot, filePath) {
    const env = resolveProjectEnvironment({
        workspaceRoot,
        filePath,
        createMarkerIfMissing: false,
    });
    const resolvedRoot = env.projectRoot || workspaceRoot;
    const isLocalDev = !!env.isLocalDev;
    const hasKigumiYaml = fs.existsSync(path.join(resolvedRoot, KUMIKI_YAML_RELATIVE_PATH))
        || fs.existsSync(path.join(resolvedRoot, LEGACY_KIGUMI_YAML_NAME));
    const hasProjectYaml = fs.existsSync(path.join(resolvedRoot, '.kigumi', 'kigumi.yaml'));
    const hasVenvPython = isPythonAvailable(getVenvPython(resolvedRoot));
    const hasExampleFile = fs.existsSync(path.join(resolvedRoot, 'my_cute_frame.py'));
    const hasExistingProject = hasKigumiYaml || hasProjectYaml || hasVenvPython || hasExampleFile;

    let projectStatus = 'no-project';
    if (isLocalDev) {
        projectStatus = 'local-dev';
    } else if (hasExistingProject) {
        projectStatus = 'existing-project';
    }

    return {
        projectRoot: resolvedRoot,
        projectStatus,
        isLocalDev,
        hasExistingProject,
        hasKigumiYaml,
        hasProjectYaml,
        hasVenvPython,
        hasExampleFile,
        isInitialized: projectStatus === 'existing-project' && hasKigumiYaml && (managedEnvironment || hasProjectYaml) && hasVenvPython && hasExampleFile,
    };
}

let _initializationInProgress = false;

function isInitializationInProgress() {
    return _initializationInProgress;
}

async function initializeWorkspaceProject(workspaceRoot, filePath) {
    if (_initializationInProgress) {
        const err = new Error('Initialization is already in progress.');
        err.code = 'INITIALIZATION_IN_PROGRESS';
        throw err;
    }
    _initializationInProgress = true;
    try {
        const env = resolveProjectEnvironment({
            workspaceRoot,
            filePath,
            createMarkerIfMissing: true,
        });
        const resolvedRoot = env.projectRoot || workspaceRoot;

        ensureKigumiYaml(resolvedRoot);
        const envResult = await ensureProjectVenv(resolvedRoot);
        const installResult = await installOrUpdateKumiki(resolvedRoot, envResult.pythonPath, env.isLocalDev);

        writeProjectYaml(resolvedRoot, envResult.pythonPath, {
            createdVenv: envResult.createdVenv,
            installedViewerDeps: installResult.installedViewerDeps,
            missingBefore: installResult.missingBefore,
            isLocalDev: env.isLocalDev,
        });

        const exampleResult = ensureExampleFrame(resolvedRoot);
        const gitignoreResult = ensureGitignore(resolvedRoot);
        const instructionsResult = await ensureAgentInstructionFiles(
            resolvedRoot, envResult.pythonPath, installResult.kumikiVersion, { isLocalDev: env.isLocalDev });

        return {
            projectRoot: resolvedRoot,
            isLocalDev: env.isLocalDev,
            pythonPath: envResult.pythonPath,
            createdVenv: envResult.createdVenv,
            installedViewerDeps: installResult.installedViewerDeps,
            missingBefore: installResult.missingBefore,
            missingAfter: installResult.missingAfter,
            kumikiVersion: installResult.kumikiVersion,
            installSummary: installResult.summary,
            exampleFilePath: exampleResult.filePath,
            createdExampleFile: exampleResult.created,
            createdGitignoreFile: gitignoreResult.created,
            addedGitignoreEntries: gitignoreResult.addedEntries,
            ...instructionsResult,
        };
    } finally {
        _initializationInProgress = false;
    }
}

async function updateWorkspaceKumiki(workspaceRoot, filePath) {
    if (_initializationInProgress) {
        const err = new Error('Initialization is already in progress.');
        err.code = 'INITIALIZATION_IN_PROGRESS';
        throw err;
    }

    _initializationInProgress = true;
    try {
        const env = resolveProjectEnvironment({
            workspaceRoot,
            filePath,
            createMarkerIfMissing: true,
        });
        const resolvedRoot = env.projectRoot || workspaceRoot;

        ensureKigumiYaml(resolvedRoot);
        const envResult = await ensureProjectVenv(resolvedRoot);
        const installResult = await installOrUpdateKumiki(resolvedRoot, envResult.pythonPath, env.isLocalDev);

        writeProjectYaml(resolvedRoot, envResult.pythonPath, {
            createdVenv: envResult.createdVenv,
            installedViewerDeps: installResult.installedViewerDeps,
            missingBefore: installResult.missingBefore,
            isLocalDev: env.isLocalDev,
        });

        const instructionsResult = await ensureAgentInstructionFiles(
            resolvedRoot, envResult.pythonPath, installResult.kumikiVersion, { isLocalDev: env.isLocalDev });

        return {
            projectRoot: resolvedRoot,
            isLocalDev: env.isLocalDev,
            pythonPath: envResult.pythonPath,
            createdVenv: envResult.createdVenv,
            installedViewerDeps: installResult.installedViewerDeps,
            missingBefore: installResult.missingBefore,
            missingAfter: installResult.missingAfter,
            kumikiVersion: installResult.kumikiVersion,
            installSummary: installResult.summary,
            ...instructionsResult,
        };
    } finally {
        _initializationInProgress = false;
    }
}

module.exports = {
    getInlineExampleFrameContent,
    getInitializationStatus,
    initializeWorkspaceProject,
    updateWorkspaceKumiki,
    isInitializationInProgress,
    getWorkspaceKumikiVersionInfo,
};
