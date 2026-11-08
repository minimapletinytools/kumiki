/**
 * Installing an update in place (electron-updater): download the new app, then restart into it.
 *
 * update-check.js finds the newest kigumi release; this reads that release's update file
 * (latest-mac.yml, latest.yml) straight from its downloads, rather than letting electron-updater
 * find "the latest release", which in this repository may be kumiki's. The Mac installs from the
 * signed .zip, Windows from the setup .exe. Elsewhere, and where a release has no update file,
 * there is nothing to install from: the caller sends the user to the download instead.
 */

const RELEASE_DOWNLOADS = 'https://github.com/minimapletinytools/kumiki/releases/download';

/** The update file electron-updater reads on this platform, or null where it can't install. */
function updateFileName(platform) {
    if (platform === 'darwin') return 'latest-mac.yml';
    if (platform === 'win32') return 'latest.yml';
    return null;
}

/**
 * @param {object} options
 * @param {object} options.autoUpdater  electron-updater's
 * @param {boolean} options.packaged  app.isPackaged: a dev run has nothing to replace
 * @param {string} options.platform
 * @param {(line: string) => void} [options.log]
 */
function createAutoInstaller({ autoUpdater, packaged, platform, log = () => {} }) {
    let downloading = null;
    autoUpdater.autoDownload = false;
    // Downloaded but not restarted yet: it goes in when the app next quits.
    autoUpdater.autoInstallOnAppQuit = true;
    autoUpdater.logger = { info: (text) => log(`[update] ${text}`), warn: (text) => log(`[update] [warn] ${text}`),
        error: (text) => log(`[update] [error] ${text}`), debug: () => {} };

    /** Whether `release` (update-check.js's) can be installed here, in place. */
    function canInstall(release) {
        const file = updateFileName(platform);
        return Boolean(packaged && file && release && release.assets.some((asset) => asset.name === file));
    }

    /**
     * Download `release`, calling `onProgress(percent)` as it comes; resolves once it is ready to
     * install (restart()). Rejects if it can't, e.g. offline.
     */
    function download(release, { onProgress = () => {} } = {}) {
        if (downloading) return downloading;
        autoUpdater.setFeedURL({ provider: 'generic', url: `${RELEASE_DOWNLOADS}/${release.tag}` });
        const progress = (info) => onProgress(Math.round(info.percent || 0));
        autoUpdater.on('download-progress', progress);
        downloading = (async () => {
            const found = await autoUpdater.checkForUpdates();
            if (!found || !found.isUpdateAvailable) {
                throw new Error(`${release.tag} has nothing newer to install than this app.`);
            }
            await autoUpdater.downloadUpdate();
        })().finally(() => {
            autoUpdater.removeListener('download-progress', progress);
        });
        downloading.catch(() => { downloading = null; });
        return downloading;
    }

    /** Quit and start the downloaded version (Windows: its installer, without asking again). */
    function restart() {
        autoUpdater.quitAndInstall(platform === 'win32', true);
    }

    return { canInstall, download, restart };
}

module.exports = { createAutoInstaller, updateFileName, RELEASE_DOWNLOADS };
