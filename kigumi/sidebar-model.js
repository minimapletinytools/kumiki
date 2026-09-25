/**
 * The Kigumi explorer's state and tree, as plain data. Host-neutral: the VS
 * Code webview view and the standalone app both render getTree().
 *
 * A node is { key, type, label, description?, tooltip?, icon, spin?,
 * expanded? (containers only), children?, action?, rowActions?, data? }.
 * `action` is the command run on click; `rowActions` lists the row's extra
 * actions from ROW_ACTIONS.
 */

const path = require('path');
const { scanWorkspaceForFrames } = require('./frame-scanner');
const { discoverDependencyContent } = require('./discovery-adapter');
const { getInitializationStatus, isInitializationInProgress } = require('./project-initializer');
const { groupPatternsByPatternbook } = require('./pattern-source-utils');
const { createTranslator } = require('./i18n');
const { getHost } = require('./host');

const t = (key, params) => createTranslator(getHost().locale)(key, params);

// Extra row actions: `inline` ones also show as buttons on the row.
const ROW_ACTIONS = Object.freeze({
    viewSource: { command: 'kigumi.viewPatternSource', icon: 'go-to-file', labelKey: 'sidebar.action.viewSource', inline: true },
    duplicate: { command: 'kigumi.duplicatePatternToWorkspace', icon: 'copy', labelKey: 'sidebar.action.duplicate', inline: true },
    openInNewWindow: { command: 'kigumi.openPatternInNewWindow', icon: 'link-external', labelKey: 'sidebar.action.openInNewWindow', inline: false },
});

const LIBRARY_SECTIONS = new Set(['shipped-patterns', 'dependency-patterns']);

function emptyState(overrides = {}) {
    return {
        workspaceRoot: null,
        initStatus: null,
        kumikiInstalledVersion: 'unknown',
        kumikiLatestVersion: 'unknown',
        frames: [],
        workspacePatternbooks: [],
        shippedPatterns: [],
        dependencyPatterns: [],
        shippedExamples: [],
        dependencyExamples: [],
        scanErrors: [],
        discoveryErrors: [],
        isScanning: false,
        ...overrides,
    };
}

function node(fields) {
    return { data: {}, ...fields };
}

function open(command, ...args) {
    return { command, arguments: args };
}

function patternRowActions(sectionKey) {
    return LIBRARY_SECTIONS.has(sectionKey)
        ? ['viewSource', 'duplicate', 'openInNewWindow']
        : ['viewSource', 'openInNewWindow'];
}

function byLabelThenDescription(a, b) {
    return `${a.label}:${a.description}`.localeCompare(`${b.label}:${b.description}`);
}

class SidebarModel {
    /**
     * @param {object} [options]
     * @param {() => string|undefined} [options.getPythonCommand]
     * @param {(workspaceRoot: string) => Promise<{installedVersion, latestVersion}>} [options.getKumikiVersionInfo]
     * @param {(line: string) => void} [options.logLine]
     */
    constructor(options = {}) {
        this.options = options;
        this._listeners = new Set();
        this._didLoadOnce = false;
        this._scanPromise = null;
        this._groupByPatternbook = true;
        this._state = emptyState();
    }

    onDidChange(listener) {
        this._listeners.add(listener);
        return { dispose: () => this._listeners.delete(listener) };
    }

    _fire() {
        for (const listener of [...this._listeners]) {
            listener();
        }
    }

    dispose() {
        this._listeners.clear();
    }

    get state() {
        return this._state;
    }

    getGroupByPatternbook() {
        return this._groupByPatternbook;
    }

    toggleGroupByPatternbook() {
        this._groupByPatternbook = !this._groupByPatternbook;
        this._fire();
    }

    ensureLoaded() {
        if (this._didLoadOnce) {
            return;
        }
        this._didLoadOnce = true;
        void this.refresh(false);
    }

    async refresh(forceRescan = true) {
        if (this._scanPromise && !forceRescan) {
            return this._scanPromise;
        }
        this._scanPromise = this._runFullScan()
            .finally(() => {
                this._scanPromise = null;
            });
        return this._scanPromise;
    }

    async getTestSnapshot(options = {}) {
        if (options.forceRefresh !== false) {
            await this.refresh(true);
        }
        const roots = this.getTree();
        return {
            groupByPatternbook: this._groupByPatternbook,
            state: {
                workspaceRoot: this._state.workspaceRoot,
                frameCount: this._state.frames.length,
                workspacePatternbookCount: this._state.workspacePatternbooks.length,
                shippedPatternCount: this._state.shippedPatterns.length,
                dependencyPatternCount: this._state.dependencyPatterns.length,
                isScanning: this._state.isScanning,
                scanErrorCount: this._state.scanErrors.length,
                discoveryErrorCount: this._state.discoveryErrors.length,
            },
            roots: roots.map((root) => {
                const children = root.children || [];
                return {
                    key: root.key,
                    type: root.type,
                    label: root.label,
                    description: root.description || '',
                    childCount: children.length,
                    childLabels: children.slice(0, 20).map((child) => child.label),
                };
            }),
        };
    }

    async _runFullScan() {
        const workspaceRoot = getHost().workspaceRoots()[0] || null;
        if (!workspaceRoot) {
            this._state = emptyState({
                discoveryErrors: ['Open a workspace folder to use Kigumi Explorer.'],
            });
            this._fire();
            return;
        }

        const initStatus = getInitializationStatus(workspaceRoot);
        const isLocalDev = initStatus.projectStatus === 'local-dev';
        if (!isLocalDev && !initStatus.isInitialized) {
            this._state = emptyState({ workspaceRoot, initStatus });
            this._fire();
            return;
        }

        const versionInfoPromise = this.options.getKumikiVersionInfo
            ? this.options.getKumikiVersionInfo(workspaceRoot)
            : Promise.resolve({ installedVersion: 'unknown', latestVersion: 'unknown' });
        const timeoutSeconds = getHost().getConfig('explorer.scanTimeoutSeconds', 15);
        const timeoutMs = Math.max(1000, Number(timeoutSeconds) * 1000);

        this._state = { ...this._state, workspaceRoot, initStatus, isScanning: true };
        this._fire();

        const [workspaceResult, shippedResult] = await Promise.allSettled([
            this._scanWorkspace(workspaceRoot, timeoutMs),
            isLocalDev ? Promise.resolve(null) : this._scanShipped(workspaceRoot, timeoutMs),
        ]);

        const scanErrors = [];
        let frames = [];
        let workspacePatternbooks = [];
        if (workspaceResult.status === 'fulfilled') {
            frames = workspaceResult.value.frames;
            workspacePatternbooks = workspaceResult.value.patternbooks;
            scanErrors.push(...workspaceResult.value.scanErrors);
        } else {
            scanErrors.push({ filePath: workspaceRoot, reason: `Workspace scan failed: ${workspaceResult.reason?.message || workspaceResult.reason}` });
        }

        const discoveryErrors = [];
        let shipped = { shippedPatterns: [], dependencyPatterns: [], shippedExamples: [], dependencyExamples: [] };
        if (shippedResult && shippedResult.status === 'fulfilled' && shippedResult.value) {
            shipped = shippedResult.value;
        } else if (shippedResult && shippedResult.status === 'rejected') {
            discoveryErrors.push(`Dependency discovery failed: ${shippedResult.reason?.message || shippedResult.reason}`);
        }

        let kumikiInstalledVersion = 'unknown';
        let kumikiLatestVersion = 'unknown';
        try {
            const payload = await versionInfoPromise;
            kumikiInstalledVersion = (payload && payload.installedVersion) || 'unknown';
            kumikiLatestVersion = (payload && payload.latestVersion) || 'unknown';
        } catch (_error) {
            // Stays 'unknown'.
        }

        this._state = {
            workspaceRoot,
            initStatus,
            kumikiInstalledVersion,
            kumikiLatestVersion,
            frames,
            workspacePatternbooks,
            ...shipped,
            scanErrors,
            discoveryErrors,
            isScanning: false,
        };
        this._logScanIssues();
        this._fire();
    }

    _logScanIssues() {
        const logLine = this.options.logLine;
        const { discoveryErrors, scanErrors } = this._state;
        if (typeof logLine !== 'function' || (discoveryErrors.length === 0 && scanErrors.length === 0)) {
            return;
        }
        logLine('[explorer] Scan issues detected:');
        for (const message of discoveryErrors) {
            logLine(`[explorer] discovery error: ${message}`);
        }
        for (const err of scanErrors) {
            logLine(`[explorer] scan error: ${err && err.reason ? err.reason : String(err)}`);
            logLine(`[explorer] scan error file: ${err && err.filePath ? err.filePath : '<unknown>'}`);
        }
    }

    async _scanWorkspace(workspaceRoot, timeoutMs) {
        const result = await scanWorkspaceForFrames(workspaceRoot, {
            timeoutMs,
            pythonCommand: this.options.getPythonCommand?.(),
            logLine: this.options.logLine,
            showPoopTaggedJoints: getHost().getConfig('viewer.showPoopTaggedJoints', false),
        });
        return {
            frames: result.frameFiles || [],
            patternbooks: result.patternbookFiles || [],
            scanErrors: result.scanErrors || [],
        };
    }

    async _scanShipped(workspaceRoot, timeoutMs) {
        const dep = await discoverDependencyContent(workspaceRoot, {
            timeoutMs,
            pythonCommand: this.options.getPythonCommand?.(),
        });

        const toItem = (filePath) => ({
            sourceFile: filePath,
            name: path.basename(filePath, '.py'),
            groups: [],
        });

        const expandPatternbookRecords = (records, fallbackPaths) => {
            const normalizedRecords = Array.isArray(records)
                ? records
                : (fallbackPaths || []).map((filePath) => ({
                    sourceFile: filePath,
                    patternbookName: path.basename(filePath, '.py'),
                    patternNames: [path.basename(filePath, '.py')],
                    groupNames: [],
                }));

            const items = [];
            for (const rec of normalizedRecords) {
                const sourceFile = rec && rec.sourceFile;
                if (!sourceFile) {
                    continue;
                }
                const patternbookName = rec.patternbookName || path.basename(sourceFile, '.py');
                const names = Array.isArray(rec.patternNames) && rec.patternNames.length > 0
                    ? rec.patternNames
                    : [patternbookName];
                const uniqueNames = Array.from(new Set(names)).sort((a, b) => a.localeCompare(b));
                for (const name of uniqueNames) {
                    items.push({
                        sourceFile,
                        name,
                        patternbookName,
                        groups: Array.isArray(rec.groupNames) ? rec.groupNames : [],
                        patternNames: uniqueNames,
                    });
                }
            }
            items.sort((a, b) => `${a.patternbookName}:${a.name}`.localeCompare(`${b.patternbookName}:${b.name}`));
            return items;
        };

        return {
            shippedPatterns: expandPatternbookRecords(dep.kumikiPatternbooks, dep.kumikiPatterns),
            shippedExamples: (dep.kumikiExamples || []).map(toItem),
            dependencyPatterns: expandPatternbookRecords(dep.dependencyPatternbooks, dep.dependencyPatterns),
            dependencyExamples: (dep.dependencyExamples || []).map(toItem),
        };
    }

    // -------------------------------------------------------------------------
    // Tree
    // -------------------------------------------------------------------------

    getTree() {
        const nodes = [...this._statusNodes()];
        const state = this._state;

        nodes.push(node({
            key: 'frames-root',
            type: 'framesRoot',
            label: state.isScanning ? t('sidebar.framesScanning') : t('sidebar.frames', { count: state.frames.length }),
            icon: state.isScanning ? 'loading' : 'home',
            spin: state.isScanning,
            expanded: true,
            children: this._workspaceFrameNodes(),
        }));

        if (state.shippedExamples.length + state.dependencyExamples.length > 0) {
            nodes.push(node({
                key: 'example-frames-root',
                type: 'exampleFramesRoot',
                label: t('sidebar.exampleFrames'),
                icon: 'symbol-folder',
                expanded: false,
                children: this._libraryFrameNodes(),
            }));
        }

        nodes.push(node({
            key: 'patterns-root',
            type: 'patternsRoot',
            label: state.isScanning ? t('sidebar.patternsScanning') : t('sidebar.patterns'),
            icon: state.isScanning ? 'loading' : 'book',
            spin: state.isScanning,
            expanded: true,
            children: this._patternSectionNodes(),
        }));

        const totalErrors = state.discoveryErrors.length + state.scanErrors.length;
        if (totalErrors > 0) {
            nodes.push(node({
                key: 'errors-root',
                type: 'errorsRoot',
                label: t('sidebar.scanIssues', { count: totalErrors }),
                icon: 'warning',
                expanded: false,
                children: this._errorNodes(),
            }));
        }

        return nodes;
    }

    // The project status, kumiki version and website rows.
    _statusNodes() {
        const nodes = [];
        const { initStatus } = this._state;
        const isLocalDev = !!(initStatus && initStatus.projectStatus === 'local-dev');
        const hasProject = !!(initStatus && (initStatus.hasExistingProject || initStatus.isInitialized));

        if (isLocalDev) {
            nodes.push(node({
                key: 'project-status-local-dev',
                type: 'projectStatusAction',
                label: t('sidebar.kumikiDevMode'),
                description: t('sidebar.kumikiDevMode.desc'),
                icon: 'beaker',
                action: open('kigumi.initializeProjectInWorkspace'),
            }));
        } else if (isInitializationInProgress()) {
            nodes.push(node({
                key: 'project-status-initializing',
                type: 'projectStatusAction',
                label: t('sidebar.initializingProject'),
                description: t('sidebar.initializingProject.desc'),
                icon: 'loading',
                spin: true,
            }));
        } else if (!hasProject) {
            nodes.push(node({
                key: 'project-status-initialize',
                type: 'projectStatusAction',
                label: t('sidebar.initializeProjectAction'),
                description: t('sidebar.initializeProjectAction.desc'),
                icon: 'rocket',
                action: open('kigumi.initializeProjectInWorkspace'),
            }));
        } else {
            nodes.push(node({
                key: 'project-status-initialized',
                type: 'projectStatusAction',
                label: t('sidebar.projectInitialized'),
                description: initStatus.projectRoot ? path.basename(initStatus.projectRoot) : t('sidebar.currentWorkspace'),
                icon: 'pass',
                action: open('kigumi.initializeProjectInWorkspace'),
            }));
        }

        if (initStatus && initStatus.isInitialized) {
            const installed = this._state.kumikiInstalledVersion || 'unknown';
            const latest = this._state.kumikiLatestVersion || 'unknown';
            if (installed !== 'unknown' && installed === latest) {
                nodes.push(node({
                    key: 'kumiki-version-up-to-date',
                    type: 'kumikiVersionAction',
                    label: t('sidebar.kumikiUpToDate', { version: installed }),
                    description: t('sidebar.kumikiUpToDate.desc'),
                    icon: 'verified-filled',
                }));
            } else {
                nodes.push(node({
                    key: 'kumiki-version-update',
                    type: 'kumikiVersionAction',
                    label: t('sidebar.updateKumikiAction', { installed, latest }),
                    description: t('sidebar.updateKumikiAction.desc'),
                    icon: 'cloud-download',
                    action: open('kigumi.updateKumiki'),
                }));
            }
        }

        nodes.push(node({
            key: 'kumiki-website-action',
            type: 'kumikiWebsiteAction',
            label: t('sidebar.goToWebsiteAction'),
            description: 'github.com/minimapletinytools/kumiki',
            icon: 'link-external',
            action: open('kigumi.openWebsite'),
        }));

        return nodes;
    }

    _placeholder(key, label, description) {
        return node({ key, type: 'placeholder', label, description, icon: 'circle-slash' });
    }

    _frameNode(key, label, filePath, data) {
        return node({
            key,
            type: 'frameFile',
            label,
            icon: 'file-code',
            action: open('kigumi.openFrameFromSidebar', filePath),
            rowActions: ['viewSource'],
            data,
        });
    }

    _workspaceFrameNodes() {
        const nodes = [];
        if (this._state.isScanning) {
            nodes.push(node({ key: 'frames-scanning', type: 'loading', label: t('sidebar.scanningWorkspace'), icon: 'loading', spin: true }));
        }
        const frames = this._state.frames;
        if (frames.length === 0) {
            nodes.push(this._placeholder(
                'frames-empty',
                t('sidebar.noFrameDefinitionsFound'),
                this._state.workspaceRoot ? '' : t('sidebar.openAWorkspace'),
            ));
            return nodes;
        }
        nodes.push(...frames.map((frameFile) => this._frameNode(
            `frame-file:workspace:${frameFile.filePath}`,
            frameFile.relativePath,
            frameFile.filePath,
            frameFile,
        )));
        return nodes;
    }

    _libraryFrameNodes() {
        const nodes = [];
        const libraryGroup = (key, label, icon, items) => node({
            key,
            type: 'libraryFrameGroup',
            label,
            icon,
            expanded: false,
            children: items.map((item) => this._frameNode(`frame-file:library:${item.sourceFile}`, item.name, item.sourceFile, item)),
            data: { items },
        });

        if (this._state.shippedExamples.length > 0) {
            nodes.push(libraryGroup('library-frames:kumiki', t('sidebar.kumiki'), 'package', this._state.shippedExamples));
        }

        const depsByLib = {};
        for (const item of this._state.dependencyExamples) {
            const libName = item.name || path.basename(item.sourceFile, '.py');
            (depsByLib[libName] = depsByLib[libName] || []).push(item);
        }
        for (const libName of Object.keys(depsByLib).sort()) {
            nodes.push(libraryGroup(`library-frames:dep:${libName}`, libName, 'extensions', depsByLib[libName]));
        }
        return nodes;
    }

    _patternSectionNodes() {
        const nodes = [];
        const state = this._state;
        if (state.isScanning) {
            nodes.push(node({
                key: 'patterns-scanning',
                type: 'loading',
                label: t('sidebar.scanning'),
                description: t('sidebar.scanningDesc'),
                icon: 'loading',
                spin: true,
            }));
        }

        const section = (sectionKey, label, icon, expanded) => node({
            key: `pattern-section:${sectionKey}`,
            type: 'patternSection',
            label,
            icon,
            expanded,
            children: this._patternNodesForSection(sectionKey),
            data: { sectionKey },
        });

        nodes.push(section('workspace-patternbooks', t('sidebar.workspace', { count: state.workspacePatternbooks.length }), 'folder-opened', true));
        if (state.shippedPatterns.length > 0 || state.shippedExamples.length > 0) {
            nodes.push(section('shipped-patterns', t('sidebar.kumikiCount', { count: state.shippedPatterns.length }), 'package', false));
        }
        if (state.dependencyPatterns.length > 0 || state.dependencyExamples.length > 0) {
            nodes.push(section('dependency-patterns', t('sidebar.dependencies', { count: state.dependencyPatterns.length }), 'extensions', false));
        }
        return nodes;
    }

    _patternNodesForSection(sectionKey) {
        if (sectionKey === 'workspace-patternbooks') {
            return this._groupByPatternbook ? this._workspacePatternTree() : this._flatWorkspacePatternNodes();
        }
        const items = sectionKey === 'shipped-patterns' ? this._state.shippedPatterns : this._state.dependencyPatterns;
        return this._libraryPatternNodes(sectionKey, items, this._groupByPatternbook);
    }

    _patternNode({ key, label, description, tooltip, sourceFile, patternName, sectionKey }) {
        return node({
            key,
            type: 'patternItem',
            label,
            description,
            tooltip,
            icon: 'library',
            action: open('kigumi.openPatternFromSidebar', { sourceFile, patternName }),
            rowActions: patternRowActions(sectionKey),
            data: { sourceFile, patternName, sectionKey },
        });
    }

    _allWorkspacePatterns() {
        const all = [];
        for (const pb of this._state.workspacePatternbooks) {
            for (const p of (Array.isArray(pb.patterns) ? pb.patterns : [])) {
                all.push({ path: p.path, tags: p.tags, sourceFile: pb.filePath });
            }
        }
        return all;
    }

    _workspacePatternTree() {
        const nodes = this._patternFolderNodes(this._allWorkspacePatterns(), null);
        if (nodes.length === 0) {
            return [this._placeholder('workspace-patternbooks-empty', t('sidebar.noPatternsFound'), t('sidebar.noPatternsFoundHint'))];
        }
        return nodes;
    }

    // Pattern paths ("a/b/c") as nested folders under `parentPath`.
    _patternFolderNodes(allPatterns, parentPath) {
        const prefix = parentPath ? `${parentPath}/` : '';
        const childSegments = new Set();
        for (const p of allPatterns) {
            if (!p.path.startsWith(prefix)) continue;
            const firstSeg = p.path.slice(prefix.length).split('/')[0];
            if (firstSeg) childSegments.add(firstSeg);
        }

        const nodes = [];
        for (const seg of [...childSegments].sort()) {
            const childPath = prefix + seg;
            const patternAtPath = allPatterns.find((p) => p.path === childPath);
            const hasChildren = allPatterns.some((p) => p.path.startsWith(`${childPath}/`));

            if (hasChildren) {
                const isMain = !!(patternAtPath && Array.isArray(patternAtPath.tags) && patternAtPath.tags.includes('main'));
                const sourceFile = patternAtPath ? patternAtPath.sourceFile : null;
                nodes.push(node({
                    key: `workspace-pattern-folder:${childPath}`,
                    type: 'workspacePatternFolder',
                    label: seg,
                    description: isMain ? t('sidebar.mainBadge') : undefined,
                    tooltip: childPath,
                    icon: isMain ? 'folder-library' : 'folder',
                    expanded: false,
                    action: isMain ? open('kigumi.openPatternFromSidebar', { sourceFile, patternName: childPath }) : undefined,
                    rowActions: isMain ? ['viewSource'] : undefined,
                    children: this._patternFolderNodes(allPatterns, childPath),
                    data: { pathPrefix: childPath, sourceFile },
                }));
            } else if (patternAtPath) {
                nodes.push(this._patternNode({
                    key: `workspace-pattern:${patternAtPath.sourceFile}:${childPath}`,
                    label: seg,
                    tooltip: `${childPath} — ${patternAtPath.sourceFile}`,
                    sourceFile: patternAtPath.sourceFile,
                    patternName: childPath,
                    sectionKey: 'workspace-patternbooks',
                }));
            }
        }
        return nodes;
    }

    _flatWorkspacePatternNodes() {
        const nodes = [];
        for (const pb of this._state.workspacePatternbooks) {
            for (const p of (Array.isArray(pb.patterns) ? pb.patterns : [])) {
                const segments = (p.path || '').split('/');
                nodes.push(this._patternNode({
                    key: `workspace-pattern-flat:${pb.filePath}:${p.path}`,
                    label: segments[segments.length - 1] || p.path || '',
                    description: pb.patternbookName,
                    tooltip: `${p.path} — ${pb.filePath}`,
                    sourceFile: pb.filePath,
                    patternName: p.path,
                    sectionKey: 'workspace-patternbooks',
                }));
            }
        }
        if (nodes.length === 0) {
            return [this._placeholder('workspace-patterns-empty', t('sidebar.noPatternsFound'))];
        }
        return nodes.sort(byLabelThenDescription);
    }

    _libraryPatternNodes(sectionKey, patternItems, grouped) {
        if (!patternItems || patternItems.length === 0) {
            return [this._placeholder(`patterns-empty:${sectionKey}`, t('sidebar.noPatternsFound'))];
        }

        const itemNode = (item, key, description) => this._patternNode({
            key,
            label: item.name || path.basename(item.sourceFile, '.py'),
            description,
            tooltip: item.sourceFile,
            sourceFile: item.sourceFile,
            patternName: item.name || null,
            sectionKey,
        });

        if (!grouped) {
            return patternItems
                .map((item) => itemNode(
                    item,
                    `pattern-item-flat:${sectionKey}:${item.sourceFile}:${item.name || path.basename(item.sourceFile, '.py')}`,
                    path.basename(item.sourceFile, '.py'),
                ))
                .sort(byLabelThenDescription);
        }

        const nodes = [];
        for (const [patternbookName, items] of groupPatternsByPatternbook(patternItems).entries()) {
            const groupData = { sectionKey, patternbookName, patterns: items };
            nodes.push(node({
                key: `patternbook-group:${sectionKey}:${patternbookName}`,
                type: 'patternbookGroup',
                label: patternbookName,
                description: items.length === 1
                    ? t('sidebar.patternCount.singular', { count: items.length })
                    : t('sidebar.patternCount.plural', { count: items.length }),
                icon: 'folder',
                expanded: false,
                action: open('kigumi.openPatternbookGroup', groupData),
                rowActions: ['viewSource', 'duplicate'],
                children: items.map((item) => itemNode(
                    item,
                    `pattern-item:${sectionKey}:${item.sourceFile}:${item.name || path.basename(item.sourceFile, '.py')}`,
                )),
                data: groupData,
            }));
        }
        return nodes;
    }

    _errorNodes() {
        const rows = this._state.discoveryErrors.map((message) => node({
            key: `discovery-error:${message}`,
            type: 'error',
            label: message,
            icon: 'error',
        }));
        for (const err of this._state.scanErrors) {
            rows.push(node({
                key: `scan-error:${err.filePath || ''}`,
                type: 'error',
                label: err.reason,
                description: path.basename(err.filePath || ''),
                tooltip: `${err.reason}\n${err.filePath}`,
                icon: 'warning',
            }));
        }
        return rows;
    }
}

module.exports = { SidebarModel, ROW_ACTIONS };
