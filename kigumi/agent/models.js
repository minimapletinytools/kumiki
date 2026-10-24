/**
 * The models the built-in agent offers, and where each one's requests go. Everything
 * model-specific lives here, so the agent loop never names a provider.
 *
 * Each model has its OpenRouter id (through Kigumi's backend, or an OpenRouter key) and, for
 * Anthropic's, its Anthropic id (an Anthropic key). `images`: it can look at screenshots.
 * `cacheMarks`: its prompt cache needs telling where to cache (Anthropic's); others cache by themselves.
 * `contextWindow`: the most tokens one request may carry.
 */

const MODELS = [
    // Cheapest; the free tier's. The dated -1017 costs more, so this is the undated id, not ~latest.
    { id: 'deepseek-v4.1-flash', label: 'DeepSeek V4.1 Flash', openrouter: 'deepseek/deepseek-v4.1-flash', images: true, contextWindow: 1048576 },
    { id: 'gpt-5.6-luna', label: 'GPT-5.6 Luna', openrouter: 'openai/gpt-5.6-luna', images: true, contextWindow: 1050000 },
    { id: 'claude-haiku-4.5', label: 'Claude Haiku 4.5', openrouter: 'anthropic/claude-haiku-4.5', anthropic: 'claude-haiku-4-5', images: true, cacheMarks: true, contextWindow: 200000 },
    { id: 'claude-sonnet-5', label: 'Claude Sonnet 5', openrouter: 'anthropic/claude-sonnet-5', anthropic: 'claude-sonnet-5', images: true, cacheMarks: true, contextWindow: 1000000 },
];

const DEFAULT_MODEL_ID = MODELS[0].id;

/** The model with `id`, else the default. */
function findModel(id) {
    return MODELS.find((model) => model.id === id) || MODELS.find((model) => model.id === DEFAULT_MODEL_ID);
}

/**
 * Where `model`'s requests go: { via, modelId, apiKey, baseURL? }, or null when nothing can carry
 * them. A key the user set wins over the account, since setting one says how they want to pay.
 *
 * @param {object} model  a row of MODELS
 * @param {object} credentials
 * @param {string} [credentials.anthropicKey]
 * @param {string} [credentials.openrouterKey]
 * @param {{url: string}|null} [credentials.backend]  signed in to Kigumi's backend, whose requests
 *     carry the account's token (agent/account.js fetchWithToken)
 */
function routeModel(model, { anthropicKey, openrouterKey, backend } = {}) {
    if (anthropicKey && model.anthropic) {
        return { via: 'anthropic', modelId: model.anthropic, apiKey: anthropicKey };
    }
    if (openrouterKey && model.openrouter) {
        return { via: 'openrouter', modelId: model.openrouter, apiKey: openrouterKey };
    }
    if (backend && backend.url && model.openrouter) {
        return { via: 'backend', modelId: model.openrouter, baseURL: `${backend.url.replace(/\/$/, '')}/v1` };
    }
    return null;
}

module.exports = { MODELS, DEFAULT_MODEL_ID, findModel, routeModel };
