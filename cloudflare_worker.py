"""Cloudflare Workers entrypoint for the KAIZO FastAPI application.

The staging Worker deliberately uses in-memory persistence. Production can use
Cloudflare Hyperdrive by adding the HYPERDRIVE binding in wrangler.jsonc; the
binding's connection string is never committed to source control.
"""
from __future__ import annotations

import os

from workers import WorkerEntrypoint, asgi

# Import the Core app during Worker startup so Cloudflare can snapshot the
# application rather than charging its full import cost to the first request.
# app.py sets up the existing backend/ and productization/ import paths.
from app import app
import main as core
import persistence

_DATABASE_INITIALIZED = False


class Default(WorkerEntrypoint):
    async def fetch(self, request):
        global _DATABASE_INITIALIZED

        hyperdrive = getattr(self.env, "HYPERDRIVE", None)
        if hyperdrive is not None:
            os.environ["DATABASE_URL"] = str(hyperdrive.connectionString)
            os.environ["KAIZO_PERSISTENCE_MODE"] = "postgres"
            if not _DATABASE_INITIALIZED:
                persistence.initialize()
                core.KNOWLEDGE_REPOSITORY.update(persistence.load_knowledge())
                _DATABASE_INITIALIZED = True
        else:
            # Staging stays isolated from production data.
            os.environ.pop("DATABASE_URL", None)
            os.environ["KAIZO_PERSISTENCE_MODE"] = str(
                getattr(self.env, "KAIZO_PERSISTENCE_MODE", "memory")
            )

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
