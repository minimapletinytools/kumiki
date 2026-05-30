const assert = require('assert');
const path = require('path');
const vscode = require('vscode');

async function waitFor(predicate, timeoutMs = 16000, intervalMs = 150) {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    const value = await predicate();
    if (value) {
      return value;
    }
    await new Promise((resolve) => setTimeout(resolve, intervalMs));
  }
  throw new Error(`Timed out waiting for condition after ${timeoutMs}ms`);
}

async function activateKigumiExtension() {
  const extension = vscode.extensions.all.find((candidate) =>
    candidate.id.toLowerCase().endsWith('.kigumi')
  );
  assert.ok(extension, 'Expected Kigumi extension to be available in Extension Host');
  await extension.activate();
}

async function openAndRenderFixture(filePath) {
  const fileUri = vscode.Uri.file(filePath);
  const document = await vscode.workspace.openTextDocument(fileUri);
  await vscode.window.showTextDocument(document, { preview: false });
  await vscode.commands.executeCommand('kigumi.render');

  return waitFor(async () => {
    const snapshot = await vscode.commands.executeCommand('kigumi.testGetSessionSnapshot', {
      filePath,
      includePanelSnapshot: true,
      timeoutMs: 5000,
    });
    if (!snapshot || !snapshot.exists || !snapshot.runnerAlive || !snapshot.frame || !snapshot.geometry) {
      return null;
    }
    return snapshot;
  }, 25000, 180);
}

function getAllTabs() {
  return vscode.window.tabGroups.all.flatMap((group) => group.tabs);
}

describe('Kigumi complex validation', () => {
  it('switches fixtures and keeps independent viewer state healthy', async function () {
    this.timeout(70000);

    await activateKigumiExtension();
    await vscode.commands.executeCommand('workbench.action.closeAllEditors');

    const minimalFixture = path.resolve(__dirname, '..', '..', 'test-fixtures', 'minimal_frame.py');
    const accessoryFixture = path.resolve(__dirname, '..', '..', 'test-fixtures', 'accessory_frame.py');

    const minimalSnapshot = await openAndRenderFixture(minimalFixture);
    assert.strictEqual(minimalSnapshot.frame.name, 'Runner Test Frame');
    assert.ok(minimalSnapshot.geometry.meshCount > 0, 'Expected minimal fixture to produce geometry');
    assert.ok(minimalSnapshot.panelSnapshot && minimalSnapshot.panelSnapshot.hasMemberListPanel, 'Expected member panel in minimal fixture');

    const accessorySnapshot = await openAndRenderFixture(accessoryFixture);
    assert.notStrictEqual(
      accessorySnapshot.frame.name,
      minimalSnapshot.frame.name,
      'Expected accessory fixture to produce a different frame name'
    );
    assert.ok(accessorySnapshot.frame.accessoryCount > 0, 'Expected accessory fixture to include accessories');
    assert.ok(
      accessorySnapshot.geometry.meshCount >= accessorySnapshot.frame.timberCount,
      'Expected accessory fixture geometry to include timber meshes'
    );
    assert.ok(
      accessorySnapshot.panelSnapshot && accessorySnapshot.panelSnapshot.isRawPythonOutputPanelLast,
      'Expected raw output panel to stay last during fixture switching'
    );

    const minimalSnapshotAfterSwitch = await openAndRenderFixture(minimalFixture);
    assert.strictEqual(minimalSnapshotAfterSwitch.frame.name, 'Runner Test Frame');
    assert.ok(minimalSnapshotAfterSwitch.runnerAlive, 'Expected runner to remain alive after switching fixtures');

    const minimalTabs = getAllTabs().filter((tab) => typeof tab.label === 'string' && tab.label.startsWith('Kigumi: Runner Test Frame'));
    assert.ok(minimalTabs.length === 1, `Expected one minimal frame viewer tab, got ${minimalTabs.length}`);
  });

  it('toggles sidebar grouping and restores the original state', async function () {
    this.timeout(45000);

    await activateKigumiExtension();

    const beforeToggle = await vscode.commands.executeCommand('kigumi.testGetSidebarSnapshot', { forceRefresh: true });
    assert.ok(beforeToggle && Array.isArray(beforeToggle.roots), 'Expected sidebar snapshot before toggle');

    await vscode.commands.executeCommand('kigumi.toggleGroupByPatternbook');

    const afterToggle = await waitFor(async () => {
      const snapshot = await vscode.commands.executeCommand('kigumi.testGetSidebarSnapshot', { forceRefresh: false });
      if (!snapshot || typeof snapshot.groupByPatternbook !== 'boolean') {
        return null;
      }
      return snapshot;
    }, 12000, 150);

    assert.notStrictEqual(
      afterToggle.groupByPatternbook,
      beforeToggle.groupByPatternbook,
      'Expected groupByPatternbook to change after toggle'
    );

    await vscode.commands.executeCommand('kigumi.toggleGroupByPatternbook');

    const restored = await waitFor(async () => {
      const snapshot = await vscode.commands.executeCommand('kigumi.testGetSidebarSnapshot', { forceRefresh: false });
      if (!snapshot || typeof snapshot.groupByPatternbook !== 'boolean') {
        return null;
      }
      return snapshot;
    }, 12000, 150);

    assert.strictEqual(
      restored.groupByPatternbook,
      beforeToggle.groupByPatternbook,
      'Expected second toggle to restore original grouping mode'
    );
    assert.ok(
      restored.roots.some((root) => typeof root.label === 'string' && root.label.startsWith('Patterns')),
      'Expected Patterns root to remain available after toggle round-trip'
    );
  });

  it('opens a pattern from sidebar command path', async function () {
    this.timeout(70000);

    await activateKigumiExtension();
    await vscode.commands.executeCommand('workbench.action.closeAllEditors');

    const sourceFile = path.resolve(__dirname, '..', '..', 'test-fixtures', 'patternbook_frame.py');

    await vscode.commands.executeCommand('kigumi.openPatternFromSidebar', {
      sourceFile,
      patternName: 'small_post_pattern',
    });

    const patternSession = await waitFor(async () => {
      const payload = await vscode.commands.executeCommand('kigumi.automationListSessions');
      if (!payload || !Array.isArray(payload.sessions)) {
        return null;
      }

      const match = payload.sessions.find((session) => (
        session
        && session.sessionType === 'pattern'
        && session.filePath === sourceFile
        && session.runnerAlive
        && session.frame
        && session.geometry
      ));
      return match || null;
    }, 30000, 180);

    assert.ok(patternSession, 'Expected sidebar pattern-open command to create a healthy pattern session');
    assert.ok(
      typeof patternSession.slotName === 'string' && patternSession.slotName.startsWith('pattern_'),
      `Expected pattern session slotName to use pattern_* format, got '${patternSession.slotName}'`
    );
    assert.ok(
      Number.isFinite(patternSession.frame.timberCount) && patternSession.frame.timberCount > 0,
      `Expected opened pattern to render timbers, got ${patternSession.frame && patternSession.frame.timberCount}`
    );
  });
});
