/**
 * What the agent panel may send its session, by type, with the shape each must have. The types are
 * webview/agent/protocol.js PANEL_TO_SESSION; agent/agent-session.js handles each.
 */

const { z } = require('zod');

const id = z.string();

const PANEL_MESSAGES = {
    'agent:ready': z.object({}),
    'agent:prompt': z.object({ text: z.string(), images: z.array(z.object({ mediaType: z.string(), data: z.string() })).default([]) }),
    'agent:stop': z.object({}),
    'agent:clear': z.object({}),
    'agent:retry': z.object({}),
    'agent:permissionAnswer': z.object({ requestId: z.number(), allow: z.boolean(), always: z.boolean().optional() }),
    'agent:setModel': z.object({ id }),
    'agent:setSetting': z.object({ key: z.string(), value: z.unknown() }),
    'agent:restore': z.object({ turn: z.number().int(), force: z.boolean().optional() }),
    'agent:unqueue': z.object({ id: z.number() }),
    'agent:listFiles': z.object({}),
    'agent:listConversations': z.object({}),
    'agent:openConversation': z.object({ id }),
    'agent:deleteConversation': z.object({ id }),
    'agent:signIn': z.object({ provider: z.enum(['github', 'google']).catch('github') }),
    'agent:signOut': z.object({}),
};

/** `message` as { type, ...fields } if it is one the panel may send in its shape; else null. */
function parsePanelMessage(message) {
    const schema = message && typeof message.type === 'string' && Object.hasOwn(PANEL_MESSAGES, message.type)
        ? PANEL_MESSAGES[message.type] : null;
    if (!schema) return null;
    const parsed = schema.safeParse(message);
    return parsed.success ? { type: message.type, ...parsed.data } : null;
}

module.exports = { PANEL_MESSAGES, parsePanelMessage };
