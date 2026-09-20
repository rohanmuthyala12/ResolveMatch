import concurrent.futures

import pytest

from backend import config, routing, service
from backend.seed import seed
from backend.store import db, engineer_rows, ticket_row


@pytest.fixture(autouse=True)
def database(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "test.sqlite3")
    seed()


def ticket():
    return service.create_ticket(
        "Databricks schema mismatch",
        "Databricks customer ETL pipeline ingestion CUSTOMER_ID type mismatch after schema change",
        "High",
        "Data Platform",
    )


def approved(t):
    rec = routing.rank(t["id"])
    with db(True) as c:
        c.execute(
            "UPDATE tickets SET status='awaiting_approval' WHERE id=?", (t["id"],)
        )
        service.grant(c, ticket_row(c, t["id"]), rec["primary"]["id"], "test-human")
    return rec["primary"]["id"]


def test_rank_is_deterministic_and_explained():
    t = ticket()
    a = routing.rank(t["id"])
    b = routing.rank(t["id"])
    assert a["primary"]["id"] == b["primary"]["id"] == "ENG-001"
    assert a["primary"]["score"] == b["primary"]["score"]
    assert a["primary"]["evidence_ids"]
    assert sum(a["primary"]["breakdown"].values()) == pytest.approx(
        a["primary"]["score"]
    )
    assert a["backup"]["id"] == "ENG-002"


def test_unavailable_best_engineer_is_excluded():
    with db(True) as c:
        c.execute("UPDATE engineers SET available=0 WHERE id='ENG-001'")
    rec = routing.rank(ticket()["id"])
    assert rec["primary"]["id"] == "ENG-002"
    assert rec["backup"] is None


def test_no_evidence_abstains():
    t = service.create_ticket(
        "Unusual quantum device issue",
        "Qubit calibration drift in a superconducting refrigerator controller",
    )
    assert routing.rank(t["id"])["manual_review"]


def test_wrong_team_never_selected():
    t = service.create_ticket(
        "Databricks schema mismatch",
        "Databricks pipeline CUSTOMER_ID schema mismatch",
        "High",
        "Payments",
    )
    assert routing.rank(t["id"])["manual_review"]


def test_assignment_without_approval_is_blocked():
    t = ticket()
    routing.rank(t["id"])
    with pytest.raises(ValueError, match="human approval"):
        service.assign(t["id"], "ENG-001")


def test_assignment_idempotent_and_capacity_released():
    t = ticket()
    eng = approved(t)
    assert service.assign(t["id"], eng)["assigned"]
    assert service.assign(t["id"], eng)["idempotent_replay"]
    with db() as c:
        assert c.execute("SELECT COUNT(*) FROM assignments").fetchone()[0] == 1
        assert (
            next(e for e in engineer_rows(c) if e["id"] == eng)["active_tickets"] == 3
        )
    service.resolve(t["id"], "test-human")
    with db() as c:
        assert (
            next(e for e in engineer_rows(c) if e["id"] == eng)["active_tickets"] == 2
        )


def test_capacity_rechecked_after_approval():
    t = ticket()
    eng = approved(t)
    with db(True) as c:
        c.execute("UPDATE engineers SET capacity=baseline_load WHERE id=?", (eng,))
    with pytest.raises(ValueError, match="capacity changed"):
        service.assign(t["id"], eng)


def test_expired_grant_blocked():
    t = ticket()
    eng = approved(t)
    with db(True) as c:
        c.execute("UPDATE approvals SET expires_at=0")
    with pytest.raises(ValueError, match="human approval"):
        service.assign(t["id"], eng)


def test_reranking_invalidates_grant():
    t = ticket()
    eng = approved(t)
    routing.rank(t["id"])
    with pytest.raises(ValueError, match="human approval"):
        service.assign(t["id"], eng)


def test_concurrent_assignments_cannot_exceed_capacity():
    first = ticket()
    second = ticket()
    a = approved(first)
    b = approved(second)
    assert a == b
    with db(True) as c:
        c.execute("UPDATE engineers SET capacity=baseline_load+1 WHERE id=?", (a,))

    def attempt(ident):
        try:
            return service.assign(ident, a)["assigned"]
        except ValueError:
            return False

    with concurrent.futures.ThreadPoolExecutor(2) as pool:
        assert sum(pool.map(attempt, [first["id"], second["id"]])) == 1


def test_malformed_ticket_rejected():
    with pytest.raises(ValueError):
        service.create_ticket("x", "short")


def test_seed_preserves_existing_data():
    t = ticket()
    assert seed() is False
    with db() as c:
        assert ticket_row(c, t["id"])["id"] == t["id"]


def test_reassign_enforces_team_availability_and_capacity():
    t = ticket()
    rec = approved(t)
    service.assign(t["id"], rec)
    with pytest.raises(ValueError, match="owning team"):
        service.reassign(t["id"], "ENG-006", "Kevin Shah (ENG-001)")
    with pytest.raises(ValueError, match="unavailable"):
        service.reassign(t["id"], "ENG-003", "Kevin Shah (ENG-001)")
    moved = service.reassign(t["id"], "ENG-002", "Kevin Shah (ENG-001)", "busy")
    assert moved["assignment"]["engineer_id"] == "ENG-002"


def resolve_documented(ticket_id, actor="Kevin Shah (ENG-001)"):
    return service.resolve(
        ticket_id,
        actor,
        "Upstream CUSTOMER_ID changed from string to integer.",
        "Updated downstream mappings and replayed the affected pipeline.",
    )


def test_documented_resolution_becomes_searchable_history():
    """The learning loop: a resolved ticket must be findable as evidence afterwards."""
    t = ticket()
    service.assign(t["id"], approved(t))
    resolve_documented(t["id"])
    with db() as c:
        learned = c.execute(
            "SELECT * FROM incidents WHERE source='learned'"
        ).fetchall()
        assert len(learned) == 1
        row = learned[0]
        assert row["resolved_by"] == "ENG-001"
        assert row["resolution_minutes"] >= 1
        # It is classified like the evidence it was matched against, not invented.
        assert row["component"] == "ETL Pipeline"
        hits = routing.search(c, t["title"] + " " + t["description"], 20)
    assert row["id"] in [h["id"] for h in hits]


def test_learned_history_raises_the_resolver_next_time():
    """Evidence gained by resolving must measurably change the next score."""
    first = ticket()
    with db() as c:
        before = routing.recommendation(c, ticket_row(c, first["id"]))
    baseline = next(e["score"] for e in before["candidates"] if e["id"] == "ENG-002")

    # ENG-002 resolves a matching incident, documented.
    t = ticket()
    with db(True) as c:
        c.execute("UPDATE engineers SET available=0 WHERE id='ENG-001'")
    service.assign(t["id"], approved(t))
    resolve_documented(t["id"], "Chris Lee (ENG-002)")
    with db(True) as c:
        c.execute("UPDATE engineers SET available=1 WHERE id='ENG-001'")

    after_ticket = ticket()
    with db() as c:
        after = routing.recommendation(c, ticket_row(c, after_ticket["id"]))
    gained = next(e for e in after["candidates"] if e["id"] == "ENG-002")
    assert gained["score"] > baseline
    assert any(i.startswith("INC-L") for i in gained["evidence_ids"])


def test_resolution_notes_are_all_or_nothing():
    t = ticket()
    service.assign(t["id"], approved(t))
    with pytest.raises(ValueError, match="both the root cause"):
        service.resolve(t["id"], "someone", "cause only", "")
    # Resolving without notes still works; it just teaches nothing.
    service.resolve(t["id"], "someone")
    with db() as c:
        assert not c.execute(
            "SELECT 1 FROM incidents WHERE source='learned'"
        ).fetchone()


VAGUE = ("Databricks Error", "Pipelines fails today all broken")
CLEAR = (
    "Databricks ingestion CUSTOMER_ID type mismatch",
    "Databricks customer ETL pipeline ingestion CUSTOMER_ID type mismatch after schema change",
)


def test_clarifying_a_manual_review_ticket_lets_routing_succeed():
    """The escalation must have a way back, or manual review is a dead end."""
    t = service.create_ticket(*VAGUE)
    assert routing.rank(t["id"])["manual_review"]
    with db() as c:
        stale_version = ticket_row(c, t["id"])["version"]
    with db(True) as c:
        c.execute("UPDATE tickets SET status='manual_review' WHERE id=?", (t["id"],))

    fixed = service.clarify(
        t["id"], *CLEAR, "High", "Data Platform", "Dana Whitfield (Manager)"
    )
    # Editing resets the ticket and voids the stale recommendation.
    assert fixed["status"] == "new"
    assert fixed["recommendation"] is None
    # Version only ever moves forward, so an approval bound to the old text
    # can never match again.
    assert fixed["version"] > stale_version

    after = routing.rank(t["id"])
    assert not after["manual_review"]
    assert after["primary"]["id"] == "ENG-001"
    with db() as c:
        actions = [
            r["action"]
            for r in c.execute("SELECT action FROM audit WHERE ticket_id=?", (t["id"],))
        ]
    assert "ticket.clarified" in actions


def test_assigned_ticket_cannot_be_edited():
    """Editing after assignment would change a ticket out from under its approval."""
    t = ticket()
    service.assign(t["id"], approved(t))
    with pytest.raises(ValueError, match="before it is assigned"):
        service.clarify(
            t["id"], *CLEAR, "Low", "Data Platform", "Dana Whitfield (Manager)"
        )
    service.resolve(t["id"], "someone")
    with pytest.raises(ValueError, match="before it is assigned"):
        service.clarify(
            t["id"], *CLEAR, "Low", "Data Platform", "Dana Whitfield (Manager)"
        )


def test_clarify_voids_a_pending_approval_and_rejects_noop_edits():
    t = ticket()
    approved(t)  # leaves an unconsumed approval and awaiting_approval status
    with db(True) as c:
        c.execute("UPDATE tickets SET status='manual_review' WHERE id=?", (t["id"],))
    service.clarify(
        t["id"], *CLEAR, "High", "Data Platform", "Dana Whitfield (Manager)"
    )
    with db() as c:
        assert not c.execute(
            "SELECT 1 FROM approvals WHERE ticket_id=?", (t["id"],)
        ).fetchone()
    with pytest.raises(ValueError, match="Change something"):
        service.clarify(
            t["id"], *CLEAR, "High", "Data Platform", "Dana Whitfield (Manager)"
        )
    with pytest.raises(ValueError, match="Unknown owning team"):
        service.clarify(
            t["id"], "A clearer title here", CLEAR[1], "High", "Nope", "Dana"
        )
