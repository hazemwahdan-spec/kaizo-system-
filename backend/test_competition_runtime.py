from fastapi.testclient import TestClient
import competition_runtime as runtime


def setup_function():
    runtime.EVENTS.clear()
    runtime.READINESS.clear()
    runtime.PERFORMANCES.clear()
    runtime.DECISIONS.clear()


def test_full_competition_context_to_decision_cycle():
    client = TestClient(__import__("main").app)
    event = client.post("/api/v1/competition/events", json={
        "event_name":"Egypt Open U15","date":"2026-11-12",
        "context":{"level":"national","weight_category":"-60kg"},
        "created_by":"coach-1","evidence_refs":["event:official"]
    })
    assert event.status_code == 201
    event_id=event.json()["event_id"]

    readiness=client.post("/api/v1/competition/readiness", json={
        "athlete_id":"athlete-1","event_id":event_id,
        "indicators":{"kumi_kata":8,"nage_waza":7,"randori_transfer":6},
        "assessed_by":"coach-1","evidence_refs":["assessment:42"]
    })
    assert readiness.status_code == 201

    performance=client.post("/api/v1/competition/performance", json={
        "athlete_id":"athlete-1","event_id":event_id,
        "performance":{"score":72,"wins":3,"losses":1},
        "recorded_by":"coach-1","evidence_refs":["competition:result:1"]
    })
    assert performance.status_code == 201

    second=client.post("/api/v1/competition/events", json={
        "event_name":"National Team Trial","date":"2026-12-01",
        "context":{"level":"national","weight_category":"-60kg"},
        "created_by":"coach-1"
    }).json()["event_id"]
    client.post("/api/v1/competition/performance", json={
        "athlete_id":"athlete-1","event_id":second,
        "performance":{"score":81,"wins":4,"losses":0},
        "recorded_by":"coach-1"
    })

    trend=client.get(f"/api/v1/competition/trend/athlete-1?event_ids={event_id},{second}")
    assert trend.status_code == 200
    assert trend.json()["trend"] == "IMPROVING"
    assert trend.json()["delta"] == 9

    decision=client.post("/api/v1/competition/next-decision", json={
        "athlete_id":"athlete-1","event_id":second,
        "decision_basis":{"trend":"IMPROVING","readiness_ref":readiness.json()["readiness_id"]},
        "decision":{"focus":"pressure entry to seoi nage"},
        "decided_by":"coach-1","evidence_refs":["trend:1"]
    })
    assert decision.status_code == 201
    assert decision.json()["coach_final_authority"] is True
    assert decision.json()["execution_authorized"] is False


def test_readiness_and_performance_require_event():
    client=TestClient(__import__("main").app)
    r=client.post("/api/v1/competition/readiness",json={
        "athlete_id":"a","event_id":"missing","indicators":{"x":1},"assessed_by":"coach"
    })
    assert r.status_code==404


def test_authority_gate():
    client=TestClient(__import__("main").app)
    r=client.post("/api/v1/competition/events",json={
        "event_name":"Blocked","date":"2026-11-12","context":{"x":1},
        "created_by":"coach","coach_final_authority":False
    })
    assert r.status_code==409


def test_trend_requires_numeric_scores():
    client=TestClient(__import__("main").app)
    ids=[]
    for i in range(2):
        ids.append(client.post("/api/v1/competition/events",json={
            "event_name":f"E{i}","date":"2026-11-{12+i}","context":{"x":1},
            "created_by":"coach"
        }).json()["event_id"])
        client.post("/api/v1/competition/performance",json={
            "athlete_id":"a","event_id":ids[-1],"performance":{"score":"unknown"},"recorded_by":"coach"
        })
    r=client.get(f"/api/v1/competition/trend/a?event_ids={ids[0]},{ids[1]}")
    assert r.status_code==400
