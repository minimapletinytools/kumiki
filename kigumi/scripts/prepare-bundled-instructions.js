const fs = require('fs');
const path = require('path');

function stripLeadingYamlFrontmatter(content) {
  if (!content.startsWith('---')) {
    return content;
  }

  const endMarker = content.indexOf('\n---', 3);
  if (endMarker === -1) {
    return content;
  }

  const afterFrontmatterIndex = endMarker + '\n---'.length;
  return content.slice(afterFrontmatterIndex).replace(/^\s+/, '');
}

function main() {
  const extensionRoot = path.resolve(__dirname, '..');
  const sourcePath = path.resolve(extensionRoot, '..', '.github', 'instructions', 'usage.instructions.md');
  const generatedDir = path.resolve(extensionRoot, '.generated');
  const outputPath = path.resolve(generatedDir, 'bundled-usage-instructions.md');

  if (!fs.existsSync(sourcePath)) {
    throw new Error(`Missing source instructions file: ${sourcePath}`);
  }

  const raw = fs.readFileSync(sourcePath, 'utf8');
  const normalized = stripLeadingYamlFrontmatter(raw).trimEnd() + '\n';

  fs.mkdirSync(generatedDir, { recursive: true });
  fs.writeFileSync(outputPath, normalized, 'utf8');

  console.log(`Prepared bundled instructions: ${outputPath}`);
}

main();