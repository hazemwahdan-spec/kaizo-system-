"""Executable safety checks for the Cloudflare Staging deployment boundary."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEPLOY = (ROOT / ".github/workflows/cloudflare-worker-staging-deploy.yml").read_text(encoding="utf-8")
CONFIG = json.loads((ROOT / "wrangler.jsonc").read_text(encoding="utf-8"))

# The credential-bearing deployment job must never run from PR or feature refs.
assert "workflow_dispatch:" in DEPLOY
assert "if: github.ref == 'refs/heads/main'" in DEPLOY
assert "CLOUDFLARE_API_TOKEN: ${{ secrets.CLOUDFLARE_API_TOKEN }}" in DEPLOY
assert "pywrangler deploy --config wrangler.jsonc" in DEPLOY

# The root configuration is explicitly Staging-only and memory-only.
assert CONFIG.get("name") == "kaizo-coach-core-staging"
assert CONFIG.get("vars", {}).get("KAIZO_ENVIRONMENT") == "staging"
assert CONFIG.get("vars", {}).get("KAIZO_PERSISTENCE_MODE") == "memory"
assert not CONFIG.get("hyperdrive")
assert "kaizo-system" not in CONFIG.get("name", "")

print("PASS: manual main-only deploy; explicit Staging environment; memory-only Worker target; explicit Wrangler config")
