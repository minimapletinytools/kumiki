# Agent architecture review and proposal (2026-10-29)

Covers `kigumi/agent/`, `kigumi/webview/agent/`, the Electron wiring in `hosts/electron/main.js`,
the evals in `kigumi/test/evals/`, and `kigumi-backend`. The agent works; this is about making it
one design instead of a pile of fixes.

## Verdict on owning the harness

Keep it. The AI SDK (`ai` v7) already does the model loop and provider wire formats; what we own is
policy (context, permissions, undo, persistence) and Kigumi's tools, which no off-the-shelf harness
gives. The Claude Agent SDK is Anthropic-only, ships a shell, and can't run in a browser.
OpenAI Agents SDK / Mastra add abstraction without solving anything we have. Bring-your-own-agent
is already covered by the MCP server.

What's wrong is not the choice, it's that each problem got a local fix in whichever layer it showed
up in. The sections below group those fixes by the missing concept they stand in for.

---

## 0. Check now (security, backend)

**Admin is decided by the email claim in the JWT** (`src/index.ts` `/admin/api/*`). Supabase's
email/password sign-up is reachable with the publishable key whatever the app's UI offers, and the
local `supabase/config.toml` has `[auth.email] enable_signup = true, enable_confirmations = false`.
If production matches, anyone can sign up as an admin's address and get the admin API. The same hole
mints unlimited $1 free-credit accounts.

- **Done:** production has email confirmation on, so an address can't be claimed without its
  inbox. Local `config.toml` now matches (`enable_confirmations = true`).
- Still worth doing: key admins on user ids (`ADMIN_USER_IDS`); and since the app only uses GitHub
  and Google, turning email sign-up off stops free-credit farming with throwaway inboxes.

---

## 1. One agent definition, used everywhere

**Now.** The agent is assembled in three places, each slightly differently:

- `hosts/electron/main.js` builds file tools and `kumiki_api` and passes them as `fileTools`
  (kumiki_api isn't a file tool; it's wrapped in the edit wrappers by accident of the parameter).
- `AgentSession`'s constructor adds Kigumi tools, wraps edits with build-check and checkpoints, adds
  the todo tool, and appends plan mode to the system prompt.
- `test/evals/run-evals.js` re-implements build-after-edit and `check_frame` by hand. Evals test a
  different assembly from the one users run.
- MCP serves a third subset (`tools.js` only: no `kumiki_api`, no file tools).

`AgentSession` takes 17 options; the host interface is implicit in that list.

**Proposal.** An explicit host interface and one composition root.

```js
// agent/host.js — what a host must give the agent (Electron, web, evals)
AgentHost = {
  files,          // project-files shape (exists)
  frames: {       // building and looking at frames
    build(file) -> BuildReport,          // view rebuild in the app; build_frame.py in evals
    screenshot?(file) -> png,            // absent in evals / headless
  },
  python: { kumikiApi(name, opts) },     // execFile on desktop, Pyodide on web
  panels?,        // absent in evals
  storage,        // conversations, blobs
}

// agent/agent.js
createAgent(host, { profile, mode }) -> { tools, instructions(context) }
```

- App, evals and the future web host all call `createAgent`. Evals become "the app with a headless
  host", so a passing eval means the shipped assembly passes.
- MCP takes `createAgent(...).tools.filter(t => t.surfaces.includes('mcp'))`. Expose `kumiki_api`
  and `describe_frame` over MCP; Claude Code users want them too.

## 2. Tools declare effects; permissions follow from effects

**Now.** One boolean, `readOnly`, means both "changes nothing" and "runs without asking". It's wrong
for `check_frame`: marked read-only, it builds (runs) any project `.py`. So in "edits" mode the agent
can `write_file` arbitrary Python then `check_frame` it with no prompt: "edits" equals "all". Editing a
file a view shows also rebuilds it, which runs it. `.vscode/` isn't protected.

**Proposal.** Each tool states its effect:

| effect | examples | meaning |
|---|---|---|
| `read` | read_file, search_files, describe_*, kumiki_api | no change, no code run |
| `ui` | open_in_viewer, set_camera, refresh_view | changes what the user sees, nothing on disk |
| `edit` | write_file, edit_file | changes project files |
| `run` | check_frame, the rebuild after an edit | runs project Python |

- Permission policy is a table over effects, not tool names. **Decided:** editing a frame means
  running it, so "edits" and "all" are the same thing. Two modes: **Ask** (`read`, `ui` run; `edit`,
  `run` ask) and **Auto** (everything runs). The panel says Auto lets the agent run Python.
- Plan mode = only `read` and `ui`.
- MCP's `readOnlyHint`/`destructiveHint` annotations come from the same field.
- Add `.vscode/` (tasks, settings) to `PROTECTED`.

Also consider the AI SDK v7's own `toolApproval` option instead of throwing inside `execute`;
check that it fits the panel's always-allow flow first.

## 3. A canonical conversation log, and a request built from it per step

This is the biggest change and the one that removes the most ad-hoc code.

**Now.** Messages pass through a chain of transforms on every step (`prepareStep`):
`onlyLatestImage` → `trimOldToolResults` → `imagesAfterToolResults` → nudge → `cacheMarked`. Then:

- **The stored history is the transformed one** (`sofar()`): old tool results are cut to 300 chars
  forever, and screenshots dropped forever. Policy changes can't be applied to old conversations, and
  the summary is written from already-trimmed results.
- **The transforms break the prompt cache.** Each new tool result cuts the 9th-newest one, which
  changes an earlier part of the prompt every step, so the cache misses from there on: the last ~8
  results (up to tens of thousands of tokens) are re-billed at full price each step. Dropping older
  images does the same.
- **Provider quirks are applied to every provider.** `imagesAfterToolResults` exists for
  chat-completions hosts, but runs on the direct-Anthropic route too, which handles images in tool
  results natively.
- **Two parallel records.** `history` (model messages) and `transcript` (panel events) are saved
  separately and can disagree.
- **Size budgets are scattered:** 40k read, 300 trim, 2000 panel, 4000 build report, 20k/60k summary
  files, 40k mention, 2000 context.
- Conversation saves are `JSON.stringify` + `writeFileSync` of everything, including base64
  screenshots and full before/after file copies for undo, in the app's main process, every turn.

**Proposal.**

```
ConversationLog (append-only, persisted)
  entries: user | assistant | toolCall | toolResult | note | summary | checkpoint | undo
  large payloads (screenshots, file snapshots) -> BlobStore by sha256, entries hold the hash

buildRequest(log, profile, budget) -> ModelMessage[]     // pure; unit-testable
  1. take entries after the latest summary
  2. compaction *epochs*: tool results older than the epoch boundary are cut; the boundary only
     moves in jumps (e.g. when 16 results are whole, move it to leave 8), so the prefix is stable for
     many steps and the cache holds
  3. images: keep the latest N (by profile)
  4. profile quirks: imagesInToolResults=false -> move to user message; cacheMarks -> mark
  5. notes rendered (see §4)

Panel replay = render(log). One source of truth for both.
```

- Summaries become a `summary` entry, not a fake user/assistant pair; `buildRequest` starts after
  it. The "changed files as they are now" attachment stays, as part of that entry.
- Undo becomes `checkpoint`/`undo` entries; the model sees an `undo` as a note.
- `estimateTokens` gives way to the last step's real `usage.inputTokens` where we have it.
- Budgets live in one `budget` object, per profile (a 1M-context model can keep more).

## 4. One mechanism for what the harness tells the model

**Now.** Harness messages arrive in five different shapes: fake user messages (stream
continuation, write-early nudge), fake user+assistant pairs ("Understood."), a prefix inside a tool
result (repeated look), a prefix on the user's own message (what they're looking at), and system
prompt suffixes (plan mode). The nudge counter (`looksSinceWrite`) also spans turns, so a plain
question after a research turn gets "write a first version now".

**Proposal.** A `note` entry type with a `kind` (`context`, `nudge`, `continuation`, `undo`,
`repeat`, `mode`), rendered one way by `buildRequest` (a tagged block on the next user-role content),
shown in the panel as a muted line (or hidden), and counted in eval output.

- Each heuristic becomes a small policy: `(log, profile) -> note | null`, registered in a list.
  Easy to switch off per model and to A/B in evals.
- Nudges count within the current turn only.
- Heuristics tuned on one DeepSeek session (nudge at 6 looks, prompt joined into one line) go behind
  the model profile and stay only if evals show they help.

## 5. Model profiles own every model-specific behaviour

**Now.** `models.js` says the loop never names a provider, but behaviour still branches on route
(`via === 'backend'` for cost, `providerMetadata.openrouter` for cost, images moved for everyone).
Cost is missing on the direct-Anthropic route. The model list is defined in the backend, copied into
`MODELS`, and filtered field by field in `validModels`.

**Proposal.**

- The backend's `/models` serves a full profile: `images`, `imagesInToolResults`, `cacheMarks`,
  `contextWindow`, `budget`, `heuristics: [...]`, prices. The client's fallback copy is generated from
  it at build time (a script), not hand-copied.
- Cost comes through one `costOf(step, route)` that knows each route, so every route reports cost.
- **Decided:** drop the direct-Anthropic route (`agent.apiKey`, `@ai-sdk/anthropic`, the
  `anthropic` id in model rows). Everything goes through OpenRouter: the backend, or a user's
  OpenRouter key.

## 6. Split AgentSession

**Now.** `agent-session.js` is protocol handling, conversation persistence, turn state (busy, queue,
generation counter, pending permissions), routing, settings migration and cost markup in one class.

**Proposal.**

- `Conversation` — the log (§3), load/save, checkpoints.
- `TurnRunner` — one turn: build the model, run `runTurn`, permissions, abort. Returns entries.
- `AgentController` — the panel protocol: queue, model/settings, account, conversations list.
- The panel protocol gets schemas (zod, shared by both sides) instead of a comment block plus a list
  of names; the existing protocol test then checks shapes, not just names.

## 7. Backend: reserve credit instead of one request at a time

**Now.** To bound overdraft, a user may have one request in flight (`claim_request` lease, 3-minute
expiry). That produced most of the recent hard bugs: stuck slots, "settle interrupted streams with
owned leases", the client's `backendFetch` that waits on `request_busy`, and the "waiting for the
previous request" notice. A stream the client abandons holds the user's lease until it settles.

**Proposal.** Reserve, then settle:

1. `reserve(user, request, max_usd)` atomically: `available = balance - sum(open reservations)`;
   refuse 402 if `available < max_usd`. `max_usd` = prompt tokens (body bytes / 3) ×
   `maxPrice.prompt` + `max_tokens` × `maxPrice.completion`. That's ~$0.11 for DeepSeek Flash and
   ~$0.80 for a full Sonnet request.
2. Settle charges the real cost and deletes the reservation (idempotent on request id, as now).
3. Reservations expire after N minutes; an expired, unsettled one is charged its reserved amount
   or looked up from OpenRouter's generation record.

Then requests may overlap, `request_busy` and the client's wait loop go away, and an abandoned
stream costs the user nothing until it settles. Overdraft is still bounded.

Smaller backend items:

- The 30 requests/minute limit is a plain 429 the client doesn't recognise; a fast model on short
  steps can hit it inside one turn, and the AI SDK's two retries won't wait long enough. Return
  `Retry-After` and treat it like any retryable wait, or raise the limit (reservations bound spend
  anyway).
- Drop the legacy `finish_request` function once no old Worker can be running.

## 8. Evals as the gate for harness changes

**Now.** Four single-turn tasks, run by hand, with a hand-built tool set (§1). Several heuristics
came from single sessions.

**Proposal.**

- Run on `createAgent` with a headless host.
- Add: a question that must not edit (checks "do what was asked"), a multi-turn task (checks the
  log/summary path), a task needing a screenshot.
- Record per run: pass, steps, cost, **cache hit rate** (the backend already logs `cachedTokens`;
  return it on the step's usage), notes fired.
- A harness change lands with an eval run against the default model, before and after.

---

## Order

1. **Done.** §0; §2's effects and two modes; batched trimming in `trimOldToolResults`; nudge counter
   per turn; the direct-Anthropic route dropped (from §5).
2. **Done: composition root (§1).** `agent/agent.js` builds the tools and prompt from a host;
   `agent/frames.js` is how a host builds frames. The app, MCP (now also given `kumiki_api`) and the
   evals (a headless host over `build_frame.py`) all use it. Left from §8: the new eval tasks and
   recording cache hit rate.
3. **Done: log, buildRequest and notes (§3, §4); Conversation out of AgentSession (§6).**
   `agent/conversation.js` holds the log (messages, notes, summaries, panel events) and draws the
   panel's replay from it; `agent/request.js` builds each step's request from it; notes go as
   `[Kigumi note: …]`; the conversation store keeps long strings as shared blobs and writes
   atomically. Old conversations open: their history becomes the log, their transcript is shown.
   Left from §6: a TurnRunner apart from the panel protocol, and typed protocol messages.
4. **Done: backend reservations (§7).** `reserve_request` holds back each request's most possible
   cost; `settle_request` drops the hold. The client's `backend-fetch.js` and its wait notice are
   gone. The rate limit's 429 says `Retry-After: 20`. Left: once the previous Worker is gone, a
   migration dropping `claim_request`, `start_request`, `finish_request`, `busy_until` and
   `active_request`.
5. **Done: profiles (§5).** `HARNESS` in `agent/models.js` holds the defaults (nudgeAfter,
   keepToolResults, summariseAt, imagesInToolResults); a model's `harness` from `/models` overrides
   them, so tuning needs no app release. No model sets one yet: set them from eval runs. Not done:
   generating the bundled fallback list from the backend (it is only used until `/models` answers).

## Decisions (2026-10-29)

- Everything through OpenRouter; the direct-Anthropic route goes. (§5)
- Two permission modes, Ask and Auto; Auto runs everything. (§2)
- Reserve credit per request instead of the one-request lease. (§7)
- Keep the full conversation log; old conversations converted best-effort. (§3)
