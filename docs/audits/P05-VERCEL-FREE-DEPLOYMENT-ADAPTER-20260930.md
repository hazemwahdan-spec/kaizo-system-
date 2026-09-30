# P05 Vercel Free Deployment Adapter — 2026-09-30

Status: PREPARED — DEPLOYMENT PENDING USER-SIDE VERCEL IMPORT

Purpose:
Provide a zero-cost verification host for KAIZO P05 after Railway rejected new resource provisioning and Render required payment information for the account.

Architecture:
GitHub (hazemwahdan-spec/kaizo-system-) -> Vercel Hobby Python Runtime -> existing longitudinal/main.py -> Neon PostgreSQL.

Changes:
- Added root app.py exporting the existing FastAPI app from longitudinal.main.
- Added root requirements.txt with the existing P05 runtime dependencies.
- No Core Engine rebuild.
- No P05 business-logic rewrite.
- No SQLite or substitute persistence.

Evidence basis:
Vercel documents FastAPI deployment with its Python runtime and zero-configuration detection of a FastAPI app exported as app. Vercel Hobby is $0/month with included Function usage, subject to Hobby limits and personal/non-commercial use restrictions.

Required external configuration:
DATABASE_URL must be configured in the Vercel project from the user's Neon PostgreSQL connection string. The secret must not be committed to GitHub.

Current closure state:
P05 remains OPEN. Runtime, persistence-survival, governance, minor-consent, and independent-retest evidence are still required before closure.
