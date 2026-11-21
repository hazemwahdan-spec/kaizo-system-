"""Cloudflare Workers entrypoint for the isolated KAIZO Coach Staging Worker.

This Staging deployment is intentionally memory-only and must never connect to
PostgreSQL, Hyperdrive, or any production persistence service.
"""
from __future__ import annotations

import os

# This Worker is Staging-only. Sanitize inherited process variables before
# importing the Core app: backend/main.py performs persistence.initialize()
# during import whenever PostgreSQL mode is enabled.
os.environ["KAIZO_ENVIRONMENT"] = "staging"
os.environ["KAIZO_PERSISTENCE_MODE"] = "memory"
os.environ.pop("DATABASE_URL", None)

from workers import WorkerEntrypoint, asgi

# Import during startup so Cloudflare can snapshot the FastAPI application.
from app import app


class Default(WorkerEntrypoint):
    async def fetch(self, request):
        environment = str(getattr(self.env, "KAIZO_ENVIRONMENT", "")).strip().lower()
        persistence_mode = str(
            getattr(self.env, "KAIZO_PERSISTENCE_MODE", "memory")
        ).strip().lower()

        if environment != "staging":
            raise RuntimeError("KAIZO Coach Worker accepts only the staging environment")
        if getattr(self.env, "HYPERDRIVE", None) is not None:
            raise RuntimeError("Memory-only Staging refuses any Hyperdrive binding")
        if persistence_mode != "memory":
            raise RuntimeError("KAIZO Coach Staging requires memory-only persistence")

        # Fail closed: no database URL may leak into the in-memory Staging runtime.
        os.environ.pop("DATABASE_URL", None)
        os.environ["KAIZO_ENVIRONMENT"] = "staging"
        os.environ["KAIZO_PERSISTENCE_MODE"] = "memory"

        for name, default in (
            ("KAIZO_IDENTITY_MODE", "oidc"),
            ("KAIZO_OIDC_ISSUER", "https://kaizo-system.us.auth0.com/"),
            ("KAIZO_OIDC_AUDIENCE", "https://api.kaizo.system"),
            (
                "KAIZO_OIDC_JWKS_URL",
                "https://kaizo-system.us.auth0.com/.well-known/jwks.json",
            ),
        ):
            value = getattr(self.env, name, None)
            os.environ[name] = str(value if value is not None else default)

        return await asgi.fetch(app, request, self.env)
