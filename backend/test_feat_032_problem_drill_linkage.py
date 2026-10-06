from problem_drill_linkage import ProblemDrillLink, serialize_link

def test_valid_link():
    result=serialize_link(ProblemDrillLink("L1","PROB-1","DRILL-1","targets entry timing","coach"))
    assert result["problem_id"]=="PROB-1"
    assert result["coach_final_authority"] is True
    assert result["execution_authorized"] is False

def test_rejects_empty_drill():
    try:
        serialize_link(ProblemDrillLink("L1","PROB-1","","rationale","coach"))
    except ValueError as exc:
        assert "drill_id" in str(exc)
    else:
        raise AssertionError("empty drill_id must be rejected")
