const { MAX_RECENT_FOLDERS, withRecentFolder, offeredRecentFolders } = require('../hosts/electron/recent-folders');

describe('withRecentFolder', () => {
    test('puts the folder first, once', () => {
        expect(withRecentFolder(['/a', '/b', '/c'], '/b')).toEqual(['/b', '/a', '/c']);
        expect(withRecentFolder([], '/a')).toEqual(['/a']);
    });

    test('keeps the newest few', () => {
        const many = Array.from({ length: MAX_RECENT_FOLDERS }, (_, i) => `/f${i}`);
        const list = withRecentFolder(many, '/new');
        expect(list).toHaveLength(MAX_RECENT_FOLDERS);
        expect(list[0]).toBe('/new');
        expect(list).not.toContain(`/f${MAX_RECENT_FOLDERS - 1}`);
    });

    test('a hand-edited setting that is not a list of paths starts over', () => {
        expect(withRecentFolder('nonsense', '/a')).toEqual(['/a']);
        expect(withRecentFolder([3, null, '/b'], '/a')).toEqual(['/a', '/b']);
    });
});

describe('offeredRecentFolders', () => {
    test('leaves out the open folder and ones that are gone', () => {
        const exists = (folder) => folder !== '/gone';
        expect(offeredRecentFolders(['/open', '/gone', '/projects/shed'], { current: '/open', exists }))
            .toEqual([{ name: 'shed', path: '/projects/shed' }]);
    });
});
