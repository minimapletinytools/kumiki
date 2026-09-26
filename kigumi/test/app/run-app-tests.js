/**
 * Launches the standalone app on this repo with smoke-driver.js and exits with
 * its result. Uses a throwaway user-data folder.
 *
 * Usage: node test/app/run-app-tests.js [--app <packaged executable>] [artifacts-dir]
 */

const fs = require('fs');
const os = require('os');
const path = require('path');
const { spawn } = require('child_process');

const KIGUMI = path.resolve(__dirname, '..', '..');
const REPO = path.dirname(KIGUMI);

const env = {
    ...process.env,
    KIGUMI_ENABLE_TEST_COMMANDS: '1',
    KIGUMI_TEST_SCRIPT: path.join(__dirname, 'smoke-driver.js'),
    KIGUMI_USER_DATA: fs.mkdtempSync(path.join(os.tmpdir(), 'kigumi-app-test-')),
};
const args = process.argv.slice(2);
const appIndex = args.indexOf('--app');
const packagedApp = appIndex === -1 ? null : path.resolve(args.splice(appIndex, 2)[1]);
if (args[0]) {
    env.KIGUMI_TEST_ARTIFACTS = path.resolve(args[0]);
}
// Set by some tools that embed Electron; it would start Electron as plain Node.
delete env.ELECTRON_RUN_AS_NODE;

const [command, commandArgs] = packagedApp
    ? [packagedApp, [REPO]]
    : [require('electron'), [path.join(KIGUMI, 'hosts', 'electron', 'main.js'), REPO]];
const child = spawn(command, commandArgs, {
    cwd: KIGUMI,
    env,
    stdio: 'inherit',
});
let timedOut = false;
const timer = setTimeout(() => {
    timedOut = true;
    console.error('App tests timed out after 5 minutes.');
    child.kill();
}, 5 * 60 * 1000);
child.on('exit', (code) => {
    clearTimeout(timer);
    process.exit(timedOut || code === null ? 1 : code);
});
