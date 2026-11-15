"""Live Auth0/OIDC Coach Product API proof for an isolated Staging deployment.

The script never prints or persists bearer tokens. It performs GET-only checks.
"""
from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request


def request(base: str, path: str, token: str | None = None, extra_headers: dict[str, str] | None = None):
    headers = {"Accept": "application/json"}
    if token:
        headers["Authorization"] = "Bearer " + token
    if extra_headers:
        headers.update(extra_headers)
    req = urllib.request.Request(base.rstrip("/") + path, headers=headers, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=20) as response:
            raw = response.read()
            return response.status, json.loads(raw.decode("utf-8")) if raw else {}
    except urllib.error.HTTPError as exc:
        raw = exc.read()
        try:
            payload = json.loads(raw.decode("utf-8")) if raw else {}
        except Exception:
            payload = {}
        return exc.code, payload


def require_status(label: str, actual: int, expected: int):
    if actual != expected:
        raise RuntimeError(f"{label}: expected HTTP {expected}, received HTTP {actual}")
    print(f"PASS {label}: HTTP {expected}")


def main():
    base = os.environ["KAIZO_STAGING_API_URL"].strip().rstrip("/")
    token = os.environ["KAIZO_OIDC_BEARER_TOKEN"].strip()
    athlete_id = os.environ["KAIZO_STAGING_OWNED_ATHLETE_ID"].strip()
    staging_host = os.environ.get("KAIZO_STAGING_API_HOST", "").strip().lower().rstrip(".")
    production_host = os.environ.get("KAIZO_PRODUCTION_API_HOST", "").strip().lower().rstrip(".")
    parsed_base = urllib.parse.urlparse(base)
    actual_host = (parsed_base.hostname or "").lower().rstrip(".")
    if parsed_base.scheme != "https" or not actual_host:
        raise RuntimeError("Staging API URL must be an HTTPS URL with a hostname")
    if parsed_base.username or parsed_base.password or parsed_base.query or parsed_base.fragment:
        raise RuntimeError("Staging API URL must not contain credentials, query parameters, or fragments")
    if not staging_host or not production_host:
        raise RuntimeError("Trusted KAIZO_STAGING_API_HOST and KAIZO_PRODUCTION_API_HOST variables are required")
    if staging_host == production_host:
        raise RuntimeError("Refusing Auth0 proof: configured Staging and Production API hosts must differ")
    if actual_host != staging_host:
        raise RuntimeError("Staging API URL host does not match the trusted KAIZO_STAGING_API_HOST")
    if actual_host == production_host:
        raise RuntimeError("Refusing Auth0 proof: target host matches the configured Production API host")
    if not token or not athlete_id:
        raise RuntimeError("Staging Bearer token and owned athlete ID are required")

    status, identity = request(base, "/api/v1/product/auth/oidc/verify", token)
    require_status("Auth0 JWT signature / issuer / audience / expiry verification", status, 200)
    if identity.get("verified") is not True or identity.get("source") != "oidc_jwt":
        raise RuntimeError("OIDC verification endpoint did not return a verified JWT principal")

    status, roster = request(base, "/api/v1/product/coach/athletes", token)
    require_status("Product permission + Coach roster authorization", status, 200)
    athletes = roster.get("athletes", [])
    if not isinstance(athletes, list) or not any(str(row.get("athlete_id")) == athlete_id for row in athletes):
        raise RuntimeError("The supplied test athlete is not present in this authenticated Coach roster")

    encoded = urllib.parse.quote(athlete_id, safe="")
    status, _ = request(base, f"/api/v1/product/coach/athletes/{encoded}", token)
    require_status("Owned athlete detail read", status, 200)

    status, spoofed_roster = request(base, "/api/v1/product/coach/athletes", token, {
        "X-KAIZO-Actor": "forged-actor", "X-KAIZO-Role": "admin",
        "X-KAIZO-Tenant": "forged-tenant", "X-KAIZO-Resource-Owner": "foreign-athlete",
    })
    require_status("Verified token remains authoritative over spoofed identity headers", status, 200)
    if not any(str(row.get("athlete_id")) == athlete_id for row in spoofed_roster.get("athletes", [])):
        raise RuntimeError("Spoofed identity headers changed the authenticated Coach roster")

    status, _ = request(base, "/api/v1/product/coach/athletes")
    require_status("Anonymous Coach API denial", status, 401)

    status, _ = request(base, "/api/v1/product/coach/athletes", "invalid-not-a-jwt")
    require_status("Invalid Bearer token denial", status, 401)

    status, _ = request(base, "/api/v1/product/coach/athletes", None, {
        "X-KAIZO-Actor": "forged-actor", "X-KAIZO-Role": "coach",
        "X-KAIZO-Tenant": "forged-tenant",
    })
    require_status("Caller-supplied identity header spoofing denial", status, 401)

    foreign_id = os.getenv("KAIZO_STAGING_FOREIGN_ATHLETE_ID", "").strip()
    if foreign_id:
        encoded_foreign = urllib.parse.quote(foreign_id, safe="")
        status, _ = request(base, f"/api/v1/product/coach/athletes/{encoded_foreign}", token)
        require_status("Cross-Coach / cross-tenant athlete denial", status, 404)

    wrong_audience_token = os.getenv("KAIZO_OIDC_WRONG_AUDIENCE_TOKEN", "").strip()
    if wrong_audience_token:
        status, _ = request(base, "/api/v1/product/auth/oidc/verify", wrong_audience_token)
        require_status("Wrong-audience Auth0 token denial", status, 401)

    no_product_token = os.getenv("KAIZO_OIDC_NO_PRODUCT_TOKEN", "").strip()
    if no_product_token:
        status, _ = request(base, "/api/v1/product/coach/athletes", no_product_token)
        require_status("Auth0 token without Product permission denial", status, 403)

    non_coach_token = os.getenv("KAIZO_OIDC_NONCOACH_TOKEN", "").strip()
    if non_coach_token:
        status, _ = request(base, "/api/v1/product/coach/athletes", non_coach_token)
        require_status("Auth0 non-Coach role denial", status, 403)

    print("PASS Auth0 Staging live proof completed; bearer token was not printed.")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"FAIL Auth0 Staging live proof: {exc}", file=sys.stderr)
        sys.exit(1)
