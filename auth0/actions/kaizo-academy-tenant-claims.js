/**
 * Auth0 Action: Client Credentials Exchange
 * Trigger: Credentials Exchange (Client Credentials Flow)
 *
 * Configure each academy M2M application's trusted Client Metadata:
 *   kaizo_role = academy
 *   kaizo_tenant_id = a distinct, stable tenant identifier
 *
 * This Action only emits KAIZO claims for the KAIZO Core API audience.
 */
exports.onExecuteCredentialsExchange = async (event, api) => {
  const audience = event.resource_server && event.resource_server.identifier;
  if (audience !== "https://api.kaizo.system") return;

  const metadata = (event.client && event.client.metadata) || {};
  const role = metadata.kaizo_role;
  const tenantId = metadata.kaizo_tenant_id;

  // Fail closed: do not mint KAIZO academy identity claims from incomplete metadata.
  if (role !== "academy" || typeof tenantId !== "string" || tenantId.trim() === "") {
    api.access.deny("KAIZO academy client metadata is missing or invalid.");
    return;
  }

  api.accessToken.setCustomClaim("https://kaizo.system/kaizo_role", "academy");
  api.accessToken.setCustomClaim("https://kaizo.system/tenant_id", tenantId.trim());
};
