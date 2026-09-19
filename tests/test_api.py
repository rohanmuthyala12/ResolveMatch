import json

import pytest
from fastapi.testclient import TestClient

from backend import config, routing, service, trueforge
from backend.main import app
from backend.seed import seed
from backend.store import db

HEAD = {"X-ResolveMatch": "1"}


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "api.sqlite3")
    monkeypatch.setattr(config, "PASSWORD", "")
    seed()
    # Endpoint tests isolate the database and do not start the live run monitor.
    c = TestClient(app)
    yield c
    c.close()


def create(client):
    return client.post(
        "/api/tickets",
        headers=HEAD,
        json={
            "title": "Databricks schema mismatch",
            "description": "Databricks customer ETL pipeline CUSTOMER_ID schema type mismatch",
            "team": "Data Platform",
        },
    ).json()


def pending(client):
    t = create(client)
    rec = routing.rank(t["id"])
    events = [
        {
            "type": "model.message",
            "id": "e1",
            "tool_calls": [
                {
                    "id": "call1",
                    "name": "resolvematch__assign_ticket",
                    "arguments": {
                        "ticket_id": t["id"],
                        "engineer_id": rec["primary"]["id"],
                    },
                }
            ],
        },
        {
            "type": "tool.approval_required",
            "id": "e2",
            "thread_id": "main",
            "tool_calls": [{"id": "call1", "source_event_id": "e1"}],
        },
    ]
    with db(True) as c:
        c.execute(
            "UPDATE tickets SET status='awaiting_approval',events=?,session_id='s1',turn_id='t1' WHERE id=?",
            (json.dumps(events), t["id"]),
        )
    return t, rec


def test_origin_and_header_protection(client):
    assert client.post("/api/tickets", json={}).status_code == 403
    assert (
        client.post(
            "/api/tickets", headers={**HEAD, "Origin": "https://evil.example"}, json={}
        ).status_code
        == 403
    )


def test_mcp_requires_separate_token(client):
    assert client.post("/mcp", json={}).status_code == 401


def test_missing_ticket_is_404(client):
    assert client.get("/api/tickets/missing").status_code == 404


def test_approval_duplicate_rejected(client, monkeypatch):
    t, rec = pending(client)

    async def resume(*args):
        pass

    monkeypatch.setattr(trueforge, "resume", resume)
    response = client.post(
        "/api/tickets/" + t["id"] + "/decision",
        headers=HEAD,
        json={"allow": True, "version": rec["version"]},
    )
    assert response.status_code == 200
    assert (
        client.post(
            "/api/tickets/" + t["id"] + "/decision",
            headers=HEAD,
            json={"allow": True, "version": rec["version"]},
        ).status_code
        == 409
    )
    assert service.assign(t["id"], rec["primary"]["id"])["assigned"]


def test_denial_has_no_assignment(client, monkeypatch):
    t, rec = pending(client)

    async def resume(*args):
        pass

    monkeypatch.setattr(trueforge, "resume", resume)
    assert (
        client.post(
            "/api/tickets/" + t["id"] + "/decision",
            headers=HEAD,
            json={"allow": False, "version": rec["version"]},
        ).status_code
        == 200
    )
    with pytest.raises(ValueError):
        service.assign(t["id"], rec["primary"]["id"])


def test_stale_approval_rejected(client):
    t, rec = pending(client)
    assert (
        client.post(
            "/api/tickets/" + t["id"] + "/decision",
            headers=HEAD,
            json={"allow": True, "version": rec["version"] - 1},
        ).status_code
        == 409
    )


def test_password_session(client, monkeypatch):
    monkeypatch.setattr(config, "PASSWORD", "test-password-only")
    assert client.get("/api/tickets").status_code == 401
    assert (
        client.post("/api/login", headers=HEAD, json={"password": "wrong"}).status_code
        == 401
    )
    assert (
        client.post(
            "/api/login", headers=HEAD, json={"password": "test-password-only"}
        ).status_code
        == 200
    )
    assert client.get("/api/tickets").status_code == 200
    client.post("/api/logout", headers=HEAD)
    assert client.get("/api/tickets").status_code == 401


def test_personas_offer_manager_and_every_engineer(client):
    people = client.get("/api/personas").json()
    assert people[0]["id"] == "MGR-001" and people[0]["role"] == "manager"
    engineers = client.get("/api/engineers").json()
    assert {p["id"] for p in people if p["role"] == "engineer"} == {
        e["id"] for e in engineers
    }


def test_engineer_history_returns_only_their_resolved_incidents(client):
    history = client.get("/api/engineers/ENG-001/history").json()
    assert history and all(i["resolved_by"] == "ENG-001" for i in history)
    assert client.get("/api/engineers/ENG-999/history").status_code == 404


def test_engineer_queue_lists_assigned_tickets(client, monkeypatch):
    t, rec = pending(client)

    async def resume(*args):
        pass

    monkeypatch.setattr(trueforge, "resume", resume)
    client.post(
        "/api/tickets/" + t["id"] + "/decision",
        headers=HEAD,
        json={"allow": True, "version": rec["version"]},
    )
    service.assign(t["id"], rec["primary"]["id"])
    queue = client.get("/api/engineers/" + rec["primary"]["id"] + "/queue").json()
    assert [q["id"] for q in queue] == [t["id"]]
    assert queue[0]["completed_at"] is None
    assert client.get("/api/engineers/ENG-999/queue").status_code == 404


def test_persona_header_names_the_audit_trail(client):
    client.post(
        "/api/tickets",
        headers={**HEAD, "X-RM-Actor": "MGR-001"},
        json={
            "title": "Kafka consumer lag spike",
            "description": "Consumer group lag climbing after the latest broker rollout",
        },
    )
    assert client.get("/api/audit").json()[0]["actor"] == "Dana Whitfield (Manager)"


def test_unknown_persona_falls_back_to_operator(client):
    client.post(
        "/api/tickets",
        headers={**HEAD, "X-RM-Actor": "ENG-does-not-exist"},
        json={
            "title": "Snowflake warehouse suspended",
            "description": "Reporting warehouse suspends mid-query and dashboards time out",
        },
    )
    assert client.get("/api/audit").json()[0]["actor"] == "operator"
