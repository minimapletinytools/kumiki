/**
 * Checking for a newer Kigumi app release on GitHub.
 *
 * Only `kigumi-v*` releases count: kumiki's releases live in the same repository. The checker
 * looks on start and then once a day, and keeps the newest release newer than this app (unless
 * that version was skipped) as `available`.
 */

const RELEASES_URL = 'https://api.github.com/repos/minimapletinytools/kumiki/releases?per_page=30';
const RELEASES_PAGE = 'https://github.com/minimapletinytools/kumiki/releases';
const DAY_MS = 24 * 60 * 60 * 1000;
const FIRST_CHECK_DELAY_MS = 10 * 1000;
const TAG = /^kigumi-v(\d+)\.(\d+)\.(\d+)$/;

/** Return [major, minor, patch] of "1.2.3", or null. */
function parseVersion(version) {
    const match = /^(\d+)\.(\d+)\.(\d+)$/.exec(String(version || ''));
    return match ? match.slice(1).map(Number) : null;
}

/** Whether version `a` is newer than version `b`. */
function isNewer(a, b) {
    const left = parseVersion(a);
    const right = parseVersion(b);
    if (!left || !right) return false;
    for (let i = 0; i < 3; i += 1) {
        if (left[i] !== right[i]) return left[i] > right[i];
    }
    return false;
}

/** A local dev build, which install.sh stamps 999.0.0. It never looks for updates. */
function isDevVersion(version) {
    const parsed = parseVersion(version);
    return !parsed || parsed[0] >= 999 || parsed[1] >= 999;
}

/** Return the newest kigumi release in GitHub's release list, or null. Drafts never count. */
function newestRelease(releases, { prereleases = false } = {}) {
    let newest = null;
    for (const release of Array.isArray(releases) ? releases : []) {
        const match = release && !release.draft && TAG.exec(release.tag_name || '');
        if (!match || (release.prerelease && !prereleases)) continue;
        const version = match.slice(1).join('.');
        if (!newest || isNewer(version, newest.version)) {
            newest = {
                version,
                tag: release.tag_name,
                page: release.html_url || `${RELEASES_PAGE}/tag/${release.tag_name}`,
                assets: (release.assets || []).map((asset) => ({ name: asset.name, url: asset.browser_download_url })),
            };
        }
    }
    return newest;
}

/** Return the download URL for this platform and arch, or the release page when none matches. */
function downloadUrl(release, platform, arch) {
    const suffix = platform === 'darwin' ? `-mac-${arch}.dmg` : platform === 'win32' ? '-windows-setup.exe' : null;
    const asset = suffix && release.assets.find((candidate) => candidate.name.endsWith(suffix));
    return asset ? asset.url : release.page;
}

/**
 * Create the checker. `fetchReleases()` resolves GitHub's release list; `onChange()` is called when
 * `available` changes. Settings: `app.checkForUpdates`, `app.updatePrereleases`,
 * `app.skippedUpdateVersion`.
 */
function createUpdateChecker({ currentVersion, settings, fetchReleases, onChange = () => {}, log = () => {} }) {
    let available = null;
    let timer = null;
    let firstTimer = null;

    function setAvailable(release) {
        const changed = (available && available.version) !== (release && release.version);
        available = release;
        if (changed) onChange(available);
    }

    /**
     * Look for a newer release and return it, or null. A manual check also finds a skipped version
     * and reports failures by rejecting; an automatic one only logs them.
     */
    async function check({ manual = false } = {}) {
        if (isDevVersion(currentVersion) && !manual) return null;
        let releases;
        try {
            releases = await fetchReleases();
        } catch (error) {
            log(`[update] [warn] Could not check for updates: ${error.message || error}`);
            if (manual) throw error;
            return null;
        }
        const newest = newestRelease(releases, { prereleases: settings.get('app.updatePrereleases', false) === true });
        const newer = newest && isNewer(newest.version, currentVersion) ? newest : null;
        const skipped = settings.get('app.skippedUpdateVersion', '');
        const shown = newer && (manual || newer.version !== skipped) ? newer : null;
        log(`[update] Latest kigumi release ${newest ? newest.version : '(none)'}; this is ${currentVersion}`
            + (newer && !shown ? `; ${newer.version} was skipped` : ''));
        setAvailable(shown);
        return newer;
    }

    /** Check shortly after start and then once a day, while `app.checkForUpdates` is on. */
    function start() {
        stop();
        if (settings.get('app.checkForUpdates', true) === false || isDevVersion(currentVersion)) return;
        firstTimer = setTimeout(() => void check(), FIRST_CHECK_DELAY_MS);
        timer = setInterval(() => void check(), DAY_MS);
    }

    function stop() {
        clearTimeout(firstTimer);
        clearInterval(timer);
        firstTimer = null;
        timer = null;
    }

    /** Stop offering `version` until a newer one comes out. */
    function skip(version) {
        settings.set('app.skippedUpdateVersion', version);
        if (available && available.version === version) setAvailable(null);
    }

    return {
        check,
        start,
        stop,
        skip,
        get available() { return available; },
        /** For tests: show `release` as available. */
        setAvailable,
    };
}

module.exports = {
    RELEASES_URL,
    createUpdateChecker,
    downloadUrl,
    isDevVersion,
    isNewer,
    newestRelease,
    parseVersion,
};
