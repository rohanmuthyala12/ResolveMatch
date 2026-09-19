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
