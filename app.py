"""Vercel entrypoint for the KAIZO Core Engine FastAPI application.

Keep the Core runtime modules in backend/ and the shared productization package
at the repository root. Vercel imports this file from the repository root.
"""
from pathlib import Path
import sys

_REPOSITORY_ROOT = Path(__file__).resolve().parent
_BACKEND_DIR = _REPOSITORY_ROOT / "backend"

# Core runtime modules use top-level imports (for example, import persistence).
# Add backend/ without removing the repository root, which is needed for
# productization and other shared packages.
for _path in (str(_BACKEND_DIR), str(_REPOSITORY_ROOT)):
    if _path not in sys.path:
        sys.path.insert(0, _path)

from main import app  # noqa: E402

__all__ = ["app"]
