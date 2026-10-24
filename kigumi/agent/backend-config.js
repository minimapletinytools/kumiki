/**
 * Where Kigumi's backend is (the kigumi-backend repo): the Supabase project users sign in with, its
 * publishable key, and the Worker that carries model requests. Empty until it is deployed, which
 * hides signing in. The environment overrides each, e.g. to point at a staging deployment.
 */

const BACKEND = {
    supabaseUrl: '',
    supabaseKey: '',
    backendUrl: '',
};

function backendConfig(env = {}) {
    return {
        supabaseUrl: env.KIGUMI_SUPABASE_URL || BACKEND.supabaseUrl,
        supabaseKey: env.KIGUMI_SUPABASE_KEY || BACKEND.supabaseKey,
        backendUrl: env.KIGUMI_BACKEND_URL || BACKEND.backendUrl,
    };
}

module.exports = { backendConfig };
