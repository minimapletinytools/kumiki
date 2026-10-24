/**
 * Where Kigumi's backend is (the kigumi-backend repo): the Supabase project users sign in with, its
 * publishable key, and the Worker that carries model requests. The environment overrides each, e.g.
 * to point at a staging deployment.
 */

const BACKEND = {
    supabaseUrl: 'https://hhezlixmspumosexmfic.supabase.co',
    // Publishable: it ships in the app. The service_role key is the Worker's alone.
    supabaseKey: 'sb_publishable_Hk983OPcDYXXcYdNuN_bDQ_mg1SIwGV',
    backendUrl: 'https://kigumi-backend.kigumi-backend.workers.dev',
};

function backendConfig(env = {}) {
    return {
        supabaseUrl: env.KIGUMI_SUPABASE_URL || BACKEND.supabaseUrl,
        supabaseKey: env.KIGUMI_SUPABASE_KEY || BACKEND.supabaseKey,
        backendUrl: env.KIGUMI_BACKEND_URL || BACKEND.backendUrl,
    };
}

module.exports = { backendConfig };
