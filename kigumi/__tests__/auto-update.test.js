const { EventEmitter } = require('events');
const { createAutoInstaller, RELEASE_DOWNLOADS } = require('../hosts/electron/auto-update');

/** electron-updater's autoUpdater, as much as auto-update.js uses. */
function fakeUpdater({ available = true, failDownload = null } = {}) {
    const updater = new EventEmitter();
    updater.feeds = [];
    updater.installs = [];
    updater.setFeedURL = (feed) => updater.feeds.push(feed);
    updater.checkForUpdates = async () => ({ isUpdateAvailable: available });
    updater.downloadUpdate = async () => {
        updater.emit('download-progress', { percent: 41.6 });
        if (failDownload) throw failDownload;
        updater.emit('download-progress', { percent: 100 });
    };
    updater.quitAndInstall = (silent, runAfter) => updater.installs.push({ silent, runAfter });
    return updater;
}

const release = (names) => ({ version: '0.9.2', tag: 'kigumi-v0.9.2', assets: names.map((name) => ({ name, url: `https://x/${name}` })) });

describe('installing an update in place', () => {
    test('the Mac and Windows install from a release with their update file; a dev run and Linux do not', () => {
        const withBoth = release(['latest-mac.yml', 'latest.yml']);
        const make = (options) => createAutoInstaller({ autoUpdater: fakeUpdater(), packaged: true, ...options });
        expect(make({ platform: 'darwin' }).canInstall(withBoth)).toBe(true);
        expect(make({ platform: 'win32' }).canInstall(withBoth)).toBe(true);
        expect(make({ platform: 'linux' }).canInstall(withBoth)).toBe(false);
        expect(make({ platform: 'darwin', packaged: false }).canInstall(withBoth)).toBe(false);
        // A release from before the app updated itself has installers only.
        expect(make({ platform: 'darwin' }).canInstall(release(['Kigumi-0.9.1-mac-arm64.dmg']))).toBe(false);
        expect(make({ platform: 'win32' }).canInstall(release(['latest-mac.yml']))).toBe(false);
    });

    test('it reads that release\'s own downloads, not "the latest release", and reports progress', async () => {
        const updater = fakeUpdater();
        const installer = createAutoInstaller({ autoUpdater: updater, packaged: true, platform: 'darwin' });
        expect(updater.autoDownload).toBe(false);
        expect(updater.autoInstallOnAppQuit).toBe(true);
        const seen = [];
        await installer.download(release(['latest-mac.yml']), { onProgress: (percent) => seen.push(percent) });
        expect(updater.feeds).toEqual([{ provider: 'generic', url: `${RELEASE_DOWNLOADS}/kigumi-v0.9.2` }]);
        expect(seen).toEqual([42, 100]);
        expect(updater.listenerCount('download-progress')).toBe(0);
    });

    test('a release with nothing newer, or a failed download, rejects; trying again starts over', async () => {
        const nothing = createAutoInstaller({ autoUpdater: fakeUpdater({ available: false }), packaged: true, platform: 'darwin' });
        await expect(nothing.download(release(['latest-mac.yml']))).rejects.toThrow('nothing newer');

        const updater = fakeUpdater({ failDownload: new Error('offline') });
        const installer = createAutoInstaller({ autoUpdater: updater, packaged: true, platform: 'win32' });
        await expect(installer.download(release(['latest.yml']))).rejects.toThrow('offline');
        updater.downloadUpdate = async () => {};
        await expect(installer.download(release(['latest.yml']))).resolves.toBeUndefined();
        expect(updater.feeds).toHaveLength(2);
    });

    test('restarting installs it: silently on Windows (the installer was agreed to), and runs the app after', () => {
        const mac = fakeUpdater();
        createAutoInstaller({ autoUpdater: mac, packaged: true, platform: 'darwin' }).restart();
        const windows = fakeUpdater();
        createAutoInstaller({ autoUpdater: windows, packaged: true, platform: 'win32' }).restart();
        expect(mac.installs).toEqual([{ silent: false, runAfter: true }]);
        expect(windows.installs).toEqual([{ silent: true, runAfter: true }]);
    });
});
