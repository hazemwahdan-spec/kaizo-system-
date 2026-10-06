from drill_library import Drill, serialize_drill


def test_feat_031_valid_drill_serializes_with_guardrails():
    drill = Drill(
        drill_id="DRILL-001",
        name="Seoi entry reaction drill",
        judo_area="Nage-waza",
        technical_skill="Seoi Nage entry",
        problem_target="late entry",
        decision_target="select entry after partner reaction",
        age_suitability="youth with coach screening",
        skill_level="intermediate",
        execution_pattern="kumi-kata to controlled entry",
        coach_cues=("control sleeve", "enter on reaction"),
        kpi="clean entry rate",
        safety_constraints="controlled speed; coach-selected partner",
        evidence=("EVID-001",),
        source=("Kodokan/IJF reference",),
        coach_review=True,
    )
    result = serialize_drill(drill)
    assert result["coach_final_authority"] is True
    assert result["execution_authorized"] is False
    assert result["evidence"] == ["EVID-001"]


def test_feat_031_rejects_missing_evidence():
    drill = Drill(
        drill_id="DRILL-002",
        name="Grip drill",
        judo_area="Kumi-kata",
        technical_skill="grip control",
        problem_target="poor grip",
        decision_target="select grip",
        age_suitability="youth",
        skill_level="beginner",
        execution_pattern="partner grip exchange",
        kpi="grip success rate",
        safety_constraints="controlled contact",
    )
    try:
        serialize_drill(drill)
    except ValueError as exc:
        assert "evidence" in str(exc)
    else:
        raise AssertionError("missing evidence must be rejected")
