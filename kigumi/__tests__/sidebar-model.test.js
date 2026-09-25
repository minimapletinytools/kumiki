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
      getKumikiVersionInfo: async () => ({ installedVersion: '0.6.0', latestVersion: '0.6.1' }),
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

    expect(mine.rowActions).toEqual(['viewSource', 'openInNewWindow']);
    expect(theirs.rowActions).toEqual(['viewSource', 'duplicate', 'openInNewWindow']);
    expect(group.rowActions).toEqual(['viewSource', 'duplicate']);
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
    expect(frames.childLabels).toEqual(['frame.py']);
    expect(snapshot.groupByPatternbook).toBe(true);
  });
});
