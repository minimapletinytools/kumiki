const assert = require('assert');
const vscode = require('vscode');

describe('Kigumi extension smoke', () => {
  it('registers the Render Kigumi command', async () => {
    const extension = vscode.extensions.all.find((candidate) =>
      candidate.id.toLowerCase().endsWith('.kigumi')
    );
    assert.ok(extension, 'Expected Kigumi extension to be available in Extension Host');

    await extension.activate();

    const commands = await vscode.commands.getCommands(true);
    assert.ok(commands.includes('kigumi.render'));
    assert.ok(commands.includes('kigumi.browsePatterns'));
    assert.ok(commands.includes('kigumi.unloadPattern'));
  });

  it('executes Render Kigumi command without crashing when no editor is active', async () => {
    await vscode.commands.executeCommand('workbench.action.closeAllEditors');
    await assert.doesNotReject(async () => {
      await vscode.commands.executeCommand('kigumi.render');
    });
  });
});
