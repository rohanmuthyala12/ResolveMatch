import json

import pytest

from backend import config, routing, service, trueforge
from backend.seed import seed
from backend.store import db, ticket_row


@pytest.fixture(autouse=True)
def database(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "forge.sqlite3")
    seed()


@pytest.mark.asyncio
async def test_real_wire_format_approval_and_completed_assignment(monkeypatch):
    t = service.create_ticket(
        "Databricks schema mismatch",
        "Databricks CUSTOMER_ID schema mismatch in ETL pipeline",
        "High",
        "Data Platform",
    )

    async def initial(method, path, payload=None):
        if path == "/sessions":
            return {"data": {"id": "s1"}}
        assert payload["stream"] is False
        return {"data": {"id": "turn1"}}

    monkeypatch.setattr(trueforge, "request", initial)
    await trueforge.start(t["id"])
    rec = routing.rank(t["id"])
    events = [
        {
            "id": "e1",
            "type": "model.message",
            "content": "Evidence supports Kevin.",
            "tool_calls": [
                {
                    "id": "call1",
                    "type": "function",
                    "function": {
                        "name": "resolvematch_assign_ticket",
                        "arguments": json.dumps(
                            {"ticket_id": t["id"], "engineer_id": rec["primary"]["id"]}
                        ),
                    },
                }
            ],
        },
        {
            "id": "e2",
            "type": "tool.approval_required",
            "thread_id": "main",
            "tool_calls": [{"id": "call1", "source_event_id": "e1"}],
        },
    ]

    async def paused(method, path, payload=None):
        return (
            {"data": events}
            if "/events" in path
            else {
                "data": {
                    "state": {
                        "status": "done",
                        "output": None,
                        "required_actions": [events[-1]],
                    }
                }
            }
        )

    monkeypatch.setattr(trueforge, "request", paused)
    updated = await trueforge.sync(t["id"])
    assert updated["status"] == "awaiting_approval"
    call = trueforge.pending_calls(updated["events"])[0]
    assert call["arguments"]["engineer_id"] == "ENG-001"
    with db(True) as c:
        service.grant(c, ticket_row(c, t["id"]), "ENG-001", "human")
        c.execute("UPDATE tickets SET status='approving' WHERE id=?", (t["id"],))

    async def resume(method, path, payload=None):
        assert payload["input"][0]["approval"]["status"] == "allow"
        assert payload["input"][0]["tool_call_id"] == "call1"
        return {"data": {"id": "turn2"}}

    monkeypatch.setattr(trueforge, "request", resume)
    await trueforge.resume(t["id"], call, True)
    service.assign(t["id"], "ENG-001")

    async def done(method, path, payload=None):
        return (
            {"data": [{"id": "e3", "type": "tool.response", "content": "Assigned"}]}
            if "/events" in path
            else {
                "data": {
                    "state": {
                        "status": "done",
                        "output": {"content": "Assigned to Kevin."},
                        "required_actions": [],
                    }
                }
            }
        )

    monkeypatch.setattr(trueforge, "request", done)
    final = await trueforge.sync(t["id"])
    assert final["status"] == "assigned"
    assert final["agent_output"] == "Assigned to Kevin."
    assert final["run_started"] is None
    assert len(final["events"]) == 2
    assert trueforge.pending_calls(final["events"]) == []


@pytest.mark.asyncio
async def test_provider_401_has_actionable_error(monkeypatch):
    t = service.create_ticket(
        "Databricks schema mismatch",
        "Databricks CUSTOMER_ID schema mismatch in ETL pipeline",
    )
    with db(True) as c:
        import time

        c.execute(
            "UPDATE tickets SET status='routing',session_id='s',turn_id='t',run_started=? WHERE id=?",
            (time.time(), t["id"]),
        )

    async def failed(method, path, payload=None):
        return (
            {"data": []}
            if "/events" in path
            else {
                "data": {
                    "state": {
                        "status": "error",
                        "message": "Request failed (401): Incorrect API key",
                    }
                }
            }
        )

    monkeypatch.setattr(trueforge, "request", failed)
    result = await trueforge.sync(t["id"])
    assert "Replace it in Settings" in result["error"]
    assert result["status"] == "error"
