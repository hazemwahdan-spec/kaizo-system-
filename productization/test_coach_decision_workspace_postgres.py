"""FEAT-009 PostgreSQL integration: full decision workspace is Coach-owned and read-only."""
import json
import sys
from pathlib import Path
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "backend"))

import persistence
import training_workflow
from productization import coach_roster, coach_decision_workspace


def test_workspace_reads_assessment_evidence_and_decision_lineage_with_owner_isolation():
    assert persistence.is_postgres_enabled()
    persistence.initialize()
    training_workflow._ensure_schema()

    tenant = "TENANT-" + uuid4().hex
    coach = "COACH-" + uuid4().hex
    owned = coach_roster.create_owned_athlete(
        tenant_id=tenant, coach_actor_id=coach, display_name="FEAT-009 owner"
    )
    other_coach = coach_roster.create_owned_athlete(
        tenant_id=tenant, coach_actor_id="COACH-" + uuid4().hex,
        display_name="FEAT-009 other coach"
    )
    other_tenant = coach_roster.create_owned_athlete(
        tenant_id="TENANT-" + uuid4().hex, coach_actor_id=coach,
        display_name="FEAT-009 other tenant"
    )
    aid = owned["athlete_id"]
    assessment = "ASSESS-" + uuid4().hex
    foreign_assessment = "ASSESS-" + uuid4().hex
    evidence = "EVIDENCE-" + uuid4().hex
    unlinked_evidence = "EVIDENCE-" + uuid4().hex
    decision = "DEC-" + uuid4().hex
    problem = "PROB-" + uuid4().hex
    diagnosis = "DIAG-" + uuid4().hex
    candidate = "CAND-" + uuid4().hex
    plan = "PLAN-" + uuid4().hex
    session = "SESSION-" + uuid4().hex
    workflow_record = "WF-" + uuid4().hex
    now = "2026-11-03T12:00:00+00:00"

    with persistence.connection() as conn:
        with conn.cursor() as cur:
            for athlete_id, assessment_id in (
                (aid, assessment),
                (other_coach["athlete_id"], foreign_assessment),
                (other_tenant["athlete_id"], "ASSESS-" + uuid4().hex),
            ):
                cur.execute("""
                    INSERT INTO kaizo_assessments
                    (assessment_id,athlete_id,template_id,measurements,recorded_by,assessed_at,created_at)
                    VALUES (%s,%s,%s,%s::jsonb,%s,%s,%s)
                """, (assessment_id, athlete_id, "TEMPLATE-1",
                      json.dumps({"grip_strength": 21.5}), coach, now, now))

            cur.execute("""
                INSERT INTO kaizo_evidence_records
                (evidence_id,subject_type,subject_id,evidence_level,status,source_ref,claim,
                 observed_value,verified_by,verified_at,notes)
                VALUES (%s,'assessment',%s,'E3','VERIFIED','assessment://feat009',
                        'Measurement is supported by source evidence.',
                        %s::jsonb,%s,%s,NULL)
            """, (evidence, assessment, json.dumps({"grip_strength": 21.5}), coach, now))
            cur.execute("""
                INSERT INTO kaizo_evidence_records
                (evidence_id,subject_type,subject_id,evidence_level,status,source_ref,claim,
                 observed_value,verified_by,verified_at,notes)
                VALUES (%s,'assessment',%s,'E3','VERIFIED','assessment://unlinked',
                        'This evidence is not attached and must not appear.',
                        '{}'::jsonb,%s,%s,NULL)
            """, (unlinked_evidence, assessment, coach, now))
            cur.execute("""
                INSERT INTO kaizo_assessment_evidence_attachments
                (assessment_id,evidence_id,attached_by,attached_at)
                VALUES (%s,%s,%s,%s),(%s,%s,%s,%s)
            """, (assessment, evidence, coach, now, assessment,
                  "MISSING-EVIDENCE-" + uuid4().hex, coach, now))

            cur.execute("""
                INSERT INTO kaizo_state_snapshots
                (snapshot_id,athlete_id,assessment_id,snapshot_type,measurements,kpis,
                 captured_by,captured_at,created_at)
                VALUES (%s,%s,%s,'BASELINE',%s::jsonb,%s::jsonb,%s,%s,%s)
            """, ("SNAP-" + uuid4().hex, aid, assessment,
                  json.dumps({"grip_strength": 21.5}), json.dumps({}), coach, now, now))

            cur.execute("""
                INSERT INTO kaizo_problem_statements
                (problem_id,athlete_id,assessment_id,statement,problem_type,impact,context,
                 structured_fields,status,created_by,created_at,updated_at)
                VALUES (%s,%s,%s,'Grip entry timing problem','TECHNICAL','HIGH',
                        '{}'::jsonb,'{}'::jsonb,'RECORDED',%s,%s,%s)
            """, (problem, aid, assessment, coach, now, now))
            cur.execute("""
                INSERT INTO kaizo_cause_context_framings
                (framing_id,problem_id,athlete_id,assessment_id,cause,context,
                 contributing_factors,framed_by,framed_at)
                VALUES (%s,%s,%s,%s,'Delayed grip entry','{}'::jsonb,'[]'::jsonb,%s,%s)
            """, ("FRAME-" + uuid4().hex, problem, aid, assessment, coach, now))
            cur.execute("""
                INSERT INTO kaizo_evidence_linked_diagnoses
                (diagnosis_id,problem_id,athlete_id,assessment_id,evidence_ids,diagnosis,
                 diagnosed_by,confidence,resolution_state,diagnosed_at)
                VALUES (%s,%s,%s,%s,%s::jsonb,'Evidence-linked diagnosis',%s,'MEDIUM','UNRESOLVED',%s)
            """, (diagnosis, problem, aid, assessment, json.dumps([evidence]), coach, now))
            cur.execute("""
                INSERT INTO kaizo_decision_candidates
                (candidate_id,diagnosis_id,problem_id,athlete_id,assessment_id,candidate_type,
                 title,rationale,source_diagnosis,status,generated_by,created_at)
                VALUES (%s,%s,%s,%s,%s,'TECHNICAL_ADAPTATION','Grip-entry drill',
                        'Improve timing','Evidence-linked diagnosis','PROPOSED',%s,%s)
            """, (candidate, diagnosis, problem, aid, assessment, coach, now))
            cur.execute("""
                INSERT INTO kaizo_decision_rationales
                (rationale_id,candidate_id,diagnosis_id,problem_id,athlete_id,assessment_id,
                 rationale,evidence_ids,recorded_by,recorded_at)
                VALUES (%s,%s,%s,%s,%s,%s,'Rationale backed by evidence',%s::jsonb,%s,%s)
            """, ("RAT-" + uuid4().hex, candidate, diagnosis, problem, aid, assessment,
                  json.dumps([evidence]), coach, now))
            cur.execute("""
                INSERT INTO kaizo_decision_comparisons
                (comparison_id,diagnosis_id,candidate_ids,alternatives,comparison_status,compared_by,compared_at)
                VALUES (%s,%s,%s::jsonb,%s::jsonb,'COMPARED',%s,%s)
            """, ("COMP-" + uuid4().hex, diagnosis, json.dumps([candidate]),
                  json.dumps([{"candidate_id": candidate, "tradeoff": "Lower load"}]), coach, now))
            cur.execute("""
                INSERT INTO kaizo_coach_decision_reviews
                (review_id,candidate_id,diagnosis_id,problem_id,athlete_id,assessment_id,
                 action,status,coach_id,override_reason,reviewed_at)
                VALUES (%s,%s,%s,%s,%s,%s,'CONFIRM','CONFIRMED',%s,NULL,%s)
            """, ("REVIEW-" + uuid4().hex, candidate, diagnosis, problem, aid, assessment, coach, now))
            cur.execute("""
                INSERT INTO kaizo_decision_records
                (decision_id,candidate_id,diagnosis_id,problem_id,athlete_id,assessment_id,
                 candidate_type,coach_action,coach_id,decision_summary,outcome_intent,status,recorded_at)
                VALUES (%s,%s,%s,%s,%s,%s,'TECHNICAL_ADAPTATION','CONFIRM',%s,
                        'Coach-confirmed grip timing decision','Improve independent entry timing','RECORDED',%s)
            """, (decision, candidate, diagnosis, problem, aid, assessment, coach, now))
            cur.execute("""
                INSERT INTO kaizo_training_plans
                (plan_id,athlete_id,decision_id,title,objective,constraints,status,created_by,created_at)
                VALUES (%s,%s,%s,'Grip timing plan','Improve timing','{}'::jsonb,'DRAFT',%s,%s)
            """, (plan, aid, decision, coach, now))
            cur.execute("""
                INSERT INTO kaizo_training_sessions
                (session_id,plan_id,athlete_id,title,duration_minutes,blocks,status,created_by,created_at)
                VALUES (%s,%s,%s,'Grip timing session',30,'[]'::jsonb,'PLANNED',%s,%s)
            """, (session, plan, aid, coach, now))
            cur.execute("""
                INSERT INTO kaizo_training_workflow_records
                (record_id,feature_id,athlete_id,decision_id,session_id,payload,created_by,
                 created_at,coach_final_authority,execution_authorized)
                VALUES (%s,'FEAT-036',%s,%s,%s,'{}'::jsonb,%s,%s,TRUE,FALSE)
            """, (workflow_record, aid, decision, session, coach, now))

            cur.execute("SELECT COUNT(*) FROM kaizo_audit_logs")
            audit_before = cur.fetchone()[0]
            cur.execute("SELECT COUNT(*) FROM kaizo_assessment_evidence_attachments")
            attachments_before = cur.fetchone()[0]
            cur.execute("SELECT COUNT(*) FROM kaizo_decision_records")
            decisions_before = cur.fetchone()[0]

    workspace = coach_decision_workspace.get_coach_decision_workspace(
        tenant_id=tenant, coach_actor_id=coach, athlete_id=aid
    )
    assert workspace is not None
    assert workspace["status"] == "WORKSPACE_AVAILABLE"
    assert workspace["available"] is True and workspace["read_only"] is True
    assert workspace["coach_final_authority"] is True
    assert workspace["execution_authorized"] is False
    assert len(workspace["assessments"]) == 1
    attached = workspace["assessments"][0]["evidence_attachments"]
    assert any(x["evidence_id"] == evidence and x["evidence_record_found"] for x in attached)
    assert any(x["evidence_id"].startswith("MISSING-EVIDENCE-") and not x["evidence_record_found"] for x in attached)
    assert unlinked_evidence not in [x["evidence_id"] for x in attached]
    assert workspace["state_snapshots"][0]["assessment_id"] == assessment
    assert workspace["problem_statements"][0]["problem_id"] == problem
    assert workspace["cause_context_framings"][0]["problem_id"] == problem
    assert workspace["diagnoses"][0]["diagnosis_id"] == diagnosis
    assert workspace["decision_candidates"][0]["candidate_id"] == candidate
    assert workspace["decision_rationales"][0]["candidate_id"] == candidate
    assert workspace["decision_comparisons"][0]["diagnosis_id"] == diagnosis
    assert workspace["coach_reviews"][0]["candidate_id"] == candidate
    assert workspace["decisions"][0]["decision_id"] == decision
    assert workspace["training_plans"][0]["plan_id"] == plan
    assert workspace["training_sessions"][0]["session_id"] == session
    assert workspace["training_records"][0]["record_id"] == workflow_record
    assert coach_decision_workspace.get_coach_decision_workspace(
        tenant_id=tenant, coach_actor_id="FOREIGN-COACH", athlete_id=aid
    ) is None
    assert coach_decision_workspace.get_coach_decision_workspace(
        tenant_id="FOREIGN-TENANT", coach_actor_id=coach, athlete_id=aid
    ) is None

    with persistence.connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM kaizo_audit_logs")
            assert cur.fetchone()[0] == audit_before
            cur.execute("SELECT COUNT(*) FROM kaizo_assessment_evidence_attachments")
            assert cur.fetchone()[0] == attachments_before
            cur.execute("SELECT COUNT(*) FROM kaizo_decision_records")
            assert cur.fetchone()[0] == decisions_before
