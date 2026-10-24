/**
 * A small key-value store for the account's session, encrypted with the OS keychain's key
 * (Electron safeStorage) in one file. Where the OS offers no encryption it keeps nothing on disk,
 * so signing in lasts until the app quits.
 */

const fs = require('fs');
const path = require('path');

class SecureStorage {
    constructor(filePath, safeStorage, log = () => {}) {
        this.filePath = filePath;
        this.safeStorage = safeStorage;
        this.persist = safeStorage.isEncryptionAvailable();
        this.values = {};
        if (!this.persist) {
            log('[account] no OS encryption available; the sign-in is kept for this run only');
        } else if (fs.existsSync(filePath)) {
            try {
                this.values = JSON.parse(safeStorage.decryptString(fs.readFileSync(filePath)));
            } catch (error) {
                log(`[account] could not read the saved sign-in: ${error.message}`);
            }
        }
    }

    getItem(key) {
        return Object.prototype.hasOwnProperty.call(this.values, key) ? this.values[key] : null;
    }

    setItem(key, value) {
        this.values[key] = value;
        this.save();
    }

    removeItem(key) {
        delete this.values[key];
        this.save();
    }

    save() {
        if (!this.persist) return;
        fs.mkdirSync(path.dirname(this.filePath), { recursive: true });
        fs.writeFileSync(this.filePath, this.safeStorage.encryptString(JSON.stringify(this.values)), { mode: 0o600 });
    }
}

module.exports = { SecureStorage };
