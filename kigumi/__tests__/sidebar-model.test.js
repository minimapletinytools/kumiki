jest.mock('../frame-scanner', () => ({
  scanWorkspaceForFrames: jest.fn(),
}));
jest.mock('../discovery-adapter', () => ({
  discoverDependencyContent: jest.fn(),
}));
jest.mock('../project-initializer', () => ({
  getInitializationStatus: jest.fn(),
  isInitializationInProgress: jest.fn(),
}));

const { scanWorkspaceForFrames } = require('../frame-scanner');
const { discoverDependencyContent } = require('../discovery-adapter');
const { getInitializationStatus, isInitializationInProgress } = require('../project-initializer');
const fs = require('fs');
const os = require('os');
const path = require('path');
const { setHost } = require('../host');
const { SidebarModel, ROW_ACTIONS } = require('../sidebar-model');

let workspaceRoots;

function findNode(nodes, predicate) {
  for (const node of nodes) {
    if (predicate(node)) return node;
    const found = node.children && findNode(node.children, predicate);
    if (found) return found;
  }
  return null;
}

function rootOf(model, type) {
  return model.getTree().find((node) => node.type === type);
}

beforeEach(() => {
  jest.clearAllMocks();
  workspaceRoots = ['/test/workspace'];
  setHost({
    locale: 'en',
    workspaceRoots: () => workspaceRoots,
    getConfig: (_key, fallback) => fallback,
  });
  getInitializationStatus.mockReturnValue({ projectStatus: 'existing-project', isInitialized: true, hasExistingProject: true });
  isInitializationInProgress.mockReturnValue(false);
  scanWorkspaceForFrames.mockResolvedValue({ frameFiles: [], patternbookFiles: [], scanErrors: [] });
  discoverDependencyContent.mockResolvedValue({
    kumikiPatterns: [], kumikiExamples: [], dependencyPatterns: [], dependencyExamples: [],
  });
});

describe('scanning', () => {
  test('with no workspace it says to open one and lists nothing', async () => {
    workspaceRoots = [];
    const model = new SidebarModel();
    await model.refresh(true);

    expect(model.state.workspaceRoot).toBeNull();
    expect(model.state.discoveryErrors).toContain('Open a workspace folder to use Kigumi Explorer.');
    expect(rootOf(model, 'errorsRoot')).toBeDefined();
  });

  test('isScanning is set while the scan runs and cleared after', async () => {
    const model = new SidebarModel();
    const scan = model.refresh(true);
    expect(model.state.isScanning).toBe(true);
    await scan;
    expect(model.state.isScanning).toBe(false);
  });

  test('listeners hear about the scan starting and finishing', async () => {
    const model = new SidebarModel();
    const listener = jest.fn();
    model.onDidChange(listener);
    await model.refresh(true);
    expect(listener).toHaveBeenCalledTimes(2);
  });

  test('ensureLoaded scans once', () => {
    const model = new SidebarModel();
    model.ensureLoaded();
    model.ensureLoaded();
    expect(scanWorkspaceForFrames).toHaveBeenCalledTimes(1);
  });

  test("refreshWorkspace rescans the workspace's files only, keeping the shipped patterns", async () => {
    discoverDependencyContent.mockResolvedValue({
      kumikiPatterns: [{ name: 'shipped one' }], kumikiExamples: [], dependencyPatterns: [], dependencyExamples: [],
    });
    const model = new SidebarModel();
    await model.refresh(true);
    const shipped = model.state.shippedPatterns;
    expect(discoverDependencyContent).toHaveBeenCalledTimes(1);

    scanWorkspaceForFrames.mockResolvedValue({ scanErrors: [], patternbookFiles: [],
      frameFiles: [{ filePath: '/ws/box.py', relativePath: 'box.py', chosenFrameName: 'box', allFrameNames: ['box'] }] });
    await model.refreshWorkspace();

    expect(scanWorkspaceForFrames).toHaveBeenCalledTimes(2);
    expect(discoverDependencyContent).toHaveBeenCalledTimes(1);
    expect(model.state.shippedPatterns).toBe(shipped);
    expect(model.listsFile('/ws/box.py')).toBe(true);
    expect(model.listsFile('/ws/other.py')).toBe(false);
    expect(model.state.isScanning).toBe(false);
  });

  test('refreshWorkspace before any scan does a full one', async () => {
    const model = new SidebarModel();
    await model.refreshWorkspace();
    expect(scanWorkspaceForFrames).toHaveBeenCalledTimes(1);
    expect(discoverDependencyContent).toHaveBeenCalledTimes(1);
  });

  test('an uninitialized project is not scanned', async () => {
    getInitializationStatus.mockReturnValue({ projectStatus: 'no-project', isInitialized: false, hasExistingProject: false });
    const model = new SidebarModel();
    await model.refresh(true);

    expect(scanWorkspaceForFrames).not.toHaveBeenCalled();
    expect(discoverDependencyContent).not.toHaveBeenCalled();
    expect(model.getTree().some((node) => node.type === 'kumikiVersionAction')).toBe(false);
  });

  test('discovered patternbooks expand into one item per pattern name', async () => {
    discoverDependencyContent.mockResolvedValue({
      kumikiPatternbooks: [{
        sourceFile: '/deps/kumiki/patterns/basic.py',
        patternbookName: 'basic',
        patternNames: ['half_lap', 'bridle_joint'],
        groupNames: [],
      }],
      kumikiExamples: [],
      dependencyPatternbooks: [],
      dependencyExamples: [],
    });
    const model = new SidebarModel();
    await model.refresh(true);

    expect(model.state.shippedPatterns.map((p) => p.name)).toEqual(['bridle_joint', 'half_lap']);
  });
});

describe('status rows', () => {
  test('when the newest kumiki can\'t be looked up, it says what is installed, with no update to offer', async () => {
    const model = new SidebarModel();
    await model.refresh(true);
    model._state.kumikiInstalledVersion = '0.9.0';
    model._state.kumikiLatestVersion = 'unknown';
    const row = model.getTree().find((node) => node.type === 'kumikiVersionAction');
    expect(row.key).toBe('kumiki-version-installed');
    expect(row.label).toBe('Kumiki v0.9.0');
    expect(row.action).toBeUndefined();
  });

  test('Close Project shows only where the host can close a project (not VS Code), and one is open', async () => {
    const closeRow = async () => {
      const model = new SidebarModel();
      await model.refresh(true);
      return model.getTree().find((node) => node.type === 'closeProjectAction');
    };
    expect(await closeRow()).toBeUndefined();

    setHost({ locale: 'en', workspaceRoots: () => workspaceRoots, getConfig: (_key, fallback) => fallback, closeProject: async () => {} });
    expect((await closeRow()).action).toEqual({ command: 'kigumi.closeProject', arguments: [] });
    workspaceRoots = [];
    expect(await closeRow()).toBeUndefined();
  });

  test('with no project open, Open Project and the recent ones take the place of Initialize Project', async () => {
    workspaceRoots = [];
    setHost({
      locale: 'en', workspaceRoots: () => workspaceRoots, getConfig: (_key, fallback) => fallback,
      projects: { open: async () => {}, recent: () => [1, 2, 3, 4, 5, 6].map((n) => ({ id: `p${n}`, label: `Project ${n}` })) },
    });
    const model = new SidebarModel();
    await model.refresh(true);
    const tree = model.getTree();
    expect(tree.find((row) => row.type === 'projectStatusAction')).toBeUndefined();
    const rows = tree.filter((row) => row.type === 'openProjectAction');
    expect(rows[0].action).toEqual({ command: 'kigumi.openProject', arguments: [] });
    expect(rows.slice(1).map((row) => row.label)).toEqual(['Project 1', 'Project 2', 'Project 3', 'Project 4', 'Project 5']);
    expect(rows[1].action).toEqual({ command: 'kigumi.openRecentProject', arguments: ['p1'] });
    expect(tree.some((row) => row.type === 'kumikiWebsiteAction')).toBe(true);
  });

  test('with a project open, there is no Open Project row', async () => {
    setHost({ locale: 'en', workspaceRoots: () => workspaceRoots, getConfig: (_key, fallback) => fallback, projects: { open: async () => {} } });
    const model = new SidebarModel();
    await model.refresh(true);
    expect(model.getTree().find((row) => row.type === 'openProjectAction')).toBeUndefined();
  });

  test('an initialized project shows its status and runs the project action', async () => {
    const model = new SidebarModel();
    await model.refresh(true);
    const status = model.getTree().filter((node) => node.type === 'projectStatusAction');

    expect(status).toHaveLength(1);
    expect(status[0].key).toBe('project-status-initialized');
    expect(status[0].action).toEqual({ command: 'kigumi.initializeProjectInWorkspace', arguments: [] });
  });

  test('initializing replaces the initialize action', async () => {
    getInitializationStatus.mockReturnValue({ projectStatus: 'no-project', isInitialized: false, hasExistingProject: false });
    isInitializationInProgress.mockReturnValue(true);
    const model = new SidebarModel();
    await model.refresh(true);
    const labels = model.getTree().map((node) => node.label);

    expect(labels).toContain('Initializing project...');
    expect(labels).not.toContain('Initialize Project');
  });

  test('an out-of-date kumiki offers the update', async () => {
    const model = new SidebarModel({
      getKumikiVersionInfo: async () => ({ installedVersion: '0.8.0', latestVersion: '0.8.1' }),
    });
    await model.refresh(true);
    const version = rootOf(model, 'kumikiVersionAction');

    expect(version.key).toBe('kumiki-version-update');
    expect(version.action.command).toBe('kigumi.updateKumiki');
  });
});

describe('tree', () => {
  function withWorkspacePatterns(model, patterns) {
    model._state.workspacePatternbooks = [{ filePath: '/ws/book.py', patternbookName: 'book', patterns }];
  }

  test('workspace patterns nest by path, and a main-tagged folder opens its pattern', () => {
    const model = new SidebarModel();
    withWorkspacePatterns(model, [
      { path: 'shed', tags: ['main'] },
      { path: 'shed/wall', tags: [] },
      { path: 'stool', tags: [] },
    ]);
    const workspace = findNode(model.getTree(), (node) => node.key === 'pattern-section:workspace-patternbooks');
    const [shed, stool] = workspace.children;

    expect(shed.type).toBe('workspacePatternFolder');
    expect(shed.action).toEqual({ command: 'kigumi.openPatternFromSidebar', arguments: [{ sourceFile: '/ws/book.py', patternName: 'shed' }] });
    expect(shed.children.map((child) => child.label)).toEqual(['wall']);
    expect(stool.action.arguments).toEqual([{ sourceFile: '/ws/book.py', patternName: 'stool' }]);
  });

  test('ungrouped, workspace patterns are a flat sorted list', () => {
    const model = new SidebarModel();
    withWorkspacePatterns(model, [{ path: 'b/z', tags: [] }, { path: 'a', tags: [] }]);
    model.toggleGroupByPatternbook();
    const workspace = findNode(model.getTree(), (node) => node.key === 'pattern-section:workspace-patternbooks');

    expect(workspace.children.map((child) => child.label)).toEqual(['a', 'z']);
  });

  test('a library patternbook group opens the whole book', () => {
    const model = new SidebarModel();
    model._state.shippedPatterns = [{ sourceFile: '/deps/book.py', name: 'a', patternbookName: 'book' }];
    const group = findNode(model.getTree(), (node) => node.type === 'patternbookGroup');

    expect(group.action.command).toBe('kigumi.openPatternbookGroup');
    expect(group.children.map((child) => child.label)).toEqual(['a']);
  });

  test('keys are unique across the tree', async () => {
    const model = new SidebarModel();
    withWorkspacePatterns(model, [{ path: 'a', tags: [] }]);
    model._state.frames = [{ filePath: '/ws/frame.py', relativePath: 'frame.py' }];
    model._state.shippedPatterns = [{ sourceFile: '/deps/book.py', name: 'a', patternbookName: 'book' }];
    const keys = [];
    (function walk(nodes) {
      for (const node of nodes) {
        keys.push(node.key);
        if (node.children) walk(node.children);
      }
    })(model.getTree());

    expect(new Set(keys).size).toBe(keys.length);
  });
});

describe('row actions', () => {
  test('only library rows can be duplicated to the workspace', () => {
    const model = new SidebarModel();
    model._state.workspacePatternbooks = [{ filePath: '/ws/book.py', patterns: [{ path: 'mine', tags: [] }] }];
    model._state.shippedPatterns = [{ sourceFile: '/deps/book.py', name: 'theirs', patternbookName: 'book' }];
    const tree = model.getTree();
    const mine = findNode(tree, (node) => node.label === 'mine');
    const theirs = findNode(tree, (node) => node.label === 'theirs');
    const group = findNode(tree, (node) => node.type === 'patternbookGroup');

    expect(mine.rowActions).toEqual(['viewSource', 'openInViewer', 'openInNewWindow']);
    expect(theirs.rowActions).toEqual(['viewSource', 'duplicate', 'openInViewer', 'openInNewWindow']);
    expect(group.rowActions).toEqual(['viewSource', 'duplicate']);
  });

  test('a project frame can be deleted; a library frame can not', () => {
    const model = new SidebarModel();
    model._state.frames = [{ filePath: '/ws/frame.py', relativePath: 'frame.py' }];
    model._state.shippedExamples = [{ sourceFile: '/deps/example.py', name: 'example' }];
    const tree = model.getTree();

    expect(findNode(tree, (node) => node.label === 'frame.py').rowActions).toContain('deleteFile');
    expect(findNode(tree, (node) => node.label === 'example').rowActions).not.toContain('deleteFile');
  });

  test('every row action names a known action', () => {
    const model = new SidebarModel();
    model._state.frames = [{ filePath: '/ws/frame.py', relativePath: 'frame.py' }];
    model._state.shippedPatterns = [{ sourceFile: '/deps/book.py', name: 'a', patternbookName: 'book' }];
    const used = new Set();
    (function walk(nodes) {
      for (const node of nodes) {
        (node.rowActions || []).forEach((id) => used.add(id));
        if (node.children) walk(node.children);
      }
    })(model.getTree());

    expect(used.size).toBeGreaterThan(0);
    for (const id of used) {
      expect(ROW_ACTIONS[id]).toBeDefined();
    }
  });
});

describe('test snapshot', () => {
  test('lists roots with their child counts', async () => {
    const model = new SidebarModel();
    scanWorkspaceForFrames.mockResolvedValue({
      frameFiles: [{ filePath: '/ws/frame.py', relativePath: 'frame.py' }],
      patternbookFiles: [],
      scanErrors: [],
    });
    const snapshot = await model.getTestSnapshot();
    const frames = snapshot.roots.find((root) => root.key === 'frames-root');

    expect(snapshot.state.frameCount).toBe(1);
    expect(frames.childLabels).toEqual(['frame.py', 'New Frame…']);
    expect(snapshot.groupByPatternbook).toBe(true);
  });
});

describe('all files', () => {
  let root;

  function filesHost(extra = {}) {
    setHost({
      locale: 'en',
      workspaceRoots: () => [root],
      getConfig: (_key, fallback) => fallback,
      showsFileBrowser: true,
      ...extra,
    });
  }

  beforeEach(() => {
    root = fs.mkdtempSync(path.join(os.tmpdir(), 'kigumi-files-'));
    for (const dir of ['patterns', 'docs', '.venv', '__pycache__']) {
      fs.mkdirSync(path.join(root, dir));
    }
    fs.writeFileSync(path.join(root, 'b_frame.py'), '');
    fs.writeFileSync(path.join(root, 'a_notes.txt'), '');
    fs.writeFileSync(path.join(root, 'patterns', 'book.py'), '');
  });

  afterEach(() => fs.rmSync(root, { recursive: true, force: true }));

  test('a host without a file browser shows none', () => {
    expect(rootOf(new SidebarModel(), 'filesRoot')).toBeUndefined();
  });

  test('the root comes first, collapsed and not listed until opened', () => {
    filesHost();
    const model = new SidebarModel();
    const tree = model.getTree().filter((one) => !one.type.startsWith('project') && !one.type.startsWith('kumiki'));

    expect(tree[0]).toMatchObject({ type: 'filesRoot', expanded: false, lazyDir: root, children: [] });
  });

  test('an opened folder lists folders first, then files, leaving out the excluded', async () => {
    filesHost();
    const model = new SidebarModel();
    await model.openFolder(root);
    const files = rootOf(model, 'filesRoot');

    expect(files.lazyDir).toBeUndefined();
    expect(files.children.map((child) => child.label)).toEqual(['docs', 'patterns', 'a_notes.txt', 'b_frame.py']);
    expect(findNode(files.children, (one) => one.label === 'patterns').lazyDir).toBe(path.join(root, 'patterns'));
  });

  test('the exclude setting replaces the default', async () => {
    filesHost({ getConfig: (key, fallback) => (key === 'app.filesExclude' ? ['*.txt'] : fallback) });
    const model = new SidebarModel();
    await model.openFolder(root);

    const labels = rootOf(model, 'filesRoot').children.map((child) => child.label);
    expect(labels).toEqual(expect.arrayContaining(['.venv', '__pycache__', 'b_frame.py']));
    expect(labels).not.toContain('a_notes.txt');
  });

  test('frames and patternbooks keep their icons; a click opens the source; Python files open in the viewer; any file or folder reveals', async () => {
    filesHost();
    const frame = path.join(root, 'b_frame.py');
    const book = path.join(root, 'patterns', 'book.py');
    scanWorkspaceForFrames.mockResolvedValue({
      frameFiles: [{ filePath: frame, relativePath: 'b_frame.py' }],
      patternbookFiles: [{ filePath: book, relativePath: 'patterns/book.py', patterns: [] }],
      scanErrors: [],
    });
    const model = new SidebarModel();
    await model.refresh(true);
    await model.openFolder(root);
    await model.openFolder(path.join(root, 'patterns'));
    const byLabel = (label) => findNode(rootOf(model, 'filesRoot').children, (one) => one.label === label);

    expect(byLabel('b_frame.py')).toMatchObject({
      icon: 'fish2-very-sad', rowActions: ['openInViewer', 'newFile', 'revealInFileManager', 'deleteFile'],
      action: { command: 'kigumi.openFileSource', arguments: [frame] },
    });
    expect(byLabel('book.py').icon).toBe('library');
    expect(byLabel('a_notes.txt')).toMatchObject({ icon: 'file', rowActions: ['newFile', 'revealInFileManager', 'deleteFile'] });
    expect(byLabel('patterns').rowActions).toEqual(['newFile', 'revealInFileManager']);
    expect(rootOf(model, 'filesRoot').rowActions).toEqual(['newFile', 'revealInFileManager']);
  });

  test('a folder outside the workspace is not listed', async () => {
    filesHost();
    const model = new SidebarModel();
    await model.openFolder(os.tmpdir());

    expect(model.isFolderListed(os.tmpdir())).toBe(false);
  });

  test('refreshing lists opened folders again', async () => {
    filesHost();
    const model = new SidebarModel();
    await model.openFolder(root);
    fs.writeFileSync(path.join(root, 'c_new.py'), '');
    await model.refreshFiles();

    expect(rootOf(model, 'filesRoot').children.map((child) => child.label)).toContain('c_new.py');
  });
});
