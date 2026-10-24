/**
 * `npm run app:start`: runs the standalone app from source.
 *
 * On macOS the menu bar and the Dock take the app's name (and the Dock its icon) from the bundle
 * that runs, which the app can't change once running. So this runs a copy of Electron's bundle
 * named Kigumi, with Kigumi's icon, made once per Electron version under build-app/dev/. It also
 * claims kigumi:// links, as a build does, so signing in comes back to it. Elsewhere, or if that copy
 * can't be made, it runs Electron as it is.
 */

const { spawn, execFileSync } = require('child_process');
const fs = require('fs');
const os = require('os');
const path = require('path');
const electron = require('electron');

const ROOT = path.join(__dirname, '..');
const DEV_DIR = path.join(ROOT, 'build-app', 'dev');
const ICON = path.join(ROOT, 'templogo.png');
// Changes when the bundle is made differently, so an older copy is made again.
const BUNDLE_FORMAT = 2;
const LSREGISTER = '/System/Library/Frameworks/CoreServices.framework/Frameworks/LaunchServices.framework/Support/lsregister';

function run(command, args) {
    execFileSync(command, args, { stdio: 'ignore' });
}

function setPlist(plist, key, value) {
    try {
        run('/usr/libexec/PlistBuddy', ['-c', `Set :${key} ${value}`, plist]);
    } catch (_error) {
        run('/usr/libexec/PlistBuddy', ['-c', `Add :${key} string ${value}`, plist]);
    }
}

/** Writes Kigumi's icon over the bundle's, as an .icns made from the PNG. */
function replaceIcon(resources) {
    const temp = fs.mkdtempSync(path.join(os.tmpdir(), 'kigumi-icon-'));
    const iconset = path.join(temp, 'kigumi.iconset');
    fs.mkdirSync(iconset);
    for (const size of [16, 32, 128, 256, 512]) {
        run('sips', ['-z', String(size), String(size), ICON, '--out', path.join(iconset, `icon_${size}x${size}.png`)]);
        run('sips', ['-z', String(size * 2), String(size * 2), ICON, '--out', path.join(iconset, `icon_${size}x${size}@2x.png`)]);
    }
    run('iconutil', ['-c', 'icns', iconset, '-o', path.join(resources, 'electron.icns')]);
    fs.rmSync(temp, { recursive: true, force: true });
}

/** Returns the executable of the Kigumi-named copy of Electron's bundle, making it if needed. */
function macBundle() {
    const source = path.resolve(electron, '..', '..', '..');
    const version = `${require('electron/package.json').version} (bundle ${BUNDLE_FORMAT})`;
    const bundle = path.join(DEV_DIR, 'Kigumi.app');
    const stamp = path.join(DEV_DIR, 'electron-version');
    const executable = path.join(bundle, 'Contents', 'MacOS', 'Kigumi');
    if (fs.existsSync(executable) && fs.existsSync(stamp) && fs.readFileSync(stamp, 'utf8') === version) {
        return executable;
    }
    fs.rmSync(bundle, { recursive: true, force: true });
    fs.rmSync(stamp, { force: true });
    fs.mkdirSync(DEV_DIR, { recursive: true });
    try {
        run('cp', ['-cR', source, bundle]); // a clone on APFS: no copying
    } catch (_error) {
        run('cp', ['-R', source, bundle]);
    }
    // The name macOS shows a process by is its executable's; Electron finds its helpers by that name.
    const plist = path.join(bundle, 'Contents', 'Info.plist');
    fs.renameSync(path.join(bundle, 'Contents', 'MacOS', 'Electron'), executable);
    setPlist(plist, 'CFBundleExecutable', 'Kigumi');
    setPlist(plist, 'CFBundleName', 'Kigumi');
    setPlist(plist, 'CFBundleDisplayName', 'Kigumi');
    setPlist(plist, 'CFBundleIdentifier', 'com.minimaple.kigumi.dev');
    const frameworks = path.join(bundle, 'Contents', 'Frameworks');
    for (const helper of fs.readdirSync(frameworks).filter((name) => /^Electron Helper.*\.app$/.test(name))) {
        const name = helper.replace(/^Electron/, 'Kigumi').replace(/\.app$/, '');
        const renamed = path.join(frameworks, `${name}.app`);
        fs.renameSync(path.join(frameworks, helper), renamed);
        fs.renameSync(path.join(renamed, 'Contents', 'MacOS', helper.replace(/\.app$/, '')), path.join(renamed, 'Contents', 'MacOS', name));
        const helperPlist = path.join(renamed, 'Contents', 'Info.plist');
        setPlist(helperPlist, 'CFBundleExecutable', name);
        setPlist(helperPlist, 'CFBundleName', name);
    }
    // kigumi:// links (sign-in coming back from the browser) open this copy; macOS reads the schemes
    // an app claims from its bundle only.
    for (const command of ['Add :CFBundleURLTypes array', 'Add :CFBundleURLTypes:0 dict',
        'Add :CFBundleURLTypes:0:CFBundleURLName string Kigumi', 'Add :CFBundleURLTypes:0:CFBundleURLSchemes array',
        'Add :CFBundleURLTypes:0:CFBundleURLSchemes:0 string kigumi']) {
        run('/usr/libexec/PlistBuddy', ['-c', command, plist]);
    }
    replaceIcon(path.join(bundle, 'Contents', 'Resources'));
    // The edits break the bundle's signature, which Apple silicon won't run without.
    run('codesign', ['--force', '--deep', '--sign', '-', bundle]);
    run(LSREGISTER, ['-f', bundle]);
    fs.writeFileSync(stamp, version);
    return executable;
}

let executable = electron;
if (process.platform === 'darwin') {
    try {
        executable = macBundle();
    } catch (error) {
        console.warn(`[app:start] Running Electron as it is; could not make the Kigumi bundle: ${error.message}`);
    }
}

const child = spawn(executable, [path.join(ROOT, 'hosts', 'electron', 'main.js'), ...process.argv.slice(2)], {
    stdio: 'inherit',
    cwd: ROOT,
});
child.on('exit', (code, signal) => process.exit(signal ? 1 : code));
for (const signal of ['SIGINT', 'SIGTERM']) {
    process.on(signal, () => child.kill(signal));
}
