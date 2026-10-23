// The app's settings: auto refresh on by default, and settings.json edited by hand applies at once.

const fs = require('fs');

module.exports = {
    name: 'settings',
    async run({ check, waitFor, settings }) {
        check('auto refresh defaults to on in the app', settings.get('viewer.autoRefreshOnFileChange') === true);
        const edited = { ...JSON.parse(fs.readFileSync(settings.filePath, 'utf8')), 'viewer.autoRefreshOnFileChange': false };
        fs.writeFileSync(settings.filePath, JSON.stringify(edited, null, 2));
        const applied = await waitFor(() => settings.get('viewer.autoRefreshOnFileChange') === false, { timeoutMs: 5000 })
            .then(() => true, () => false);
        check('editing settings.json applies without a restart', applied);
    },
};
