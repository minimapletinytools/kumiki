// The app's settings: auto refresh on by default, settings.json edited by hand applies at once, and
// the Language menu, at Default (the system's language).

const fs = require('fs');
const { Menu } = require('electron');

module.exports = {
    name: 'settings',
    async run({ check, waitFor, settings }) {
        check('auto refresh defaults to on in the app', settings.get('viewer.autoRefreshOnFileChange') === true);
        const edited = { ...JSON.parse(fs.readFileSync(settings.filePath, 'utf8')), 'viewer.autoRefreshOnFileChange': false };
        fs.writeFileSync(settings.filePath, JSON.stringify(edited, null, 2));
        const applied = await waitFor(() => settings.get('viewer.autoRefreshOnFileChange') === false, { timeoutMs: 5000 })
            .then(() => true, () => false);
        check('editing settings.json applies without a restart', applied);

        const items = (menu) => (menu ? menu.items.flatMap((item) => [item, ...items(item.submenu)]) : []);
        const language = items(Menu.getApplicationMenu()).find((item) => item.label === 'Language');
        const choices = language ? language.submenu.items.map((item) => `${item.label}${item.checked ? ' *' : ''}`) : [];
        check('the Language menu offers Default (checked), English and 日本語', settings.get('app.language') === 'default'
            && choices.join(', ') === 'Default (system language) *, English, 日本語', choices.join(', '));
    },
};
