"""Cloudflare Workers entrypoint for the KAIZO FastAPI application.

The staging Worker deliberately uses in-memory persistence. Production can use
Cloudflare Hyperdrive by adding the HYPERDRIVE binding in wrangler.jsonc; the
binding's connection string is never committed to source control.
"""
from __future__ import annotations

import os
import sys

from workers import WorkerEntrypoint, asgi

# The existing FastAPI app keeps its current backend/productization module layout.
sys.path.insert(0, "backend")
sys.path.insert(0, ".")


class Default(WorkerEntrypoint):
    async def fetch(self, request):
        hyperdrive = getattr(self.env, "HYPERDRIVE", None)

        if hyperdrive is not None:
            os.environ["DATABASE_URL"] = str(hyperdrive.connectionString)
            os.environ["KAIZO_PERSISTENCE_MODE"] = "postgres"
        else:
            # Staging stays isolated from production data and never silently
            # falls back from a configured Hyperdrive connection.
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

        # Import only after the runtime bindings are available: main.py performs
        # durable schema initialization when PostgreSQL mode is selected.
        from main import app

        return await asgi.fetch(app, request, self.env)
