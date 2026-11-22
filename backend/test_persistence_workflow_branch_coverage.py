"""Guard the persistence validation workflow's stacked Coach PR base filters."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "persistence-adapter-validation.yml"


def _branch_names(section: str) -> set[str]:
    lines = section.splitlines()
    return {
        line.strip()[2:]
        for line in lines
        if line.strip().startswith("- ")
    }


def test_stacked_coach_closure_bases_trigger_persistence_validation():
    source = WORKFLOW.read_text(encoding="utf-8")
    push = source.split("  push:", 1)[1].split("  pull_request:", 1)[0]
    pull_request = source.split("  pull_request:", 1)[1].split("jobs:", 1)[0]
    push_branches = _branch_names(push)
    pull_request_branches = _branch_names(pull_request)
    assert "fix/persistence-validation-stacked-pr-coverage-20261122" in push_branches
    expected = {
        "fix/staging-coach-schema-additive-only-20261119",
        "fix/cloudflare-free-memory-staging-20261119",
        "fix/cloudflare-worker-import-memory-guard-20261120",
    }
    assert expected.issubset(pull_request_branches), f"missing persistence-validation PR bases: {sorted(expected - pull_request_branches)}"
