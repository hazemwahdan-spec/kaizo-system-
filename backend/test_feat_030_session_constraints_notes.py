from backend.session_constraints_notes import SessionConstraintNote, validate_item, serialize_item

def test_feat_030_session_constraints_and_notes():
    constraint=SessionConstraintNote("030-1","SESSION-030","CONSTRAINT","No uncontrolled randori","HIGH","coach")
    validate_item(constraint)
    data=serialize_item(constraint)
    assert data["kind"]=="CONSTRAINT"
    assert data["priority"]=="HIGH"
    assert data["coach_final_authority"] is True
    assert data["execution_authorized"] is False

    note=SessionConstraintNote("030-2","SESSION-030","NOTE","Use left-side entry first","NORMAL","coach")
    assert serialize_item(note)["kind"]=="NOTE"

def test_feat_030_rejects_invalid_kind():
    bad=SessionConstraintNote("030-3","SESSION-030","BAD","x","NORMAL","coach")
    try:
        validate_item(bad)
        assert False
    except ValueError as exc:
        assert "kind" in str(exc)
