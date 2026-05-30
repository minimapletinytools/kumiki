const assert = require('assert');
const path = require('path');
const vscode = require('vscode');

async function waitFor(predicate, timeoutMs = 12000, intervalMs = 120) {
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

describe('Kigumi initial state validation', () => {
  it('shows expected sidebar baseline sections', async function () {
    this.timeout(45000);

    await activateKigumiExtension();
    await vscode.commands.executeCommand('kigumi.refreshSidebar');

    const snapshot = await waitFor(async () => {
      const payload = await vscode.commands.executeCommand('kigumi.testGetSidebarSnapshot', { forceRefresh: true });
      if (!payload || !Array.isArray(payload.roots) || payload.roots.length === 0) {
        return null;
      }
      const hasFramesRoot = payload.roots.some((root) => typeof root.label === 'string' && root.label.startsWith('Frames'));
      const hasPatternsRoot = payload.roots.some((root) => typeof root.label === 'string' && root.label.startsWith('Patterns'));
      return hasFramesRoot && hasPatternsRoot ? payload : null;
    }, 30000, 200);

    const rootLabels = snapshot.roots.map((root) => root.label);
    assert.ok(rootLabels.some((label) => label.startsWith('Frames')), 'Expected Frames root in sidebar');
    assert.ok(rootLabels.some((label) => label.startsWith('Patterns')), 'Expected Patterns root in sidebar');

    const framesRoot = snapshot.roots.find((root) => typeof root.label === 'string' && root.label.startsWith('Frames'));
    assert.ok(framesRoot, 'Expected Frames root snapshot');
    assert.ok(
      framesRoot.childCount > 0,
      `Expected Frames root to include at least one frame entry, got ${framesRoot.childCount}`
    );

    const patternsRoot = snapshot.roots.find((root) => typeof root.label === 'string' && root.label.startsWith('Patterns'));
    assert.ok(patternsRoot, 'Expected Patterns root snapshot');
    assert.ok(
      patternsRoot.childCount >= 1,
      `Expected Patterns root to include at least the workspace section, got ${patternsRoot.childCount}`
    );
  });

  it('renders fixture with expected initial viewer and panel state', async function () {
    this.timeout(45000);

    await activateKigumiExtension();

    const fixturePath = path.resolve(__dirname, '..', '..', 'test-fixtures', 'minimal_frame.py');
    const fixtureUri = vscode.Uri.file(fixturePath);

    await vscode.commands.executeCommand('workbench.action.closeAllEditors');
    const document = await vscode.workspace.openTextDocument(fixtureUri);
    await vscode.window.showTextDocument(document, { preview: false });

    await vscode.commands.executeCommand('kigumi.render');

    const sessionSnapshot = await waitFor(async () => {
      const payload = await vscode.commands.executeCommand('kigumi.testGetSessionSnapshot', {
        filePath: fixturePath,
        includePanelSnapshot: true,
        timeoutMs: 6000,
      });
      if (!payload || !payload.exists || !payload.frame || !payload.geometry || !payload.panelSnapshot) {
        return null;
      }
      if (!payload.runnerAlive) {
        return null;
      }
      return payload;
    }, 30000, 150);

    assert.ok(sessionSnapshot.hasPanel, 'Expected viewer panel to be open');
    assert.ok(
      typeof sessionSnapshot.panelTitle === 'string' && sessionSnapshot.panelTitle.startsWith('Kigumi: Runner Test Frame'),
      `Expected viewer tab title to include rendered frame name, got '${sessionSnapshot.panelTitle}'`
    );

    assert.strictEqual(sessionSnapshot.frame.name, 'Runner Test Frame');
    assert.ok(
      sessionSnapshot.frame.timberCount > 0,
      `Expected rendered frame to have timbers, got ${sessionSnapshot.frame.timberCount}`
    );
    assert.ok(
      sessionSnapshot.geometry.meshCount >= sessionSnapshot.frame.timberCount,
      `Expected geometry mesh count to cover timbers (${sessionSnapshot.frame.timberCount}), got ${sessionSnapshot.geometry.meshCount}`
    );

    const panelSnapshot = sessionSnapshot.panelSnapshot;
    assert.ok(panelSnapshot.hasRenderControls, 'Expected options panel controls to be rendered');
    assert.ok(panelSnapshot.hasMemberListPanel, 'Expected Member List panel to be rendered');
    assert.ok(panelSnapshot.hasMemberTableBody, 'Expected member table body to be rendered');
    assert.ok(panelSnapshot.hasLogOutputPanel, 'Expected Log Output panel to be rendered');
    assert.ok(panelSnapshot.hasRawPythonOutputPanel, 'Expected Raw Python Output panel to be rendered');
    assert.ok(panelSnapshot.isRawPythonOutputPanelLast, 'Expected Raw Python Output panel to be at the bottom');

  });
});
