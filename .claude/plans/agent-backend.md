# Agent backend: accounts, credits and a model proxy (2026-10-13)

## Goal

"1 click usage" for Kigumi's built-in agent: open the agent panel, sign in with Google or
GitHub, and it works, with a little free credit. No API keys for the user to find.

Most users are expected to bring their own agent (Claude Code, Claude Desktop, Cursor) over
Kigumi's MCP server. The built-in agent is the easy path, restricted to what Kigumi allows.

## Constraints

- **No "sign in with your Claude account".** As understood (check the current Agent SDK docs),
  third-party apps may not offer claude.ai login or subscription rate limits without
  Anthropic's approval; apps use API keys. A user's Claude subscription is used through their
  own agent plus Kigumi's MCP server. Packaged builds must drop the agent's fallback to the
  local Claude login (`agent/agent-session.js`); development builds may keep it.
- **Bring your own key stays** (`agent.apiKey`), for people who would rather pay Anthropic directly.
- **The built-in agent is narrow:**
  - Kigumi's tools;
  - reading and editing files, inside the project only;
  - no shell, web or subagents;
  - a fixed model list and a turn cap;
  - a short system prompt of Kigumi's own instead of Claude Code's.

## Shape

```
Kigumi app ──(Kigumi key)──> proxy (Cloudflare Worker) ──(our Anthropic key)──> Anthropic API
     │                           │
     └─ browser sign-in ──> Supabase Auth          Supabase Postgres: users, keys, balances, usage
                                 Stripe / Paddle ──(payment notifications)──> proxy ──> credits
```

The Agent SDK can be pointed at another endpoint (`ANTHROPIC_BASE_URL`), which is how
companies route Claude through their own gateways, so the agent code barely changes. The
web version will use the same proxy later, with its own simpler agent loop in the page.

## Sign-in flow

1. The agent panel, signed out, says: "Sign in to use the agent. Includes $1 of free usage."
2. **Sign in** opens the browser at the hosted sign-in page (Supabase Auth: Google, GitHub).
3. The page sends the session to `kigumi://auth?...`. The app trades it at the proxy
   (`POST /keys`) for a **Kigumi key**: long-lived, revocable, stored hashed on the server and
   in the system keychain on the device (Electron `safeStorage`). A key rather than the
   Supabase session, so a long agent run never meets an expired token.
4. The first sign-in grants the free credit (a database trigger).
5. **Buy credits** opens the checkout in the browser. The payment notification adds the credit,
   and the panel's balance refreshes.

There is no anonymous trial: free credit without an account gets farmed by reinstalling the app.

## Backend pieces (~750 lines plus SQL)

| Piece | Size | Job |
|---|---|---|
| `POST /v1/messages` proxy | ~350 | Check the key and the balance. Allow only listed models; cap `max_tokens`. Forward with our key and stream the response through, reading token counts from the stream. Charge the usage. |
| `POST /v1/messages/count_tokens` | ~10 | Pass through, free (the SDK may call it). |
| `POST /keys`, `DELETE /keys/:id` | ~60 | Trade a Supabase session for a Kigumi key; revoke one. |
| `GET /account` | ~30 | Balance and recent usage, for the panel. |
| Billing | ~120 | Create a checkout session. Handle payment notifications, applying each payment once. Link to the billing portal. |
| Limits | ~50 | Per-user requests per minute. A global daily spend ceiling, so a bug cannot run up the Anthropic bill. |
| Schema | ~80 SQL | `users`, `keys` (hashed), `balances`, `usage_events`, `payments`. A database function that reserves and settles charges atomically, and the sign-up credit trigger. |
| Sign-in page | ~100 | Static page: Supabase sign-in, then a redirect to `kigumi://`. |

**Charging:**
- Reserve an estimate before forwarding a request.
- Settle on the actual usage once the response ends, counting cache reads and writes, and
  release what was over-reserved.
- Requests with no balance get a 402, which the panel turns into "Buy credits".
- Prices live in one per-model table, in micro-dollars.
- Credits are priced at about 1.3–1.5× our Anthropic cost, to cover payment fees and failed requests.

**Models:** Haiku by default and Sonnet as an option. Haiku must be allowed regardless,
because the SDK uses it for small background tasks.

## Desktop pieces (~400 lines)

- Sign in and out; register the `kigumi://` link; store the key in the keychain.
- An account section in the agent panel: balance, buy credits, sign out, and "sign in for $1 free".
- In `agent/agent-session.js`, when signed in:
  - point the SDK at the proxy (`ANTHROPIC_BASE_URL`, `ANTHROPIC_API_KEY` = the Kigumi key);
  - turn off its optional background traffic (`CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC=1`);
  - narrow its tools as above;
  - fall back to `agent.apiKey` if set, and offer sign-in if not.
- Packaged builds: no fallback to the local Claude login.

## Deployment and running costs

| Service | Cost | Setup |
|---|---|---|
| Cloudflare Workers | Free for 100k requests/day; $5/mo paid plan | Anthropic key as a Worker secret (`wrangler secret put`), `wrangler deploy`, a domain (`api.<domain>`) |
| Supabase | Free tier pauses after a week idle; Pro $25/mo | Google and GitHub sign-in registrations; the schema migration |
| Stripe, or Paddle / Lemon Squeezy | Stripe ~2.9% + 30¢ per payment, no monthly fee. Merchant-of-record services charge more but handle sales tax and VAT. | Business verification (days); payment notification endpoint; products |
| Anthropic | Usage | A separate key with a monthly spend limit |

- **Fixed costs:** about $5–30 a month before model use.
- **Minimum top-up:** $10, since fees eat about 9% of a $5 payment.
- **Model cost for scale:** the first live tests on Haiku cost $0.03–0.05 a question. A Sonnet
  session with several tool calls is perhaps $0.10–0.50. $1 of free credit is roughly 20–30
  Haiku questions; prompt caching lowers that.

## Work

| Step | Who | Time |
|---|---|---|
| Worker, schema, billing; tests against local Supabase and payment test mode | Claude | 3–4 days |
| Desktop sign-in, keychain, account panel, agent narrowing | Claude | 2–3 days |
| End-to-end flow in test mode | both | 1–2 days |
| Accounts: Cloudflare, Supabase, payments, domain, sign-in providers, Anthropic key | maple | ~1 day, plus waiting on payment verification |
| Terms of service and privacy policy | maple | — |

About 1.5–2 weeks to a working beta. After that: support, refunds and watching costs.

## Decisions before starting

1. **Payments:** Stripe (lower fees; we handle tax) or Paddle / Lemon Squeezy (they handle tax).
2. **Models offered:** Haiku only, or Haiku plus Sonnet.
3. **Free credit:** how much per new account, and whether to cap it per day.
4. **Domain** for the proxy and the sign-in page.

## Order

1. Narrow the built-in agent, and make packaged builds use a key only. This is worth doing
   regardless (½–1 day).
2. Backend in the repo (`backend/`), running locally against Supabase's local stack and payment
   test mode.
3. Desktop sign-in and account panel against the local backend.
4. Deploy to staging; maple runs through the flow; then production with a low global spend ceiling.
5. Later: the web version's agent loop on the same proxy, after deciding where Python runs on the web.

## Risks

- **The Agent SDK's request mix through a custom endpoint:** if it uses more endpoints than
  `/v1/messages` and `count_tokens`, the proxy must pass them through. Check against the
  pinned SDK version.
- **Abuse:** free credit farmed with throwaway accounts. Mitigations: credit only after a
  verified email or OAuth sign-in, per-user and global ceilings, a small free amount.
- **Policy:** confirm that reselling model use inside Kigumi this way fits Anthropic's
  commercial terms, and keep the no-Claude-login rule in packaged builds.
