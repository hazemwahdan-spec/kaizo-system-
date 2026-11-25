// Public Auth0 SPA configuration. Never place a client secret in this file.
// The shared frontend is deployed to both Railway Production and the isolated
// Cloudflare Staging Worker; select credentials strictly by the exact Staging
// hostname so a Staging identity can never be used against Production.
const isKaizoCoachStaging =
  window.location.hostname === "kaizo-coach-core-staging.hazemwahdan.workers.dev";

window.KAIZO_AUTH_CONFIG = Object.freeze({
  domain: "kaizo-system.us.auth0.com",
  clientId: isKaizoCoachStaging
    ? "k5s2COCSh3YDE0biqBK8V6TLxjfiwexW"
    : "gDX8EH7Nd91sBWZBcFKuVMma1wxKeq4e",
  audience: isKaizoCoachStaging
    ? "https://api.staging.kaizo.system"
    : "https://api.kaizo.system"
});

// Railway serves this UI separately from Core. Route its API calls to the
// Core service; non-Railway staging hosts keep their same-origin API route.
window.KAIZO_API_BASE = window.KAIZO_API_BASE || (
  window.location.hostname === "kaizo-coach-production.up.railway.app"
    ? "https://kaizo-core-engine-production.up.railway.app/api/v1"
    : "/api/v1"
);
