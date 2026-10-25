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
- @-mentions (`@file` attaches it, `@selection` what is selected in full); images pasted or dropped
  into the box; a to-do list the agent keeps, pinned above the box; plan mode (proposes, changes
  nothing); `check_frame` (builds a frame, opening a view if none shows it); the view before and
  after an edit, on its chip.

## Next

Everything planned here is in. Ideas from using it go here.

- **`kumiki_api` tool** (not started). Asks the project's Python about a kumiki name rather than
  searching source text: `kumiki_api("create_axis_aligned_timber")` gives the signature (defaults,
  type hints), the docstring, and the file and line; the source on request; `members=True` on a
  module lists what it exports. Exact and short, finds re-exported names (`from kumiki import *`
  hides where they live), and works for any install. Keep the read-only source access alongside,
  for reading an implementation. Why: in a DeepSeek V4.1 Flash session (2026-10-24) the agent
  guessed at `bottom_position` and `front_face_on_butt_timber` for many steps; the docs don't
  give either.

From the same session, most useful first:

1. **Model evals.** A few real tasks (fix a broken frame, build from a description, change a
   joint) run against each model, scored on whether it builds, steps and cost. Picks the default
   model, and shows whether a change helped.
2. **Seeing where timbers are.** A `describe_frame` tool: each timber's world bounding box, and
   whether each joint's timbers touch. kumiki side: warn when a joint's timbers don't meet (the
   sawhorse's leg tenons cut into air, and it built).
3. **kumiki errors that say how to fix them.** "front_face_on_butt_timber must be parallel to the
   joint alignment plane" cost dozens of steps; naming the faces that would work makes it one.
4. **Do what was asked.** Asked for a screenshot and an opinion, it investigated for 40 steps: answer
   questions directly, and ask before investigating or editing unasked.
5. **Guards for small models.** A call repeated with the same arguments is told so (read_file
   without offset, ten times).
6. **Summaries that can't mislead.** A summary said a fixed bug was still there; attach the current
   content of files the conversation changed.
7. **Docs.** concepts.md contradicts itself on which way a timber runs; nothing says what
   `bottom_position` is or what the joint face arguments mean.
8. **"Internal Server Error" failures.** Two turns died on them, apart from the slot problem.

## Sources

- Cursor agent: checkpoints, auto-run modes, to-do list, queued messages, summarizing at the
  context limit (cursor.com/help/ai-features/agent, cursor.com/docs/agent/overview).
- Claude Code: permission modes, plan mode, checkpoints and /rewind, /compact, /context, /resume,
  @-mentions (code.claude.com/docs/en/vs-code, support.claude.com Claude Code cheatsheet).
