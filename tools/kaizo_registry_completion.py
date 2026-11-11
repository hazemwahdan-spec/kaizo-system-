#!/usr/bin/env python3
"""Validate and calculate the KAIZO Master Requirements & Evidence Registry.

Standard-library only. Conservative policy:
- Only CLOSED_VERIFIED rows with VERIFIED_PASS evidence and closure approval earn credit.
- Historical evidence does not count as current PASS.
- The official whole-project percentage is suppressed until baseline controls are approved.
- This script does not infer status from prose or automatically close requirements.
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import Counter
from decimal import Decimal, InvalidOperation
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_REGISTRY = ROOT / "docs/audits/KAIZO_MASTER_REQUIREMENTS_EVIDENCE_REGISTRY_v1.0.csv"
DEFAULT_EVIDENCE = ROOT / "docs/audits/KAIZO_MASTER_EVIDENCE_LEDGER_v1.0.csv"
DEFAULT_CONTROL = ROOT / "docs/audits/KAIZO_MASTER_REGISTRY_CONTROL_v1.0.json"

CREDITED_STATUS = "CLOSED_VERIFIED"
CREDITED_EVIDENCE = "VERIFIED_PASS"
EXCLUDED_STATUSES = {"DUPLICATE_LINKED"}
ALLOWED_STATUSES = {
    "CLOSED_VERIFIED", "PARTIAL", "OPEN_NOT_PROVEN", "BLOCKED",
    "NOT_VERIFIED", "FUTURE", "DUPLICATE_LINKED"
}
ALLOWED_EVIDENCE_STATUSES = {
    "VERIFIED_PASS", "VERIFIED_FAIL", "HOLD", "NOT_VERIFIED", "HISTORICAL_ONLY"
}
REQUIRED_COLUMNS = {
    "requirement_id", "title", "domain", "scope", "acceptance_criteria",
    "verification_method", "required_evidence", "status", "evidence_status",
    "weight", "proof_url", "closure_approved_by", "closure_date"
}


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def truthy(value: object) -> bool:
    return str(value).strip().lower() in {"true", "yes", "1"}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--registry", type=Path, default=DEFAULT_REGISTRY)
    parser.add_argument("--evidence", type=Path, default=DEFAULT_EVIDENCE)
    parser.add_argument("--control", type=Path, default=DEFAULT_CONTROL)
    args = parser.parse_args()

    errors: list[str] = []
    warnings: list[str] = []
    try:
        rows = read_csv(args.registry)
        evidence_rows = read_csv(args.evidence)
        control = json.loads(args.control.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, csv.Error) as exc:
        print(f"FATAL: could not load registry inputs: {exc}", file=sys.stderr)
        return 2

    if not rows:
        errors.append("Registry has no requirement rows.")
    if rows:
        missing_columns = REQUIRED_COLUMNS - set(rows[0].keys())
        if missing_columns:
            errors.append("Missing required columns: " + ", ".join(sorted(missing_columns)))

    ids = [r.get("requirement_id", "").strip() for r in rows]
    blank_ids = [i + 2 for i, value in enumerate(ids) if not value]
    if blank_ids:
        errors.append(f"Blank requirement_id at CSV line(s): {blank_ids}")
    duplicates = [key for key, count in Counter(ids).items() if key and count > 1]
    if duplicates:
        errors.append("Duplicate requirement IDs: " + ", ".join(duplicates))

    evidence_ids = [r.get("evidence_id", "").strip() for r in evidence_rows]
    duplicate_evidence = [key for key, count in Counter(evidence_ids).items() if key and count > 1]
    if duplicate_evidence:
        errors.append("Duplicate evidence IDs: " + ", ".join(duplicate_evidence))
    known_ids = set(ids)
    evidence_by_requirement: dict[str, list[dict[str, str]]] = {}
    for item in evidence_rows:
        req_id = item.get("requirement_id", "").strip()
        if req_id not in known_ids:
            errors.append(
                f"Evidence {item.get('evidence_id', '')} references unknown requirement "
                f"{req_id}."
            )
        evidence_by_requirement.setdefault(req_id, []).append(item)
        status = item.get("evidence_status", "").strip()
        if status and status not in ALLOWED_EVIDENCE_STATUSES:
            errors.append(f"Unknown evidence status {status!r} on {item.get('evidence_id', '')}.")

    included: list[tuple[dict[str, str], Decimal]] = []
    excluded_duplicates = 0
    for line, row in enumerate(rows, start=2):
        status = row.get("status", "").strip()
        evidence_status = row.get("evidence_status", "").strip()
        if status not in ALLOWED_STATUSES:
            errors.append(f"Unknown requirement status {status!r} at CSV line {line}.")
        if evidence_status and evidence_status not in ALLOWED_EVIDENCE_STATUSES:
            errors.append(f"Unknown evidence status {evidence_status!r} at CSV line {line}.")
        try:
            weight = Decimal(row.get("weight", "").strip())
        except InvalidOperation:
            errors.append(f"Invalid weight at CSV line {line}: {row.get('weight')!r}")
            continue
        if weight <= 0:
            errors.append(f"Weight must be greater than zero at CSV line {line}.")
        if status == "DUPLICATE_LINKED":
            excluded_duplicates += 1
            continue
        if not row.get("acceptance_criteria", "").strip():
            errors.append(f"Missing acceptance criteria at CSV line {line}.")
        if not row.get("verification_method", "").strip():
            errors.append(f"Missing verification method at CSV line {line}.")
        included.append((row, weight))

    if errors:
        print("VALIDATION: FAIL")
        for error in errors:
            print(f"ERROR: {error}")
        return 1

    total_weight = sum((weight for _, weight in included), Decimal("0"))
    earned_weight = Decimal("0")
    status_counts: Counter[str] = Counter()
    evidence_counts: Counter[str] = Counter()
    unknown_weight = Decimal("0")
    critical_open: list[str] = []

    for row, weight in included:
        status = row.get("status", "").strip()
        ev_status = row.get("evidence_status", "").strip()
        status_counts[status] += 1
        evidence_counts[ev_status or "UNSET"] += 1
        if ev_status in {"NOT_VERIFIED", "HISTORICAL_ONLY", "HOLD", ""}:
            unknown_weight += weight
        can_credit = (
            status == CREDITED_STATUS
            and ev_status == CREDITED_EVIDENCE
            and bool(row.get("proof_url", "").strip())
            and bool(row.get("closure_approved_by", "").strip())
            and bool(row.get("closure_date", "").strip())
            and bool(row.get("acceptance_criteria", "").strip())
            and any(
                item.get("evidence_status", "").strip() == CREDITED_EVIDENCE
                and bool(item.get("source_url", "").strip())
                and bool(item.get("source_commit_or_run", "").strip())
                and bool(item.get("environment", "").strip())
                and bool(item.get("observed_at", "").strip())
                for item in evidence_by_requirement.get(row.get("requirement_id", "").strip(), [])
            )
        )
        if can_credit:
            earned_weight += weight
        elif row.get("criticality", "").strip().lower() == "critical":
            critical_open.append(row.get("requirement_id", ""))

    ratio = (earned_weight / total_weight * Decimal("100")) if total_weight else Decimal("0")
    controls_approved = all(
        truthy(control.get(key))
        for key in (
            "inventory_complete", "baseline_approved", "duplicates_reconciled",
            "conflicts_resolved", "weights_frozen", "independent_audit_approved"
        )
    ) and truthy(control.get("official_percentage_allowed"))

    print("KAIZO MASTER REQUIREMENTS & EVIDENCE REGISTRY")
    print(f"Registry rows: {len(rows)}")
    print(f"Evidence ledger rows: {len(evidence_rows)}")
    print(f"Duplicate-linked rows excluded: {excluded_duplicates}")
    print(f"Requirement status counts: {dict(sorted(status_counts.items()))}")
    print(f"Evidence status counts: {dict(sorted(evidence_counts.items()))}")
    print(f"Included requirements: {len(included)}")
    print(f"Total provisional weight: {total_weight}")
    print(f"Earned weight under strict evidence rule: {earned_weight}")
    print(f"Seed-only weighted ratio (NOT whole-project completion): {ratio.quantize(Decimal('0.01'))}%")
    print(f"Weight attached to unverified/held/historical evidence: {unknown_weight}")
    print(f"Critical requirements not proven closed: {len(critical_open)}")
    if critical_open:
        print("Critical open/not-proven IDs: " + ", ".join(critical_open))

    if controls_approved:
        print(f"OFFICIAL WHOLE-PROJECT COMPLETION: {ratio.quantize(Decimal('0.01'))}%")
    else:
        print("OFFICIAL WHOLE-PROJECT COMPLETION: SUPPRESSED")
        print("Reason: inventory/baseline/duplicate/conflict/weight/auditor controls are not all approved.")
        print("Do not report the seed-only ratio as the project's completion percentage.")

    if critical_open:
        warnings.append("One or more critical requirements are not proven closed.")
    if not controls_approved:
        warnings.append("The registry is not yet approved as a complete project baseline.")
    for warning in warnings:
        print(f"WARNING: {warning}")

    print("VALIDATION: PASS (structural validation only; not a claim of project completion)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
