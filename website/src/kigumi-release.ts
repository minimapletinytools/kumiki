// The Kigumi release the download links point at: the newest kigumi-v* tag, the same one /try is
// built from. release.yml redeploys the site once a release's installers are attached.
import { execSync } from 'node:child_process';
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';

function latestTag(): string | null {
  try {
    const tag = execSync("git tag --list 'kigumi-v*' --sort=-v:refname", { encoding: 'utf8' }).split('\n')[0].trim();
    return tag || null;
  } catch {
    return null;
  }
}

// Without tags (a shallow checkout), the version in kigumi/package.json.
function packageVersion(): string {
  return JSON.parse(readFileSync(resolve(process.cwd(), '../kigumi/package.json'), 'utf8')).version;
}

export const kigumiVersion: string = latestTag()?.replace(/^kigumi-v/, '') ?? packageVersion();
const downloads = `https://github.com/minimapletinytools/kumiki/releases/download/kigumi-v${kigumiVersion}`;

export const releasePage = `https://github.com/minimapletinytools/kumiki/releases/tag/kigumi-v${kigumiVersion}`;
export const appDownloads = {
  macArm: `${downloads}/Kigumi-${kigumiVersion}-mac-arm64.dmg`,
  macIntel: `${downloads}/Kigumi-${kigumiVersion}-mac-x64.dmg`,
  windows: `${downloads}/Kigumi-${kigumiVersion}-windows-setup.exe`,
};
export const marketplace = 'https://marketplace.visualstudio.com/items?itemName=minimaple.kigumi';
export const openVsx = 'https://open-vsx.org/extension/minimaple/kigumi';
