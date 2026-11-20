"""Regression tests for the memory-only Cloudflare Staging import boundary."""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]


class CloudflareWorkerImportGuardTests(unittest.TestCase):
    def test_memory_and_database_guards_precede_core_app_import(self):
        worker_source = (ROOT / "cloudflare_worker.py").read_text()
        core_source = (ROOT / "backend" / "main.py").read_text()

        core_import = worker_source.index("from app import app")
        self.assertLess(
            worker_source.index('os.environ["KAIZO_ENVIRONMENT"] = "staging"'),
            core_import,
        )
        self.assertLess(
            worker_source.index('os.environ["KAIZO_PERSISTENCE_MODE"] = "memory"'),
            core_import,
        )
        self.assertLess(
            worker_source.index('os.environ.pop("DATABASE_URL", None)'),
            core_import,
        )

        # This is the import-time side effect the Worker bootstrap must block.
        self.assertIn("if persistence.is_postgres_enabled():", core_source)
        self.assertIn("persistence.initialize()", core_source)


if __name__ == "__main__":
    unittest.main()
