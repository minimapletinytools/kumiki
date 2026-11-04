const { createUpdateChecker, downloadUrl, isNewer, newestRelease } = require('../hosts/electron/update-check');

function release(tag, extra = {}) {
    return {
        tag_name: tag,
        html_url: `https://github.com/minimapletinytools/kumiki/releases/tag/${tag}`,
        assets: [
            { name: `Kigumi-${tag.replace(/^\w+-v/, '')}-mac-arm64.dmg`, browser_download_url: `https://dl/${tag}/mac-arm64.dmg` },
            { name: `Kigumi-${tag.replace(/^\w+-v/, '')}-windows-setup.exe`, browser_download_url: `https://dl/${tag}/setup.exe` },
        ],
        ...extra,
    };
}

function memorySettings(values = {}) {
    return { get: (key, fallback) => (key in values ? values[key] : fallback), set: (key, value) => { values[key] = value; } };
}

describe('newestRelease', () => {
    test('counts only kigumi releases, and not drafts or prereleases', () => {
        const releases = [
            release('kumiki-v9.0.0'),
            release('kigumi-v0.9.0', { draft: true }),
            release('kigumi-v0.8.2', { prerelease: true }),
            release('kigumi-v0.8.1'),
            release('kigumi-v0.8.0'),
        ];

        expect(newestRelease(releases).version).toBe('0.8.1');
        expect(newestRelease(releases, { prereleases: true }).version).toBe('0.8.2');
    });

    test('compares versions as numbers', () => {
        expect(newestRelease([release('kigumi-v0.9.0'), release('kigumi-v0.10.0')]).version).toBe('0.10.0');
        expect(isNewer('0.10.0', '0.9.9')).toBe(true);
        expect(isNewer('0.9.0', '0.9.0')).toBe(false);
    });

    test('finds nothing in an answer that is not a list', () => {
        expect(newestRelease({ message: 'rate limited' })).toBeNull();
    });
});

describe('downloadUrl', () => {
    const newest = newestRelease([release('kigumi-v0.9.0')]);

    test('picks the file for this platform and arch', () => {
        expect(downloadUrl(newest, 'darwin', 'arm64')).toBe('https://dl/kigumi-v0.9.0/mac-arm64.dmg');
        expect(downloadUrl(newest, 'win32', 'x64')).toBe('https://dl/kigumi-v0.9.0/setup.exe');
    });

    test('falls back to the release page', () => {
        expect(downloadUrl(newest, 'darwin', 'x64')).toBe(newest.page);
        expect(downloadUrl(newest, 'linux', 'x64')).toBe(newest.page);
    });
});

describe('createUpdateChecker', () => {
    const fetchReleases = async () => [release('kigumi-v0.9.0'), release('kigumi-v0.8.0')];

    test('a newer release is available, and onChange hears of it', async () => {
        const onChange = jest.fn();
        const updates = createUpdateChecker({ currentVersion: '0.8.0', settings: memorySettings(), fetchReleases, onChange });

        await updates.check();

        expect(updates.available.version).toBe('0.9.0');
        expect(onChange).toHaveBeenCalledTimes(1);
    });

    test('the newest one being this one is no update', async () => {
        const updates = createUpdateChecker({ currentVersion: '0.9.0', settings: memorySettings(), fetchReleases });

        expect(await updates.check()).toBeNull();
        expect(updates.available).toBeNull();
    });

    test('a skipped version is not offered again, except to a manual check', async () => {
        const settings = memorySettings();
        const updates = createUpdateChecker({ currentVersion: '0.8.0', settings, fetchReleases });
        await updates.check();

        updates.skip('0.9.0');

        expect(updates.available).toBeNull();
        expect(settings.get('app.skippedUpdateVersion')).toBe('0.9.0');
        await updates.check();
        expect(updates.available).toBeNull();
        await updates.check({ manual: true });
        expect(updates.available.version).toBe('0.9.0');
    });

    test('a failed automatic check only logs; a manual one says so', async () => {
        const log = jest.fn();
        const failing = async () => { throw new Error('offline'); };
        const updates = createUpdateChecker({ currentVersion: '0.8.0', settings: memorySettings(), fetchReleases: failing, log });

        expect(await updates.check()).toBeNull();
        expect(log).toHaveBeenCalledWith(expect.stringContaining('offline'));
        await expect(updates.check({ manual: true })).rejects.toThrow('offline');
    });

    test('a dev build does not look on its own', async () => {
        const fetch = jest.fn(fetchReleases);
        const updates = createUpdateChecker({ currentVersion: '999.0.0', settings: memorySettings(), fetchReleases: fetch });

        expect(await updates.check()).toBeNull();
        expect(fetch).not.toHaveBeenCalled();
    });

    test('start looks after a delay and then daily, unless turned off', () => {
        jest.useFakeTimers();
        try {
            const fetch = jest.fn(fetchReleases);
            const settings = memorySettings();
            const updates = createUpdateChecker({ currentVersion: '0.8.0', settings, fetchReleases: fetch });

            updates.start();
            jest.advanceTimersByTime(10 * 1000);
            jest.advanceTimersByTime(24 * 60 * 60 * 1000);
            expect(fetch).toHaveBeenCalledTimes(2);

            settings.set('app.checkForUpdates', false);
            updates.start();
            jest.advanceTimersByTime(2 * 24 * 60 * 60 * 1000);
            expect(fetch).toHaveBeenCalledTimes(2);
        } finally {
            jest.useRealTimers();
        }
    });
});
