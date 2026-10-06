from backend.progression_rules import ProgressionRegressionRule, validate_rule

def test_progression_and_regression_rules():
    progress = ProgressionRegressionRule("R-029-P","quality progress","technical_quality","GTE",8,"PROGRESS",2,"coach")
    validate_rule(progress)
    assert progress.evaluate(8)["action"] == "PROGRESS"
    assert progress.evaluate(7)["action"] == "HOLD"

    regression = ProgressionRegressionRule("R-029-R","quality regression","technical_quality","LT",6,"REGRESS",1,"coach")
    validate_rule(regression)
    result = regression.evaluate(5)
    assert result["action"] == "REGRESS"
    assert result["adjustment"] == 1
    assert result["coach_final_authority"] is True
    assert result["execution_authorized"] is False
