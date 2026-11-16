"""Cloudflare Workers entrypoint for the KAIZO FastAPI application.

The isolated Staging Worker requires a Hyperdrive binding connected to the
dedicated kaizo_coach_staging database. It never creates or migrates schema:
all Core and Coach evidence tables must be pre-provisioned before deployment.
In-memory mode is reserved for local dry runs.
"""
from __future__ import annotations

import asyncio
import os
from urllib.parse import unquote, urlparse

from workers import WorkerEntrypoint, asgi

# Import the Core app during Worker startup so Cloudflare can snapshot the
# application rather than charging its full import cost to the first request.
# app.py sets up the existing backend/ and productization/ import paths.
from app import app
import main as core
import persistence
import staging_schema_guard

_DATABASE_INITIALIZED = False
_DATABASE_LOCK = asyncio.Lock()
_STAGING_DATABASE_NAME = "kaizo_coach_staging"


class Default(WorkerEntrypoint):
    async def fetch(self, request):
        global _DATABASE_INITIALIZED

        hyperdrive = getattr(self.env, "HYPERDRIVE", None)
        environment = str(getattr(self.env, "KAIZO_ENVIRONMENT", "")).strip().lower()

        if hyperdrive is not None:
            if environment != "staging":
                raise RuntimeError("KAIZO Worker refuses Hyperdrive outside the Staging environment")
            connection_string = str(hyperdrive.connectionString)
            database_name = unquote(urlparse(connection_string).path.lstrip("/").split("?", 1)[0])
            if database_name != _STAGING_DATABASE_NAME:
                raise RuntimeError("KAIZO Staging refuses a database other than kaizo_coach_staging")
            os.environ["DATABASE_URL"] = connection_string
            os.environ["KAIZO_PERSISTENCE_MODE"] = "postgres"
        else:
            if environment == "staging":
                raise RuntimeError("KAIZO Staging requires its isolated PostgreSQL Hyperdrive binding")
            # Local dry-run mode is in-memory only; it is never accepted for Staging.
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

        if hyperdrive is not None:
            # Cloudflare recommends serializing synchronous PostgreSQL driver
            # operations in Python Workers. The current KAIZO adapter uses
            # synchronous psycopg calls, so guard the request boundary.
            async with _DATABASE_LOCK:
                if not _DATABASE_INITIALIZED:
                    if not persistence.is_postgres_enabled():
                        raise RuntimeError("KAIZO Staging requires PostgreSQL persistence")
                    # Connection and schema checks are read-only; deployment must
                    # never trigger Core schema DDL or implicit migrations.
                    persistence.check_connection()
                    staging_schema_guard.verify_required_tables(
                        staging_schema_guard.CORE_SCHEMA_TABLES
                        + staging_schema_guard.COACH_EVIDENCE_TABLES
                    )
                    core.KNOWLEDGE_REPOSITORY.update(persistence.load_knowledge())
                    _DATABASE_INITIALIZED = True
                return await asgi.fetch(app, request, self.env)

        return await asgi.fetch(app, request, self.env)
