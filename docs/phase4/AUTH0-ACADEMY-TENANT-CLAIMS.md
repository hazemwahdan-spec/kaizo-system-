# Phase 4 — Auth0 academy tenant claims

## Purpose
The live tenant-isolation workflow uses two distinct Auth0 Machine-to-Machine clients. Each client must receive a signed, trusted KAIZO role and tenant claim from Auth0 Client Credentials Exchange. Do not use browser SPA credentials or manually supplied request parameters as tenant identity.

## 1. Create and deploy the Action
In Auth0 Dashboard, open **Actions → Library → Create Action** and select the **Credentials Exchange** trigger (Client Credentials Flow). Use Node.js and paste the code from `auth0/actions/kaizo-academy-tenant-claims.js`. Save, then deploy the Action. In **Actions → Triggers**, attach the deployed Action to the **Credentials Exchange** flow.

The Action only applies to API audience `https://api.kaizo.system` and fails closed when the calling client lacks trusted academy metadata.

## 2. Create two dedicated M2M clients
Create separate M2M applications for Academy A and Academy B and authorize each for the **KAIZO Core API** with only the minimum required permissions. Do not reuse the Frontend SPA or a human-user application.

For each M2M application, open its **Settings → Advanced Settings → Client Metadata** (location may vary by dashboard version) and set:
- `kaizo_role` = `academy`
- `kaizo_tenant_id` = a distinct, stable identifier for that academy (for example, `academy-a` and `academy-b` only if those are the real tenant identifiers in the production database).

Save each application. Never put Client Secrets in source control, pull requests, screenshots, or chat.

## 3. Add GitHub Actions secrets
Repository → **Settings → Secrets and variables → Actions → New repository secret**. Add:
- `AUTH0_DOMAIN` = `kaizo-system.us.auth0.com`
- `AUTH0_ACADEMY_A_CLIENT_ID`
- `AUTH0_ACADEMY_A_CLIENT_SECRET`
- `AUTH0_ACADEMY_B_CLIENT_ID`
- `AUTH0_ACADEMY_B_CLIENT_SECRET`

If production is not hosted at the workflow's current default, configure repository variable `KAIZO_PHASE4_PRODUCTION_BASE_URL` with the actual production base URL. Do not set it to a staging host and call the result production evidence.

## 4. Run the live isolation test
Open **Actions → KAIZO Phase 4 Live Academy Tenant Isolation → Run workflow**. A valid pass requires both distinct signed identities, non-empty durable audit records for each tenant, tenant-scoped results, and identical results when a caller attempts `?tenant_id=<other-tenant>`.

## Evidence boundary
Creating this Action or configuring Auth0 is not proof of isolation. Do not merge or close Phase 4 until the workflow passes against the verified production host and the run output establishes all checks above. If the API's audit endpoint requires a different permission name, update the policy and test based on the actual API authorization configuration rather than weakening the test.
