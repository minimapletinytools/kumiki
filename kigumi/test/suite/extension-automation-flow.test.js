const assert = require('assert');
const fs = require('fs');
const path = require('path');
const vscode = require('vscode');

async function waitFor(predicate, timeoutMs = 20000, intervalMs = 150) {
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

describe('Kigumi automation flow', () => {
  it('opens a specific file in the viewer via automation command', async function () {
    this.timeout(60000);

    await activateKigumiExtension();
    await vscode.commands.executeCommand('workbench.action.closeAllEditors');

    const fixturePath = path.resolve(__dirname, '..', '..', 'test-fixtures', 'minimal_frame.py');

    const openResult = await vscode.commands.executeCommand('kigumi.automationOpenFileInViewer', {
      filePath: fixturePath,
    });

    assert.ok(openResult && openResult.ok, 'Expected automation open file command to succeed');
    assert.strictEqual(openResult.filePath, fixturePath, 'Expected automation open file command to report the opened path');

    const snapshot = await waitFor(async () => {
      const candidate = await vscode.commands.executeCommand('kigumi.testGetSessionSnapshot', { filePath: fixturePath });
      if (!candidate || !candidate.exists || !candidate.runnerAlive || !candidate.frame || !candidate.geometry) {
        return null;
      }
      return candidate;
    }, 25000, 180);

    assert.strictEqual(snapshot.filePath, fixturePath, 'Expected session snapshot to match opened fixture');
  });

  it('supports session refresh/log/camera/screenshot automation commands', async function () {
    this.timeout(90000);

    await activateKigumiExtension();
    await vscode.commands.executeCommand('workbench.action.closeAllEditors');

    await vscode.workspace.getConfiguration('kigumi').update(
      'viewer.autoRefreshOnFileChange',
      false,
      vscode.ConfigurationTarget.Workspace
    );

    const fixturePath = path.resolve(__dirname, '..', '..', 'test-fixtures', 'minimal_frame.py');
    const fixtureUri = vscode.Uri.file(fixturePath);
    const document = await vscode.workspace.openTextDocument(fixtureUri);
    await vscode.window.showTextDocument(document, { preview: false });
    await vscode.commands.executeCommand('kigumi.render');

    const baselineSnapshot = await waitFor(async () => {
      const snapshot = await vscode.commands.executeCommand('kigumi.testGetSessionSnapshot', { filePath: fixturePath });
      if (!snapshot || !snapshot.exists || !snapshot.runnerAlive || !snapshot.frame || !snapshot.geometry) {
        return null;
      }
      return snapshot;
    }, 25000, 180);

    assert.strictEqual(baselineSnapshot.watcherEnabled, false, 'Expected watcher to default off via config');

    const listResult = await vscode.commands.executeCommand('kigumi.automationListSessions');
    assert.ok(listResult && Array.isArray(listResult.sessions), 'Expected automation list sessions payload');
    assert.ok(
      listResult.sessions.some((session) => session.filePath === fixturePath),
      'Expected list sessions to include the rendered fixture'
    );

    const editableDocument = await vscode.workspace.openTextDocument(fixtureUri);
    const originalText = editableDocument.getText();

    const dirtyEdit = new vscode.WorkspaceEdit();
    const appendPosition = new vscode.Position(editableDocument.lineCount, 0);
    dirtyEdit.insert(editableDocument.uri, appendPosition, '\n# automation temporary change\n');
    const editApplied = await vscode.workspace.applyEdit(dirtyEdit);
    assert.strictEqual(editApplied, true, 'Expected dirty edit to apply');
    const dirtyDocument = await vscode.workspace.openTextDocument(fixtureUri);
    assert.strictEqual(dirtyDocument.isDirty, true, 'Expected fixture document to become dirty');

    const dirtyRefresh = await vscode.commands.executeCommand('kigumi.automationRefreshSession', {
      filePath: fixturePath,
      dirtyOnce: true,
      saveIfDirty: false,
      reason: 'automation test dirty-once',
    });
    assert.ok(dirtyRefresh && dirtyRefresh.ok, 'Expected dirty-once refresh command to succeed');
    assert.strictEqual(dirtyRefresh.mode, 'dirtyOnce');
    assert.strictEqual(dirtyRefresh.result && dirtyRefresh.result.refreshed, true, 'Expected dirty-once refresh to run');

    const restoreDocument = await vscode.workspace.openTextDocument(fixtureUri);
    const restoreEdit = new vscode.WorkspaceEdit();
    const fullRange = new vscode.Range(
      new vscode.Position(0, 0),
      new vscode.Position(restoreDocument.lineCount, 0)
    );
    restoreEdit.replace(restoreDocument.uri, fullRange, originalText);
    await vscode.workspace.applyEdit(restoreEdit);

    const refreshResult = await vscode.commands.executeCommand('kigumi.automationRefreshSession', {
      filePath: fixturePath,
      reason: 'automation test explicit refresh',
    });
    assert.ok(refreshResult && refreshResult.ok, 'Expected explicit refresh to succeed');

    const logsResult = await vscode.commands.executeCommand('kigumi.automationReadSessionLogs', {
      filePath: fixturePath,
      contains: '[refresh]',
      minLevel: 'info',
    });
    assert.ok(logsResult && logsResult.ok, 'Expected log read command to succeed');
    assert.ok(Array.isArray(logsResult.entries), 'Expected log entries array');
    assert.ok(logsResult.entries.length > 0, 'Expected refresh logs to be available');

    const cameraBefore = await vscode.commands.executeCommand('kigumi.automationGetCameraState', {
      filePath: fixturePath,
    });
    assert.ok(cameraBefore && cameraBefore.ok && cameraBefore.payload, 'Expected camera state before update');

    const nextCameraState = {
      orbitCenter: cameraBefore.payload.orbitCenter,
      up: cameraBefore.payload.up,
      orbit: {
        theta: Number(cameraBefore.payload.orbit.theta) + 0.07,
        phi: Number(cameraBefore.payload.orbit.phi),
        distance: Number(cameraBefore.payload.orbit.distance) * 1.05,
      },
    };

    const cameraSet = await vscode.commands.executeCommand('kigumi.automationSetCameraState', {
      filePath: fixturePath,
      cameraState: nextCameraState,
    });
    assert.ok(cameraSet && cameraSet.ok, 'Expected set camera command to succeed');

    const cameraAfter = await vscode.commands.executeCommand('kigumi.automationGetCameraState', {
      filePath: fixturePath,
    });
    assert.ok(cameraAfter && cameraAfter.ok && cameraAfter.payload, 'Expected camera state after update');

    const thetaDelta = Math.abs(Number(cameraAfter.payload.orbit.theta) - Number(cameraBefore.payload.orbit.theta));
    assert.ok(thetaDelta > 0.001, 'Expected camera theta to change after automation set');

    const artifactDir = path.resolve(__dirname, '..', '..', '.artifacts', 'automation');
    const screenshotResult = await vscode.commands.executeCommand('kigumi.captureScreenshot', {
      filePath: fixturePath,
      outputDir: artifactDir,
      namePrefix: `automation-${Date.now()}`,
      preRefresh: true,
      preRefreshDirtyOnce: false,
      timeoutMs: 0,
    });

    assert.ok(screenshotResult && screenshotResult.ok, 'Expected screenshot command to succeed');
    assert.ok(fs.existsSync(screenshotResult.screenshotPath), 'Expected screenshot artifact to be written');

    const toggleResult = await vscode.commands.executeCommand('kigumi.toggleAutoRefreshOnFileChange');
    assert.ok(toggleResult && typeof toggleResult.enabled === 'boolean', 'Expected toggle command result');

    const snapshotAfterToggle = await waitFor(async () => {
      const snapshot = await vscode.commands.executeCommand('kigumi.testGetSessionSnapshot', { filePath: fixturePath });
      if (!snapshot || !snapshot.exists) {
        return null;
      }
      return snapshot;
    }, 10000, 150);
    assert.strictEqual(snapshotAfterToggle.watcherEnabled, toggleResult.enabled, 'Expected watcher state to follow toggle');

    await vscode.workspace.getConfiguration('kigumi').update(
      'viewer.autoRefreshOnFileChange',
      false,
      vscode.ConfigurationTarget.Workspace
    );
  });
});
