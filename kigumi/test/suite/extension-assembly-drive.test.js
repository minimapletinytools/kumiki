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

describe('Assembly timeline drive', () => {
  it('loads an assembly-annotated frame and keeps the webview healthy', async function () {
    this.timeout(90000);

    await activateKigumiExtension();
    await vscode.commands.executeCommand('workbench.action.closeAllEditors');

    const fixturePath = path.resolve(__dirname, '..', '..', 'test-fixtures', 'assembly_frame.py');

    const openResult = await vscode.commands.executeCommand('kigumi.automationOpenFileInViewer', {
      filePath: fixturePath,
    });
    assert.ok(openResult && openResult.ok, 'Expected automation open file command to succeed');

    const snapshot = await waitFor(async () => {
      const candidate = await vscode.commands.executeCommand('kigumi.testGetSessionSnapshot', { filePath: fixturePath });
      if (!candidate || !candidate.exists || !candidate.runnerAlive || !candidate.frame || !candidate.geometry) {
        return null;
      }
      return candidate;
    }, 30000, 200);
    assert.strictEqual(snapshot.filePath, fixturePath, 'Expected session snapshot for the assembly fixture');

    // A successful screenshot requires a webview requestAnimationFrame round
    // trip, which proves the app is still rendering with assembly data present
    // (the timeline branch is active: the fixture has an annotated joint).
    const artifactDir = path.resolve(__dirname, '..', '..', '.artifacts', 'assembly');
    const screenshotResult = await vscode.commands.executeCommand('kigumi.captureScreenshot', {
      filePath: fixturePath,
      outputDir: artifactDir,
      namePrefix: `assembly-drive-${Date.now()}`,
      preRefresh: false,
      timeoutMs: 0,
    });
    assert.ok(screenshotResult && screenshotResult.ok, `Expected screenshot to succeed: ${JSON.stringify(screenshotResult)}`);
    assert.ok(fs.existsSync(screenshotResult.screenshotPath), 'Expected screenshot artifact to be written');
  });
});
