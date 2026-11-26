/**
 * An AppImage is one loose file, so nothing tells the desktop it opens kigumi:// links (sign-in
 * coming back from the browser). It says so itself, on each launch: a desktop entry of its own in
 * ~/.local/share/applications that runs this file, made the scheme's handler. Rewritten every
 * time, so a moved AppImage is found where it now is.
 */

const fs = require('fs');
const os = require('os');
const path = require('path');
const { execFile } = require('child_process');

const DESKTOP_FILE = 'kigumi-appimage.desktop';
const SCHEME = 'x-scheme-handler/kigumi';

/** A path quoted for a desktop entry's Exec line. */
function quoteExec(file) {
    return `"${file.replace(/[\\"`$]/g, (char) => `\\${char}`)}"`;
}

/** The desktop entry that runs `appImage`, with `icon` (a path) as its icon. */
function desktopEntry(appImage, icon) {
    return [
        '[Desktop Entry]',
        'Type=Application',
        'Name=Kigumi',
        'Comment=Interactive 3D viewer and CAD environment for Kumiki timber framing and woodworking joinery in Python',
        'StartupWMClass=Kigumi',
        `Exec=${quoteExec(appImage)} %U`,
        `Icon=${icon}`,
        'Terminal=false',
        'Categories=Graphics;',
        `MimeType=${SCHEME};`,
        '',
    ].join('\n');
}

/**
 * Write the entry (and the icon beside it, as the AppImage's own folder goes when it quits) and make
 * it the scheme's handler. Failures are logged, never thrown: the app works without it.
 */
function registerAppImage({ appImage, iconSource, home = os.homedir(), run = execFile, log = () => {} }) {
    try {
        const share = path.join(home, '.local', 'share');
        const applications = path.join(share, 'applications');
        const icon = path.join(share, 'icons', 'kigumi-appimage.png');
        fs.mkdirSync(applications, { recursive: true });
        fs.mkdirSync(path.dirname(icon), { recursive: true });
        if (iconSource && fs.existsSync(iconSource)) fs.copyFileSync(iconSource, icon);
        fs.writeFileSync(path.join(applications, DESKTOP_FILE), desktopEntry(appImage, icon));
        run('xdg-mime', ['default', DESKTOP_FILE, SCHEME], (error) => {
            if (error) log(`[linux] could not make Kigumi the kigumi:// handler: ${error.message}`);
        });
        run('update-desktop-database', [applications], () => {});
    } catch (error) {
        log(`[linux] could not write Kigumi's desktop entry: ${error.message}`);
    }
}

module.exports = { registerAppImage, desktopEntry, quoteExec, DESKTOP_FILE };
