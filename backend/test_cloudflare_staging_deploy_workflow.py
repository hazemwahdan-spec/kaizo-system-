"""Static contract tests for the manual Cloudflare Staging deploy workflow."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "cloudflare-worker-staging-deploy.yml"


def test_manual_worker_deploy_is_pinned_to_staging_and_preflights_token():
    text = WORKFLOW.read_text(encoding="utf-8")
    assert "workflow_dispatch:" in text
    assert 'case "$GITHUB_REF_NAME" in' in text
    assert "main|fix/coach-staging-*)" in text
    assert 'CLOUDFLARE_ACCOUNT_ID: "962a31c413bed22002379d4e0a42cfe8"' in text
    assert "secrets.CLOUDFLARE_API_TOKEN" in text
    assert "secrets.CLOUDFLARE_ACCOUNT_ID" not in text
    assert 'f"/accounts/{account_id}/tokens/verify"' in text
    assert 'request("/user/tokens/verify"' in text
    assert "allow_auth_fallback=True" in text
    assert "/accounts/{account_id}/workers/scripts?per_page=100" in text
    assert 'status != "active"' in text
    assert "Verify memory-only import guard" in text
    assert "KAIZO_PERSISTENCE_MODE" in text and "memory" in text
    assert "pywrangler deploy --dry-run" in text
    assert "pywrangler deploy\n" in text
    assert "print(token)" not in text
    assert 'echo "$CLOUDFLARE_API_TOKEN"' not in text
    assert text.index("pywrangler deploy --dry-run") < text.index("pywrangler deploy\n")
