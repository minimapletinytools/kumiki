const assert = require('assert');
const path = require('path');
const vscode = require('vscode');

async function waitFor(condition, timeoutMs = 15000, intervalMs = 120) {
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

describe('Horsey Viewer extension flow', () => {
  it('renders milestone fixture and keeps panel healthy across rerender', async function () {
    this.timeout(40000);

    const fixturePath = path.resolve(__dirname, '..', '..', 'test-fixtures', 'milestone_joint_frame.py');
    const fixtureUri = vscode.Uri.file(fixturePath);

    await vscode.commands.executeCommand('workbench.action.closeAllEditors');
    const document = await vscode.workspace.openTextDocument(fixtureUri);
    await vscode.window.showTextDocument(document, { preview: false });

    const expectedTabPrefix = 'Horsey: Runner Milestone Joint Frame';

    await vscode.commands.executeCommand('horsey-viewer.renderHorsey');

    await waitFor(() => {
      const tabs = getAllTabs();
      return tabs.some((tab) => tab.label.startsWith(expectedTabPrefix));
    }, 25000, 150);

    await assert.doesNotReject(async () => {
      await vscode.commands.executeCommand('horsey-viewer.renderHorsey');
    });

    const tabs = getAllTabs();
    assert.ok(
      tabs.some((tab) => tab.label.startsWith(expectedTabPrefix)),
      'Expected Horsey webview tab for milestone_joint_frame.py with the current frame-name title format'
    );
  });
});
