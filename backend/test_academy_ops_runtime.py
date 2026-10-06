from fastapi.testclient import TestClient

import academy_ops_runtime as academy


def setup_function():
    academy.ACADEMIES.clear()
    academy.MEMBERSHIPS.clear()
    academy.GROUPS.clear()
    academy.ASSIGNMENTS.clear()


def test_full_academy_operations_cycle():
    client = TestClient(__import__("main").app)

    academy_resp = client.post(
        "/api/v1/academy/academies",
        json={"name": "KAIZO Academy", "owner_id": "coach-owner"},
    )
    assert academy_resp.status_code == 201
    a = academy_resp.json()
    assert a["coach_final_authority"] is True
    assert a["execution_authorized"] is False

    for coach_id, role in [("coach-1", "HEAD_COACH"), ("coach-2", "COACH")]:
        r = client.post(
            "/api/v1/academy/memberships",
            json={"academy_id": a["academy_id"], "coach_id": coach_id, "role": role},
        )
        assert r.status_code == 201

    group = client.post(
        "/api/v1/academy/groups",
        json={"academy_id": a["academy_id"], "name": "U15 Competition"},
    )
    assert group.status_code == 201

    assignment = client.post(
        "/api/v1/academy/assignments",
        json={
            "academy_id": a["academy_id"],
            "athlete_id": "athlete-1",
            "coach_ids": ["coach-1", "coach-2"],
        },
    )
    assert assignment.status_code == 201
    assert assignment.json()["coach_ids"] == ["coach-1", "coach-2"]

    dashboard = client.get(f"/api/v1/academy/academies/{a['academy_id']}/dashboard")
    assert dashboard.status_code == 200
    metrics = dashboard.json()["metrics"]
    assert metrics["active_coaches"] == 2
    assert metrics["active_groups"] == 1
    assert metrics["assigned_athletes"] == 1
    assert metrics["multi_coach_athletes"] == 1
    assert metrics["coach_assignment_loads"]["coach-1"] == 1
    assert metrics["coach_assignment_loads"]["coach-2"] == 1


def test_assignment_requires_active_academy_membership():
    client = TestClient(__import__("main").app)
    a = client.post(
        "/api/v1/academy/academies",
        json={"name": "Membership Gate Academy", "owner_id": "owner"},
    ).json()

    response = client.post(
        "/api/v1/academy/assignments",
        json={
            "academy_id": a["academy_id"],
            "athlete_id": "athlete-1",
            "coach_ids": ["unregistered-coach"],
        },
    )
    assert response.status_code == 409
    assert "membership required" in response.json()["detail"]


def test_coach_final_authority_gate():
    client = TestClient(__import__("main").app)
    response = client.post(
        "/api/v1/academy/academies",
        json={"name": "Blocked Academy", "owner_id": "owner", "coach_final_authority": False},
    )
    assert response.status_code == 409
    assert response.json()["detail"] == "COACH_FINAL_AUTHORITY_REQUIRED"


def test_duplicate_membership_and_group_are_blocked():
    client = TestClient(__import__("main").app)
    a = client.post(
        "/api/v1/academy/academies",
        json={"name": "Uniqueness Academy", "owner_id": "owner"},
    ).json()

    first_member = client.post(
        "/api/v1/academy/memberships",
        json={"academy_id": a["academy_id"], "coach_id": "coach-1", "role": "COACH"},
    )
    second_member = client.post(
        "/api/v1/academy/memberships",
        json={"academy_id": a["academy_id"], "coach_id": "coach-1", "role": "COACH"},
    )
    assert first_member.status_code == 201
    assert second_member.status_code == 409

    first_group = client.post(
        "/api/v1/academy/groups",
        json={"academy_id": a["academy_id"], "name": "U11"},
    )
    second_group = client.post(
        "/api/v1/academy/groups",
        json={"academy_id": a["academy_id"], "name": "u11"},
    )
    assert first_group.status_code == 201
    assert second_group.status_code == 409
