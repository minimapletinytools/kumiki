/**
 * The built-in agent's instructions, from agent/system-prompt.md, for hosts with a file system.
 * Returns the function AgentSession takes as `systemPrompt`.
 */

const fs = require('fs');
const path = require('path');

const FILE = path.join(__dirname, 'system-prompt.md');

/**
 * `markdown` as (kumikiSource, kumikiExamples) => the system prompt: its comments left out, the part
 * after "---" only with a source (its {kumikiSource} and {kumikiExamples} filled in), and joined into one line, which models followed better than the file's line breaks
 * (DeepSeek, asked for an opinion, made 1 tool call each time joined, 1 to 8 with them).
 */
function systemPromptFrom(markdown) {
    const [base, withSource = ''] = markdown.replace(/<!--[\s\S]*?-->/g, '').split(/^---$/m)
        .map((part) => part.replace(/\s+/g, ' ').trim());
    return (kumikiSource, kumikiExamples = null) => (kumikiSource && withSource
        ? `${base} ${withSource.split('{kumikiSource}').join(kumikiSource).split('{kumikiExamples}').join(kumikiExamples || `${kumikiSource}/patterns`)}`
        : base);
}

function loadSystemPrompt(file = FILE) {
    return systemPromptFrom(fs.readFileSync(file, 'utf8'));
}

module.exports = { loadSystemPrompt, systemPromptFrom };
