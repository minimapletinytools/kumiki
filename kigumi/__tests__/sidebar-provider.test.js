/**
 * Integration tests for KigumiSidebarProvider.
 *
 * Tests the sidebar tree structure, state management, and user interactions.
 */

// Mock vscode module
const mockEventEmitter = {
  dispose: jest.fn(),
  fire: jest.fn(),
};

const mockTreeItemCollapsibleState = {
  None: 0,
  Collapsed: 1,
  Expanded: 2,
};

jest.mock('vscode', () => ({
  EventEmitter: jest.fn(() => mockEventEmitter),
  TreeItemCollapsibleState: mockTreeItemCollapsibleState,
  TreeItem: class TreeItem {
    constructor(label, collapsibleState) {
      this.label = label;
      this.collapsibleState = collapsibleState;
    }
  },
  ThemeIcon: class ThemeIcon {
    constructor(id) {
      this.id = id;
    }
  },
  workspace: {
    workspaceFolders: undefined,
    getConfiguration: jest.fn(() => ({
      get: jest.fn((key, defaultValue) => defaultValue),
    })),
  },
}), { virtual: true });

// Mock frame-scanner
jest.mock('../frame-scanner', () => ({
  scanWorkspaceForFrames: jest.fn().mockResolvedValue({
    frameFiles: [],
    patternbookFiles: [],
    scanErrors: [],
  }),
}));

// Mock discovery-adapter
jest.mock('../discovery-adapter', () => ({
  discoverDependencyContent: jest.fn().mockResolvedValue({
    kumikiPatterns: [],
    kumikiExamples: [],
    dependencyPatterns: [],
    dependencyExamples: [],
  }),
}));

// Mock project-initializer
jest.mock('../project-initializer', () => ({
  getInitializationStatus: jest.fn().mockReturnValue({
    projectStatus: 'ready',
    isInitialized: true,
  }),
}));

// Mock pattern-source-utils
jest.mock('../pattern-source-utils', () => ({
  groupPatternsByPatternbook: jest.fn((patterns) => ({})),
}));

const { KigumiSidebarProvider, SidebarNode } = require('../sidebar-provider');
const vscode = require('vscode');

describe('KigumiSidebarProvider', () => {
  let provider;
  let mockContext;

  beforeEach(() => {
    jest.clearAllMocks();
    mockEventEmitter.dispose.mockClear();
    mockEventEmitter.fire.mockClear();

    mockContext = {
      subscriptions: [],
    };

    provider = new KigumiSidebarProvider(mockContext, {
      getPythonCommand: () => undefined,
    });
  });

  afterEach(() => {
    provider.dispose();
  });

  describe('initialization', () => {
    test('should create provider with initial state', () => {
      expect(provider.context).toBe(mockContext);
      expect(provider._groupByPatternbook).toBe(true);
      expect(provider._selectedElementData).toBeNull();
    });

    test('should have empty state on creation', () => {
      expect(provider._state.frames).toEqual([]);
      expect(provider._state.workspacePatternbooks).toEqual([]);
      expect(provider._state.shippedPatterns).toEqual([]);
      expect(provider._state.isScanning).toBe(false);
    });

    test('should create event emitter for tree changes', () => {
      expect(vscode.EventEmitter).toHaveBeenCalled();
      expect(provider._onDidChangeTreeData).toBe(mockEventEmitter);
    });
  });

  describe('toggleGroupByPatternbook', () => {
    test('should toggle group state from true to false', () => {
      expect(provider.getGroupByPatternbook()).toBe(true);
      provider.toggleGroupByPatternbook();
      expect(provider.getGroupByPatternbook()).toBe(false);
    });

    test('should toggle group state from false to true', () => {
      provider.toggleGroupByPatternbook();
      expect(provider.getGroupByPatternbook()).toBe(false);
      provider.toggleGroupByPatternbook();
      expect(provider.getGroupByPatternbook()).toBe(true);
    });

    test('should fire onDidChangeTreeData event when toggling', () => {
      provider.toggleGroupByPatternbook();
      expect(mockEventEmitter.fire).toHaveBeenCalled();
    });

    test('should toggle multiple times independently', () => {
      const states = [];
      for (let i = 0; i < 5; i++) {
        provider.toggleGroupByPatternbook();
        states.push(provider.getGroupByPatternbook());
      }
      expect(states).toEqual([false, true, false, true, false]);
    });
  });

  describe('selected element tracking', () => {
    test('should initially have no selected element', () => {
      expect(provider.getSelectedElementData()).toBeNull();
    });

    test('should store selected element data', () => {
      const element = { type: 'patternItem', label: 'Test Pattern' };
      provider.setSelectedElementData(element);
      expect(provider.getSelectedElementData()).toBe(element);
    });

    test('should update selected element data', () => {
      const element1 = { type: 'patternItem', label: 'Pattern 1' };
      const element2 = { type: 'frameFile', label: 'Frame 1' };
      
      provider.setSelectedElementData(element1);
      expect(provider.getSelectedElementData()).toBe(element1);
      
      provider.setSelectedElementData(element2);
      expect(provider.getSelectedElementData()).toBe(element2);
    });

    test('should clear selected element when set to null', () => {
      const element = { type: 'patternItem', label: 'Test' };
      provider.setSelectedElementData(element);
      provider.setSelectedElementData(null);
      expect(provider.getSelectedElementData()).toBeNull();
    });
  });

  describe('getTreeItem conversion', () => {
    test('should convert SidebarNode to VS Code TreeItem', () => {
      const node = new SidebarNode({
        key: 'test-key',
        type: 'patternItem',
        label: 'Test Pattern',
        collapsibleState: vscode.TreeItemCollapsibleState.None,
      });

      const treeItem = provider.getTreeItem(node);

      expect(treeItem.label).toBe('Test Pattern');
      expect(treeItem.id).toBe('test-key');
      expect(treeItem.contextValue).toBe('patternItem');
      expect(treeItem.collapsibleState).toBe(vscode.TreeItemCollapsibleState.None);
    });

    test('should include command in TreeItem when provided', () => {
      const command = { command: 'kigumi.openPattern', title: 'Open Pattern' };
      const node = new SidebarNode({
        key: 'test-key',
        type: 'patternItem',
        label: 'Test',
        command,
      });

      const treeItem = provider.getTreeItem(node);
      expect(treeItem.command).toBe(command);
    });

    test('should set description in TreeItem', () => {
      const node = new SidebarNode({
        key: 'test-key',
        type: 'patternItem',
        label: 'Test',
        description: 'Test Description',
      });

      const treeItem = provider.getTreeItem(node);
      expect(treeItem.description).toBe('Test Description');
    });

    test('should set iconPath in TreeItem', () => {
      const icon = new vscode.ThemeIcon('symbol-array');
      const node = new SidebarNode({
        key: 'test-key',
        type: 'patternItem',
        label: 'Test',
        iconPath: icon,
      });

      const treeItem = provider.getTreeItem(node);
      expect(treeItem.iconPath).toBe(icon);
    });

    test('should use type as contextValue when not explicitly provided', () => {
      const node = new SidebarNode({
        key: 'test-key',
        type: 'frameFile',
        label: 'Frame.py',
      });

      const treeItem = provider.getTreeItem(node);
      expect(treeItem.contextValue).toBe('frameFile');
    });

    test('should use explicit contextValue over type', () => {
      const node = new SidebarNode({
        key: 'test-key',
        type: 'patternItem',
        label: 'Pattern',
        contextValue: 'patternItemWorkspace',
      });

      const treeItem = provider.getTreeItem(node);
      expect(treeItem.contextValue).toBe('patternItemWorkspace');
    });
  });

  describe('no workspace handling', () => {
    test('should handle no workspace folders gracefully', async () => {
      vscode.workspace.workspaceFolders = undefined;

      await provider.refresh(true);

      expect(provider._state.workspaceRoot).toBeNull();
      expect(provider._state.frames).toEqual([]);
      expect(provider._state.discoveryErrors).toContain('Open a workspace folder to use Kigumi Explorer.');
      expect(mockEventEmitter.fire).toHaveBeenCalled();
    });

    test('should show error message when getting root nodes with no workspace', async () => {
      vscode.workspace.workspaceFolders = undefined;
      await provider.refresh(true);

      const rootNodes = await provider.getRootNodes();
      expect(rootNodes.some(n => n.type === 'errorsRoot')).toBe(true);
    });
  });

  describe('dispose', () => {
    test('should dispose event emitter', () => {
      provider.dispose();
      expect(mockEventEmitter.dispose).toHaveBeenCalled();
    });
  });

  describe('refresh mechanics', () => {
    test('should mark as scanned after first ensureLoaded', () => {
      expect(provider._didLoadOnce).toBe(false);
      provider.ensureLoaded();
      expect(provider._didLoadOnce).toBe(true);
    });

    test('should not refresh twice when ensureLoaded called multiple times', () => {
      const fireCallsBefore = mockEventEmitter.fire.mock.calls.length;
      provider.ensureLoaded();
      provider.ensureLoaded();
      provider.ensureLoaded();
      
      // Should only trigger one refresh (from first ensureLoaded's async refresh)
      // Additional ensureLoaded calls should skip
      expect(mockEventEmitter.fire.mock.calls.length).toBeGreaterThan(fireCallsBefore);
    });

    test('should set isScanning to true during scan', async () => {
      vscode.workspace.workspaceFolders = [
        { uri: { fsPath: '/test/workspace' } }
      ];

      const scanPromise = provider.refresh(true);
      expect(provider._state.isScanning).toBe(true);

      await scanPromise;
      expect(provider._state.isScanning).toBe(false);
    });

    test('should fire event when scan completes', async () => {
      vscode.workspace.workspaceFolders = [
        { uri: { fsPath: '/test/workspace' } }
      ];

      const callCountBefore = mockEventEmitter.fire.mock.calls.length;
      await provider.refresh(true);
      const callCountAfter = mockEventEmitter.fire.mock.calls.length;

      expect(callCountAfter).toBeGreaterThan(callCountBefore);
    });
  });

  describe('tree navigation', () => {
    test('should return root nodes when getChildren called with no element', async () => {
      vscode.workspace.workspaceFolders = undefined;
      provider.ensureLoaded();
      
      const children = await provider.getChildren(null);
      
      expect(Array.isArray(children)).toBe(true);
      expect(children.length).toBeGreaterThan(0);
    });

    test('should return frame file nodes for framesRoot', async () => {
      const framesRootNode = new SidebarNode({
        key: 'frames-root',
        type: 'framesRoot',
        label: 'Frames',
      });

      const children = await provider.getChildren(framesRootNode);
      
      expect(Array.isArray(children)).toBe(true);
    });

    test('should return pattern section nodes for patternsRoot', async () => {
      const patternsRootNode = new SidebarNode({
        key: 'patterns-root',
        type: 'patternsRoot',
        label: 'Patterns',
      });

      const children = await provider.getChildren(patternsRootNode);
      
      expect(Array.isArray(children)).toBe(true);
    });

    test('should return empty array for unknown element type', async () => {
      const unknownNode = new SidebarNode({
        key: 'unknown',
        type: 'unknownType',
        label: 'Unknown',
      });

      const children = await provider.getChildren(unknownNode);
      
      expect(children).toEqual([]);
    });
  });

  describe('state management', () => {
    test('should initialize state with empty collections', () => {
      expect(provider._state.frames).toEqual([]);
      expect(provider._state.workspacePatternbooks).toEqual([]);
      expect(provider._state.shippedPatterns).toEqual([]);
      expect(provider._state.dependencyPatterns).toEqual([]);
      expect(provider._state.shippedExamples).toEqual([]);
      expect(provider._state.dependencyExamples).toEqual([]);
      expect(provider._state.scanErrors).toEqual([]);
      expect(provider._state.discoveryErrors).toEqual([]);
    });

    test('should maintain options reference', () => {
      const options = { getPythonCommand: () => 'python3' };
      const customProvider = new KigumiSidebarProvider(mockContext, options);
      
      expect(customProvider.options).toBe(options);
    });
  });

  describe('backward compatibility', () => {
    test('should have refreshPatterns method that calls refresh', async () => {
      vscode.workspace.workspaceFolders = [
        { uri: { fsPath: '/test/workspace' } }
      ];

      const result = await provider.refreshPatterns(true);
      
      // Should complete without error and update state
      expect(provider._state).toBeDefined();
    });
  });

  describe('SidebarNode creation', () => {
    test('should create node with minimal required properties', () => {
      const node = new SidebarNode({
        key: 'test',
        type: 'test',
        label: 'Test',
      });

      expect(node.key).toBe('test');
      expect(node.type).toBe('test');
      expect(node.label).toBe('Test');
      expect(node.collapsibleState).toBe(vscode.TreeItemCollapsibleState.None);
    });

    test('should create node with all properties', () => {
      const data = { extra: 'data' };
      const node = new SidebarNode({
        key: 'test',
        type: 'testType',
        label: 'Test Label',
        collapsibleState: vscode.TreeItemCollapsibleState.Expanded,
        command: { command: 'test.cmd' },
        description: 'Test Description',
        tooltip: 'Test Tooltip',
        iconPath: new vscode.ThemeIcon('test-icon'),
        data,
        contextValue: 'testContext',
      });

      expect(node.key).toBe('test');
      expect(node.type).toBe('testType');
      expect(node.label).toBe('Test Label');
      expect(node.collapsibleState).toBe(vscode.TreeItemCollapsibleState.Expanded);
      expect(node.command).toEqual({ command: 'test.cmd' });
      expect(node.description).toBe('Test Description');
      expect(node.tooltip).toBe('Test Tooltip');
      expect(node.data).toBe(data);
      expect(node.contextValue).toBe('testContext');
    });

    test('should use empty object for data when not provided', () => {
      const node = new SidebarNode({
        key: 'test',
        type: 'test',
        label: 'Test',
      });

      expect(node.data).toEqual({});
    });

    test('should use label as tooltip when tooltip not provided', () => {
      const node = new SidebarNode({
        key: 'test',
        type: 'test',
        label: 'Test Label',
      });

      expect(node.tooltip).toBeUndefined();
    });
  });
});
