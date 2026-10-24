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

## Next: fixes what has been hit

1. **A `search_files` tool** (grep over the project, with line numbers). The agent read whole
   files to find things, and every read is resent with every later step: searching is far cheaper.
2. **Context meter and auto-compaction.** Show how full the conversation is; when it passes a
   threshold, summarize older steps and continue, keeping the latest request word for word. Long
   turns grew to 2.5 MB.
3. **Conversation history**, kept locally per project: reopen, rename, delete; the last one comes
   back after a restart. In the backend later, with cloud projects (kigumi-backend plan
   `cloud-projects.md`).
4. **Markdown in replies**: code blocks with copy, lists, links to files that open them.

## Then: the usual agent panel

5. **Permission modes** in place of one bypass: *Ask*, *Allow edits* (file writes without asking;
   camera and other changes still ask), *Allow all*; and per tool "always allow".
6. **Edits shown as diffs** in the permission card and the chip, not the raw input.
7. **Checkpoints and undo**: before each turn's first edit, keep the files it touches; "Restore"
   on a message rolls the project's files back to before it.
8. **Queued messages**: type the next request while the agent works; it runs when the turn ends.
9. **Edit and resend, retry** the last message.
10. **@-mentions**: `@file` to attach a file, `@selection` for what is selected in the view.
11. **Paste or drop images** (a sketch, a photo of a joint) into the prompt.
12. **A to-do list** the agent keeps for a long task, shown pinned above the input.
13. **Plan mode**: read-only; the agent proposes, then you let it go ahead.
14. **Keyboard**: Esc stops, Cmd+Enter sends, Up recalls the last message.

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
