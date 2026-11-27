const { unprivilegedNamespacesAllowed } = require('../hosts/electron/linux-sandbox');

const reading = (values) => (file) => {
    if (!(file in values)) throw new Error(`ENOENT: ${file}`);
    return values[file];
};

test('user namespaces are allowed unless a kernel switch forbids them', () => {
    expect(unprivilegedNamespacesAllowed(reading({}))).toBe(true);
    expect(unprivilegedNamespacesAllowed(reading({ '/proc/sys/kernel/apparmor_restrict_unprivileged_userns': '0\n' }))).toBe(true);
    expect(unprivilegedNamespacesAllowed(reading({ '/proc/sys/kernel/apparmor_restrict_unprivileged_userns': '1\n' }))).toBe(false);
    expect(unprivilegedNamespacesAllowed(reading({ '/proc/sys/kernel/unprivileged_userns_clone': '0\n' }))).toBe(false);
    expect(unprivilegedNamespacesAllowed(reading({ '/proc/sys/kernel/unprivileged_userns_clone': '1\n' }))).toBe(true);
});
