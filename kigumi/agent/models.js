/**
 * The models the built-in agent offers, and where each one's requests go. Everything
 * model-specific lives here, so the agent loop never names a provider.
 *
 * The list is the backend's (kigumi-backend src/models.ts, served at GET /models); MODELS is a
 * copy for before the app has heard from it. Each model has its OpenRouter id, used through Kigumi's
 * backend or the user's OpenRouter key.
 * `images`: it can look at screenshots. `cacheMarks`: its prompt cache needs telling where to
 * cache (Anthropic's); others cache by themselves. `contextWindow`: the most tokens one request may carry.
 * `harness`: how the agent loop treats it, where it differs from HARNESS.
 */

/**
 * How the agent loop treats a model, unless its `harness` says otherwise:
 *   nudgeAfter           tool calls in a turn without an edit before a write-early reminder; 0 for none
 *   keepToolResults      tool results kept whole (request.js trimOldToolResults)
 *   summariseAt          tokens (estimated) past which a turn starts by summarising the conversation
 *   imagesInToolResults  whether images may stay in tool results, rather than go in a user message after
 */
const HARNESS = Object.freeze({ nudgeAfter: 6, keepToolResults: 8, summariseAt: 100000, imagesInToolResults: false });

const MODELS = [
    { id: 'deepseek-v4.1-flash', label: 'DeepSeek V4.1 Flash', openrouter: 'deepseek/deepseek-v4.1-flash', images: true, contextWindow: 1048576 },
    { id: 'gpt-5.6-luna', label: 'GPT-5.6 Luna', openrouter: 'openai/gpt-5.6-luna', images: true, contextWindow: 1050000 },
    { id: 'claude-haiku-4.5', label: 'Claude Haiku 4.5', openrouter: 'anthropic/claude-haiku-4.5', images: true, cacheMarks: true, contextWindow: 200000 },
    { id: 'claude-sonnet-5', label: 'Claude Sonnet 5', openrouter: 'anthropic/claude-sonnet-5', images: true, cacheMarks: true, contextWindow: 1000000 },
];

/** The model with `id` in `models`, else their default (the first). */
function findModel(id, models = MODELS) {
    return models.find((model) => model.id === id) || models[0];
}

/** `model`'s harness: HARNESS with what its `harness` sets. */
function harnessOf(model) {
    return { ...HARNESS, ...((model && model.harness) || {}) };
}

/** The fields of `harness` that are HARNESS's and of its type, or null if none are. */
function validHarness(harness) {
    if (!harness || typeof harness !== 'object') return null;
    const valid = Object.fromEntries(Object.entries(harness).filter(([key, value]) => key in HARNESS
        && typeof value === typeof HARNESS[key] && (typeof value !== 'number' || (Number.isFinite(value) && value >= 0))));
    return Object.keys(valid).length ? valid : null;
}

/** `rows` as a model list, keeping only well-formed models; null if none are. */
function validModels(rows) {
    if (!Array.isArray(rows)) return null;
    const models = rows.filter((row) => row && typeof row.id === 'string' && typeof row.label === 'string'
        && typeof row.openrouter === 'string' && Number.isFinite(row.contextWindow))
        .map((row) => {
            const harness = validHarness(row.harness);
            return { id: row.id, label: row.label, openrouter: row.openrouter, images: row.images === true,
                ...(row.cacheMarks === true ? { cacheMarks: true } : {}), contextWindow: row.contextWindow, ...(harness ? { harness } : {}) };
        });
    return models.length ? models : null;
}

/**
 * The models offered, as the backend last listed them: the one saved, else MODELS, until
 * refresh() hears. Host-neutral: the host saves the list where it likes.
 *
 * @param {object} options
 * @param {string} options.backendUrl
 * @param {typeof fetch} [options.fetch]
 * @param {{load: () => any, save: (models: object[]) => void}} [options.storage]
 * @param {() => void} [options.onChange]
 */
function createModelList({ backendUrl, fetch: fetcher = (...args) => fetch(...args), storage = null, onChange = () => {} }) {
    let models = validModels(storage && (() => { try { return storage.load(); } catch (_error) { return null; } })()) || MODELS;
    return {
        list: () => models,
        async refresh() {
            const response = await fetcher(`${backendUrl.replace(/\/$/, '')}/models`);
            if (!response.ok) throw new Error(`models: ${response.status}`);
            const listed = validModels((await response.json()).models);
            if (!listed) throw new Error('models: none listed');
            const changed = JSON.stringify(listed) !== JSON.stringify(models);
            models = listed;
            if (changed) {
                if (storage) storage.save(models);
                onChange();
            }
        },
    };
}

/**
 * Where `model`'s requests go: { via, modelId, apiKey, baseURL? }, or null when nothing can carry
 * them. The user's OpenRouter key wins over the account.
 *
 * @param {object} model  a row of MODELS
 * @param {object} credentials
 * @param {string} [credentials.openrouterKey]
 * @param {{url: string}|null} [credentials.backend]  signed in to Kigumi's backend, whose requests
 *     carry the account's token (agent/account.js fetchWithToken)
 */
function routeModel(model, { openrouterKey, backend } = {}) {
    if (openrouterKey && model.openrouter) {
        return { via: 'openrouter', modelId: model.openrouter, apiKey: openrouterKey };
    }
    if (backend && backend.url && model.openrouter) {
        return { via: 'backend', modelId: model.openrouter, baseURL: `${backend.url.replace(/\/$/, '')}/v1` };
    }
    return null;
}

module.exports = { MODELS, HARNESS, findModel, harnessOf, validModels, createModelList, routeModel };
