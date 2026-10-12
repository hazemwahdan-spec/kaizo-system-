"""Database-backed tenant and minor-consent checks for product resource reads.

The caller must first resolve a Principal through the existing identity module.
All database errors fail closed; this module never treats caller-supplied tenant
labels as proof that a resource belongs to an academy.
"""
from __future__ import annotations

from datetime import datetime, timezone
from threading import Lock

import persistence


class ResourceAuthorizationError(PermissionError):
    """The requested resource is not authorized."""


class ResourceAuthorizationUnavailable(RuntimeError):
    """Durable authorization data could not be verified."""


_schema_ready = False
_schema_lock = Lock()


def _ensure_schema() -> None:
    global _schema_ready
    if _schema_ready:
        return
    with _schema_lock:
        if _schema_ready:
            return
        if not persistence.is_postgres_enabled():
            raise ResourceAuthorizationUnavailable(
                "durable tenant and consent verification requires PostgreSQL"
            )
        try:
            with persistence.connection() as conn:
                with conn.cursor() as cur:
                    cur.execute("""
                        CREATE TABLE IF NOT EXISTS kaizo_academy_assignments (
                            assignment_id TEXT PRIMARY KEY,
                            academy_id TEXT NOT NULL,
                            athlete_id TEXT NOT NULL,
                            coach_ids JSONB NOT NULL,
                            status TEXT NOT NULL,
                            created_at TEXT NOT NULL,
                            updated_at TEXT NOT NULL
                        );
                        CREATE INDEX IF NOT EXISTS idx_kaizo_assignment_athlete_academy
                            ON kaizo_academy_assignments(athlete_id, academy_id, status);
                        CREATE TABLE IF NOT EXISTS kaizo_guardian_links (
                            guardian_id TEXT NOT NULL,
                            child_id TEXT NOT NULL,
                            academy_id TEXT NOT NULL,
                            status TEXT NOT NULL,
                            updated_at TEXT NOT NULL,
                            PRIMARY KEY (guardian_id, child_id, academy_id)
                        );
                        CREATE TABLE IF NOT EXISTS kaizo_minor_consents (
                            child_id TEXT NOT NULL,
                            guardian_id TEXT NOT NULL,
                            academy_id TEXT NOT NULL,
                            resource TEXT NOT NULL,
                            action TEXT NOT NULL,
                            state TEXT NOT NULL,
                            expires_at TEXT,
                            updated_at TEXT NOT NULL,
                            updated_by TEXT NOT NULL,
                            PRIMARY KEY (child_id, guardian_id, academy_id, resource, action)
                        );
                    """)
                conn.commit()
            _schema_ready = True
        except Exception as exc:
            raise ResourceAuthorizationUnavailable(
                "could not initialize durable tenant/consent authorization schema"
            ) from exc


def require_athlete_academy(athlete_id: str, academy_id: str) -> None:
    """Prove the athlete has an active assignment to this academy in PostgreSQL."""
    if not athlete_id or not academy_id:
        raise ResourceAuthorizationError("athlete and academy are required")
    _ensure_schema()
    try:
        with persistence.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """SELECT 1 FROM kaizo_academy_assignments
                       WHERE athlete_id=%s AND academy_id=%s AND status='ACTIVE'
                       LIMIT 1""",
                    (athlete_id, academy_id),
                )
                found = cur.fetchone()
    except Exception as exc:
        raise ResourceAuthorizationUnavailable(
            "could not verify athlete-to-academy assignment"
        ) from exc
    if not found:
        raise ResourceAuthorizationError("athlete is not assigned to this academy")


def require_parent_consent(
    guardian_id: str,
    athlete_id: str,
    academy_id: str,
    resource: str = "athlete_progress",
    action: str = "read",
) -> None:
    """Require an active guardian link and current, exact-scope consent."""
    if not guardian_id or not athlete_id or not academy_id:
        raise ResourceAuthorizationError("verified guardian, athlete and academy are required")
    _ensure_schema()
    try:
        with persistence.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """SELECT 1 FROM kaizo_guardian_links
                       WHERE guardian_id=%s AND child_id=%s AND academy_id=%s
                         AND status='ACTIVE' LIMIT 1""",
                    (guardian_id, athlete_id, academy_id),
                )
                linked = cur.fetchone()
                if not linked:
                    consent = None
                else:
                    cur.execute(
                        """SELECT state, expires_at FROM kaizo_minor_consents
                           WHERE child_id=%s AND guardian_id=%s AND academy_id=%s
                             AND resource=%s AND action=%s
                           LIMIT 1""",
                        (athlete_id, guardian_id, academy_id, resource, action),
                    )
                    consent = cur.fetchone()
    except Exception as exc:
        raise ResourceAuthorizationUnavailable(
            "could not verify guardian link and durable consent"
        ) from exc

    if not linked:
        raise ResourceAuthorizationError("verified guardian-to-child link is required")
    if not consent:
        raise ResourceAuthorizationError("parental consent is absent for this resource/action")
    state, expires_at = consent
    if str(state).lower() != "active":
        raise ResourceAuthorizationError(f"parental consent is not active: {state}")
    if expires_at:
        try:
            expiry = datetime.fromisoformat(str(expires_at).replace("Z", "+00:00"))
            if expiry.tzinfo is None:
                expiry = expiry.replace(tzinfo=timezone.utc)
            if expiry <= datetime.now(timezone.utc):
                raise ResourceAuthorizationError("parental consent has expired")
        except ValueError as exc:
            raise ResourceAuthorizationError("parental consent expiry is invalid") from exc
