const fs = require('fs');
const os = require('os');
const path = require('path');

const { normalizeRetentionDays, pruneOldLogFiles } = require('../log-retention');

describe('log-retention', () => {
  let tmpRoot;

  beforeEach(() => {
    tmpRoot = fs.mkdtempSync(path.join(os.tmpdir(), 'kigumi-log-retention-'));
  });

  afterEach(() => {
    if (tmpRoot && fs.existsSync(tmpRoot)) {
      fs.rmSync(tmpRoot, { recursive: true, force: true });
    }
  });

  test('normalizeRetentionDays clamps invalid values to fallback or zero', () => {
    expect(normalizeRetentionDays(undefined)).toBe(15);
    expect(normalizeRetentionDays(9.9)).toBe(9);
    expect(normalizeRetentionDays(-4)).toBe(0);
  });

  test('pruneOldLogFiles removes files older than retention window', () => {
    const logsDir = path.join(tmpRoot, '.kigumi', 'logs');
    fs.mkdirSync(logsDir, { recursive: true });

    const oldLogPath = path.join(logsDir, 'old.jsonl');
    const newLogPath = path.join(logsDir, 'new.jsonl');
    fs.writeFileSync(oldLogPath, '{"old":true}\n', 'utf8');
    fs.writeFileSync(newLogPath, '{"new":true}\n', 'utf8');

    const sixteenDaysAgo = new Date(Date.now() - (16 * 24 * 60 * 60 * 1000));
    const twoDaysAgo = new Date(Date.now() - (2 * 24 * 60 * 60 * 1000));
    fs.utimesSync(oldLogPath, sixteenDaysAgo, sixteenDaysAgo);
    fs.utimesSync(newLogPath, twoDaysAgo, twoDaysAgo);

    const result = pruneOldLogFiles(tmpRoot, 15);
    expect(result.scannedFiles).toBe(2);
    expect(result.removedFiles).toContain(oldLogPath);
    expect(fs.existsSync(oldLogPath)).toBe(false);
    expect(fs.existsSync(newLogPath)).toBe(true);
  });
});