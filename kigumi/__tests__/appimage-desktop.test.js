const fs = require('fs');
const os = require('os');
const path = require('path');
const { registerAppImage, quoteExec, DESKTOP_FILE } = require('../hosts/electron/appimage-desktop');

test('an Exec path is quoted, with the characters a desktop entry reads specially escaped', () => {
    expect(quoteExec('/home/a b/Kigumi.AppImage')).toBe('"/home/a b/Kigumi.AppImage"');
    expect(quoteExec('/x/$a"b`c\\d')).toBe('"/x/\\$a\\"b\\`c\\\\d"');
});

test('an AppImage writes its own desktop entry and makes it the kigumi:// handler', () => {
    const home = fs.mkdtempSync(path.join(os.tmpdir(), 'kigumi-home-'));
    const iconSource = path.join(home, 'icon.png');
    fs.writeFileSync(iconSource, 'png');
    const ran = [];
    registerAppImage({ appImage: '/opt/my apps/Kigumi.AppImage', iconSource, home, run: (cmd, args, done) => { ran.push([cmd, ...args]); done(null); } });
    const entry = fs.readFileSync(path.join(home, '.local/share/applications', DESKTOP_FILE), 'utf8');
    expect(entry).toContain('Exec="/opt/my apps/Kigumi.AppImage" %U');
    expect(entry).toContain('MimeType=x-scheme-handler/kigumi;');
    expect(entry).toContain(`Icon=${path.join(home, '.local/share/icons/kigumi-appimage.png')}`);
    expect(fs.readFileSync(path.join(home, '.local/share/icons/kigumi-appimage.png'), 'utf8')).toBe('png');
    expect(ran[0]).toEqual(['xdg-mime', 'default', DESKTOP_FILE, 'x-scheme-handler/kigumi']);
});

test('a failure to register is logged, not thrown', () => {
    const lines = [];
    registerAppImage({ appImage: '/a', home: '/dev/null/nowhere', run: () => {}, log: (line) => lines.push(line) });
    expect(lines.length).toBe(1);
});
