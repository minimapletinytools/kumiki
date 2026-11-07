/**
 * The standalone app's recently opened project folders, newest first, kept in its settings as
 * `app.recentFolders`.
 */

const path = require('path');

const MAX_RECENT_FOLDERS = 10;

/** Return `list` with `folder` moved to the front, at most MAX_RECENT_FOLDERS long. */
function withRecentFolder(list, folder) {
    const others = (Array.isArray(list) ? list : []).filter((one) => typeof one === 'string' && one !== folder);
    return [folder, ...others].slice(0, MAX_RECENT_FOLDERS);
}

/** Return the folders worth offering: still there, and not `current`, as { name, path }. */
function offeredRecentFolders(list, { current = null, exists }) {
    return (Array.isArray(list) ? list : [])
        .filter((one) => typeof one === 'string' && one !== current && exists(one))
        .map((one) => ({ name: path.basename(one), path: one }));
}

module.exports = { MAX_RECENT_FOLDERS, withRecentFolder, offeredRecentFolders };
