const assert = require('assert');
const fs = require('fs');
const path = require('path');
const vscode = require('vscode');

const SCREENSHOT_MODE = String(process.env.HORSEY_EXT_SCREENSHOT_MODE || 'never').toLowerCase();
const SHOULD_CAPTURE_ALWAYS = SCREENSHOT_MODE === 'always';
const SHOULD_CAPTURE_ON_FAILURE = SCREENSHOT_MODE === 'on-failure';

function screenshotArtifactsDir() {
  return process.env.HORSEY_EXT_SCREENSHOT_DIR
    ? path.resolve(process.env.HORSEY_EXT_SCREENSHOT_DIR)
    : path.resolve(__dirname, '..', '..', '.artifacts', 'screenshots');
}

async function captureScreenshot(filePath, name) {
  const outputPath = path.join(screenshotArtifactsDir(), `${name}.png`);
  const result = await vscode.commands.executeCommand('horsey-viewer.captureRenderedScreenshot', {
    filePath,
    outputPath,
    timeoutMs: 10000,
  });

  assert.ok(result, 'Expected screenshot command to return metadata');
  assert.ok(result.byteLength > 0, 'Expected screenshot bytes to be non-empty');
  assert.ok(fs.existsSync(outputPath), `Expected screenshot to be written: ${outputPath}`);
  return outputPath;
}

async function waitFor(condition, timeoutMs = 12000, intervalMs = 100) {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    if (condition()) {
      return;
    }
    await new Promise((resolve) => setTimeout(resolve, intervalMs));
  }
  throw new Error(`Timed out waiting for condition after ${timeoutMs}ms`);
}

function getAllTabs() {
  return vscode.window.tabGroups.all.flatMap((group) => group.tabs);
}

describe('Horsey Viewer extension smoke', () => {
  it('registers the Render Horsey command', async () => {
    const extension = vscode.extensions.all.find((candidate) =>
      candidate.id.toLowerCase().endsWith('.horsey-viewer')
    );
    assert.ok(extension, 'Expected Horsey Viewer extension to be available in Extension Host');

    await extension.activate();

    const commands = await vscode.commands.getCommands(true);
    assert.ok(commands.includes('horsey-viewer.renderHorsey'));
    assert.ok(commands.includes('horsey-viewer.browsePatterns'));
    assert.ok(commands.includes('horsey-viewer.unloadPattern'));
  });

  it('executes Render Horsey command without crashing when no editor is active', async () => {
    await vscode.commands.executeCommand('workbench.action.closeAllEditors');
    await assert.doesNotReject(async () => {
      await vscode.commands.executeCommand('horsey-viewer.renderHorsey');
    });
  });

  it('opens fixture and renders Horsey webview panel with frame name', async function () {
    this.timeout(30000);

    const fixturePath = path.resolve(__dirname, '..', '..', 'test-fixtures', 'minimal_frame.py');
    const fixtureUri = vscode.Uri.file(fixturePath);

    await vscode.commands.executeCommand('workbench.action.closeAllEditors');
    const document = await vscode.workspace.openTextDocument(fixtureUri);
    await vscode.window.showTextDocument(document, { preview: false });

    const expectedTabPrefix = 'Horsey: Runner Test Frame';

    const runAssertions = async () => {
      await vscode.commands.executeCommand('horsey-viewer.renderHorsey');

      await waitFor(() => {
        const tabs = getAllTabs();
        return tabs.some((tab) => tab.label.startsWith(expectedTabPrefix));
      }, 20000, 120);

      const tabs = getAllTabs();
      assert.ok(
        tabs.some((tab) => tab.label.startsWith(expectedTabPrefix)),
        'Expected Horsey webview tab for minimal_frame.py with rendered frame name'
      );
    };

    try {
      await runAssertions();
      if (SHOULD_CAPTURE_ALWAYS) {
        await captureScreenshot(fixturePath, 'extension-smoke-minimal-frame-success');
      }
    } catch (error) {
      if (SHOULD_CAPTURE_ALWAYS || SHOULD_CAPTURE_ON_FAILURE) {
        try {
          await captureScreenshot(fixturePath, 'extension-smoke-minimal-frame-failure');
        } catch (captureError) {
          console.warn('Failed to capture smoke failure screenshot:', captureError.message);
        }
      }
      throw error;
    }
  });
});
