// Public Auth0 SPA configuration. Never place a client secret in this file.
window.KAIZO_AUTH_CONFIG = Object.freeze({
  domain: "kaizo-system.us.auth0.com",
  clientId: "gDX8EH7Nd91sBWZBcFKuVMma1wxKeq4e",
  audience: "https://api.kaizo.system"
});
    
// Railway serves this UI separately from Core. Route its API calls to the
// Core service; non-Railway staging hosts keep their same-origin API route.
window.KAIZO_API_BASE = window.KAIZO_API_BASE || (
  window.location.hostname === "kaizo-coach-production.up.railway.app"
    ? "https://kaizo-core-engine-production.up.railway.app/api/v1"
    : "/api/v1"
);
