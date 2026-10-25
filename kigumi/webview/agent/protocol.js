// Every message between the agent panel and its session (agent/agent-session.js), each way.
// __tests__/agent-protocol.test.js checks that the session and the panel send and handle only these.

/** What the panel sends. */
export const PANEL_TO_SESSION = [
    'agent:ready', 'agent:prompt', 'agent:stop', 'agent:clear', 'agent:retry', 'agent:permissionAnswer',
    'agent:setModel', 'agent:setSetting', 'agent:restore', 'agent:unqueue', 'agent:listFiles',
    'agent:listConversations', 'agent:openConversation', 'agent:deleteConversation', 'agent:signIn', 'agent:signOut',
];

/** What the session sends. */
export const SESSION_TO_PANEL = [
    'agent:state', 'agent:busy', 'agent:text', 'agent:reasoning', 'agent:tool', 'agent:toolResult', 'agent:toolImages',
    'agent:notice', 'agent:context', 'agent:permission', 'agent:done', 'agent:error', 'agent:conversations',
    'agent:replay', 'agent:checkpoint', 'agent:restored', 'agent:restoreConflict', 'agent:queued', 'agent:dequeued',
    'agent:userMessage', 'agent:todos', 'agent:files',
];
