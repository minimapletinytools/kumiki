const fs = require('fs');
const path = require('path');

function normalizeRetentionDays(value, fallback = 15) {
    if (!Number.isFinite(value)) {
        return fallback;
    }
    return Math.max(0, Math.floor(value));
}

function pruneOldLogFiles(workspaceRoot, retentionDays = 15) {
    if (!workspaceRoot || typeof workspaceRoot !== 'string') {
        return { logsDir: null, removedFiles: [], scannedFiles: 0, retentionDays: normalizeRetentionDays(retentionDays) };
    }

    const normalizedRetentionDays = normalizeRetentionDays(retentionDays);
    const logsDir = path.join(workspaceRoot, '.kigumi', 'logs');
    if (!fs.existsSync(logsDir)) {
        return { logsDir, removedFiles: [], scannedFiles: 0, retentionDays: normalizedRetentionDays };
    }

    const cutoffTimeMs = Date.now() - (normalizedRetentionDays * 24 * 60 * 60 * 1000);
    const removedFiles = [];
    let scannedFiles = 0;

    for (const entry of fs.readdirSync(logsDir, { withFileTypes: true })) {
        if (!entry.isFile()) {
            continue;
        }

        const filePath = path.join(logsDir, entry.name);
        scannedFiles += 1;
        const stat = fs.statSync(filePath);
        if (stat.mtimeMs > cutoffTimeMs) {
            continue;
        }

        fs.rmSync(filePath, { force: true });
        removedFiles.push(filePath);
    }

    return {
        logsDir,
        removedFiles,
        scannedFiles,
        retentionDays: normalizedRetentionDays,
    };
}

module.exports = {
    normalizeRetentionDays,
    pruneOldLogFiles,
};