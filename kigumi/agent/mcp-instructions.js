/** Introduce Kigumi and its authoring tools to external MCP agents. */

const MCP_INSTRUCTIONS = [
    'Kigumi shows timber frames written in Python with the kumiki library.',
    'Before writing or changing a frame, read kumiki_source "docs/agent_usage_instructions.md" (the rules) and "docs/api_cheat_sheet.md".',
    'Check a function\'s exact signature with kumiki_api rather than guessing.',
    'kumiki_source also reads and searches kumiki\'s source and its example frames.',
    'After an edit, build the frame with check_frame and see where its timbers ended up with describe; describe with a timber lists the feature names to measure in a drawing.',
].join(' ');

module.exports = { MCP_INSTRUCTIONS };
