# Agent panel: features (2026-10-24)

What the built-in agent's panel should do, from what Cursor's agent and Claude Code offer, cut to
what Kigumi needs. The agent is narrow (Kigumi's tools and the project's files, no shell), so
shell sandboxing, subagents and background agents are left out.

## Done

- Streaming replies; tool calls as chips that open to their input and output; the model's
  reasoning in a block that opens.
- What it is doing now (thinking, running a tool, waiting for you), with animated dots.
- Stop; clear the conversation.
- Asking before a tool that changes something; a bypass in the panel's settings, shown as a warning.
- Model picker; each turn's cost; the account's balance.
- A failed turn keeps its steps, so "continue" carries on; a turn cut short says why.
- Only the latest screenshot is resent (each is about a megabyte).
- Open the agent at startup (setting).
- `search_files`; what you are looking at goes with each message; editing a file a view shows
  rebuilds it and says whether it built; prompt-cache marks for Claude models.
- Older tool results cut down (the last 8 kept whole); a conversation past ~100k tokens summarised
  at the start of a turn; a context meter.
- Conversation history, kept per project; the latest comes back when the panel opens.
- Markdown in replies (code blocks with copy).
- Permission modes (ask, edit files without asking, everything) and "always allow" per tool; edits
  shown as diffs; a turn's file changes undone in one click; requests queued while the agent works;
  "try again" after a failure; Esc stops, Up recalls the last request.

## Then: the usual agent panel

10. **@-mentions**: `@file` to attach a file, `@selection` for what is selected in the view.
11. **Paste or drop images** (a sketch, a photo of a joint) into the prompt.
12. **A to-do list** the agent keeps for a long task, shown pinned above the input.
13. **Plan mode**: read-only; the agent proposes, then you let it go ahead.

## Kigumi's own

15. **Build check after an edit**: when a frame file the view shows is edited, refresh the view and
    hand the agent the log's errors without it asking (one step instead of three).
16. **What you are looking at, attached**: the active view and selection go with each message
    (small), so "this" needs no describe_panel step.
17. **Run a frame headless** (build it, return errors and a summary) for files no view shows.
18. **Before/after screenshots** on a chip after an edit that rebuilt a view.

## Sources

- Cursor agent: checkpoints, auto-run modes, to-do list, queued messages, summarizing at the
  context limit (cursor.com/help/ai-features/agent, cursor.com/docs/agent/overview).
- Claude Code: permission modes, plan mode, checkpoints and /rewind, /compact, /context, /resume,
  @-mentions (code.claude.com/docs/en/vs-code, support.claude.com Claude Code cheatsheet).
