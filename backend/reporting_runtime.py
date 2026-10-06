"""KAIZO Reporting Runtime — FEAT-071..075.

Reports are derived from approved operational records. Export is a controlled
representation of approved data only; no report authorizes execution.
"""
from datetime import datetime, timezone
from typing import Any, Dict, List
from uuid import uuid4
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
import csv
import io
import json

import persistence

router = APIRouter(prefix="/api/v1/reporting", tags=["Reporting"])

PROGRESS: Dict[str, Dict[str, Any]] = {}
KPI_TRENDS: Dict[str, Dict[str, Any]] = {}
COACH_SUMMARIES: Dict[str, Dict[str, Any]] = {}
ACADEMY_DASHBOARDS: Dict[str, Dict[str, Any]] = {}
EXPORTS: Dict[str, Dict[str, Any]] = {}


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def authority(ok: bool) -> None:
    if not ok:
        raise HTTPException(status_code=409, detail="COACH_FINAL_AUTHORITY_REQUIRED")


def required(**values: str) -> None:
    for key, value in values.items():
        if not value or not value.strip():
            raise HTTPException(status_code=400, detail=f"{key} is required")


def approved_records(records: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    if not records:
        raise HTTPException(status_code=400, detail="at least one approved record is required")
    invalid = [r for r in records if r.get("approval_status") != "APPROVED"]
    if invalid:
        raise HTTPException(status_code=409, detail="all records must have approval_status=APPROVED")
    return records


def audit(actor: str, action: str, payload: Dict[str, Any]) -> None:
    if persistence.is_postgres_enabled():
        try:
            persistence.append_audit({
                "actor_id": actor, "action": action, "occurred_at": now(),
                "payload": payload, "evidence_refs": payload.get("evidence_refs", []),
                "coach_final_authority": True, "execution_authorized": False,
            })
        except Exception:
            pass


class ProgressCreate(BaseModel):
    athlete_id: str
    period: str
    progress: Dict[str, Any]
    recorded_by: str
    evidence_refs: List[str] = Field(default_factory=list)
    coach_final_authority: bool = True


class KPITrendCreate(BaseModel):
    athlete_id: str
    kpi_id: str
    period: str
    trend: Dict[str, Any]
    recorded_by: str
    evidence_refs: List[str] = Field(default_factory=list)
    coach_final_authority: bool = True


class CoachSummaryCreate(BaseModel):
    coach_id: str
    period: str
    summary: Dict[str, Any]
    recorded_by: str
    evidence_refs: List[str] = Field(default_factory=list)
    coach_final_authority: bool = True


class AcademyDashboardCreate(BaseModel):
    academy_id: str
    period: str
    metrics: Dict[str, Any]
    recorded_by: str
    evidence_refs: List[str] = Field(default_factory=list)
    coach_final_authority: bool = True


class ExportCreate(BaseModel):
    approved_record_ids: List[str]
    format: str
    records: List[Dict[str, Any]]
    requested_by: str
    evidence_refs: List[str] = Field(default_factory=list)
    coach_final_authority: bool = True


@router.post("/progress", status_code=201)
def create_progress(req: ProgressCreate) -> Dict[str, Any]:
    authority(req.coach_final_authority)
    required(athlete_id=req.athlete_id, period=req.period, recorded_by=req.recorded_by)
    if not req.progress:
        raise HTTPException(status_code=400, detail="progress is required")
    item = {"report_id": str(uuid4()), "athlete_id": req.athlete_id,
            "period": req.period, "progress": req.progress,
            "recorded_by": req.recorded_by, "evidence_refs": req.evidence_refs,
            "created_at": now(), "coach_final_authority": True,
            "execution_authorized": False}
    PROGRESS[item["report_id"]] = item
    audit(req.recorded_by, "ATHLETE_PROGRESS_REPORTED", item)
    return item


@router.post("/kpi-trend", status_code=201)
def create_kpi_trend(req: KPITrendCreate) -> Dict[str, Any]:
    authority(req.coach_final_authority)
    required(athlete_id=req.athlete_id, kpi_id=req.kpi_id, period=req.period, recorded_by=req.recorded_by)
    if not req.trend:
        raise HTTPException(status_code=400, detail="trend is required")
    item = {"report_id": str(uuid4()), "athlete_id": req.athlete_id,
            "kpi_id": req.kpi_id, "period": req.period, "trend": req.trend,
            "recorded_by": req.recorded_by, "evidence_refs": req.evidence_refs,
            "created_at": now(), "coach_final_authority": True,
            "execution_authorized": False}
    KPI_TRENDS[item["report_id"]] = item
    audit(req.recorded_by, "KPI_TREND_REPORTED", item)
    return item


@router.post("/coach-summary", status_code=201)
def create_coach_summary(req: CoachSummaryCreate) -> Dict[str, Any]:
    authority(req.coach_final_authority)
    required(coach_id=req.coach_id, period=req.period, recorded_by=req.recorded_by)
    if not req.summary:
        raise HTTPException(status_code=400, detail="summary is required")
    item = {"report_id": str(uuid4()), "coach_id": req.coach_id,
            "period": req.period, "summary": req.summary,
            "recorded_by": req.recorded_by, "evidence_refs": req.evidence_refs,
            "created_at": now(), "coach_final_authority": True,
            "execution_authorized": False}
    COACH_SUMMARIES[item["report_id"]] = item
    audit(req.recorded_by, "COACH_PERFORMANCE_SUMMARY_REPORTED", item)
    return item


@router.post("/academy-dashboard", status_code=201)
def create_academy_dashboard(req: AcademyDashboardCreate) -> Dict[str, Any]:
    authority(req.coach_final_authority)
    required(academy_id=req.academy_id, period=req.period, recorded_by=req.recorded_by)
    if not req.metrics:
        raise HTTPException(status_code=400, detail="metrics are required")
    item = {"report_id": str(uuid4()), "academy_id": req.academy_id,
            "period": req.period, "metrics": req.metrics,
            "recorded_by": req.recorded_by, "evidence_refs": req.evidence_refs,
            "created_at": now(), "coach_final_authority": True,
            "execution_authorized": False}
    ACADEMY_DASHBOARDS[item["report_id"]] = item
    audit(req.recorded_by, "ACADEMY_PERFORMANCE_DASHBOARD_REPORTED", item)
    return item


@router.post("/export", status_code=201)
def create_export(req: ExportCreate) -> Dict[str, Any]:
    authority(req.coach_final_authority)
    required(requested_by=req.requested_by, format=req.format)
    fmt = req.format.upper()
    if fmt not in {"CSV", "JSON"}:
        raise HTTPException(status_code=400, detail="format must be CSV or JSON")
    if not req.approved_record_ids:
        raise HTTPException(status_code=400, detail="approved_record_ids must be non-empty")
    if len(req.approved_record_ids) != len(set(req.approved_record_ids)):
        raise HTTPException(status_code=400, detail="approved_record_ids must be unique")
    records = approved_records(req.records)
    supplied_ids = {str(r.get("record_id")) for r in records}
    missing = [rid for rid in req.approved_record_ids if rid not in supplied_ids]
    if missing:
        raise HTTPException(status_code=409, detail={"missing_approved_records": missing})

    export_id = str(uuid4())
    if fmt == "JSON":
        content = json.dumps(records, ensure_ascii=False, separators=(",", ":"))
        media_type = "application/json"
    else:
        fields = sorted({key for record in records for key in record.keys()})
        out = io.StringIO()
        writer = csv.DictWriter(out, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(records)
        content = out.getvalue()
        media_type = "text/csv"

    item = {"report_id": export_id, "approved_record_ids": req.approved_record_ids,
            "format": fmt, "record_count": len(records), "content": content,
            "media_type": media_type, "requested_by": req.requested_by,
            "evidence_refs": req.evidence_refs, "created_at": now(),
            "coach_final_authority": True, "execution_authorized": False}
    EXPORTS[export_id] = item
    audit(req.requested_by, "APPROVED_DATA_EXPORT_CREATED", item)
    return item


@router.get("/export/{report_id}")
def get_export(report_id: str) -> Dict[str, Any]:
    item = EXPORTS.get(report_id)
    if item is None:
        raise HTTPException(status_code=404, detail="export not found")
    return item
