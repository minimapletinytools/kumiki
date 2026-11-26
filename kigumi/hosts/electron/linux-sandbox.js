/**
 * Whether this Linux system lets an unprivileged process make user namespaces, which Chromium's
 * sandbox needs when it has no setuid helper (an AppImage). Ubuntu 23.10 on restricts them through
 * AppArmor; older kernels could turn them off. Unknown counts as allowed: the sandbox stays on.
 */

const fs = require('fs');

const SWITCHES = [
    // 1 restricts them (Ubuntu's AppArmor).
    { file: '/proc/sys/kernel/apparmor_restrict_unprivileged_userns', forbidden: '1' },
    // 0 turns them off (Debian's and older Ubuntu kernels).
    { file: '/proc/sys/kernel/unprivileged_userns_clone', forbidden: '0' },
];

function unprivilegedNamespacesAllowed(readFile = (file) => fs.readFileSync(file, 'utf8')) {
    for (const { file, forbidden } of SWITCHES) {
        let value;
        try {
            value = String(readFile(file)).trim();
        } catch {
            continue;
        }
        if (value === forbidden) return false;
    }
    return true;
}

module.exports = { unprivilegedNamespacesAllowed };
