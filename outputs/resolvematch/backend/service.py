import time

from .store import audit, db, engineer_rows, now, ticket_row, uid


def create_ticket(title, description, severity="High", team="", actor="operator"):
    if (
        not 5 <= len(title.strip()) <= 180
        or not 15 <= len(description.strip()) <= 12000
    ):
        raise ValueError(
            "Use a 5–180 character title and a 15–12000 character description"
        )
    if severity not in ("Low", "Medium", "High", "Critical"):
        raise ValueError("Invalid severity")
    with db(True) as c:
        teams = {r["team"] for r in engineer_rows(c)}
        if team and team not in teams:
            raise ValueError("Unknown owning team")
        ident = uid("RM")
        c.execute(
            "INSERT INTO tickets(id,title,description,severity,team,status,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?)",
            (
                ident,
                title.strip(),
                description.strip(),
                severity,
                team,
                "new",
                now(),
                now(),
            ),
        )
        audit(c, actor, "ticket.created", ident, {"severity": severity})
        return ticket_row(c, ident)


def grant(c, ticket, engineer_id, actor):
    rec = ticket["recommendation"]
    if not rec or rec["manual_review"]:
        raise ValueError("No actionable recommendation to approve")
    eligible = {r["id"] for r in [rec["primary"], rec["backup"]] if r}
    if engineer_id not in eligible:
        raise ValueError("Engineer is not an approved recommendation candidate")
    if ticket["status"] != "awaiting_approval":
        raise ValueError("Ticket is not awaiting approval")
    c.execute(
        "INSERT OR REPLACE INTO approvals VALUES(?,?,?,?,?,0)",
        (ticket["id"], engineer_id, actor, time.time() + 600, ticket["version"]),
    )
    audit(
        c,
        actor,
        "assignment.approved",
        ticket["id"],
        {"engineer_id": engineer_id, "version": ticket["version"]},
    )


def assign(ticket_id, engineer_id):
    with db(True) as c:
        ticket = ticket_row(c, ticket_id)
        existing = ticket["assignment"]
        if existing:
            if existing["engineer_id"] != engineer_id:
                raise ValueError("Ticket already assigned to a different engineer")
            return {"assigned": True, "idempotent_replay": True, **existing}
        approval = c.execute(
            "SELECT * FROM approvals WHERE ticket_id=?", (ticket_id,)
        ).fetchone()
        if (
            not approval
            or approval["consumed"]
            or approval["expires_at"] < time.time()
            or approval["engineer_id"] != engineer_id
            or approval["recommendation_version"] != ticket["version"]
        ):
            raise ValueError(
                "An unexpired human approval from the ResolveMatch dashboard is required"
            )
        if ticket["status"] not in ("approving", "awaiting_approval"):
            raise ValueError("Ticket is not assignable in its current state")
        engineer = next((e for e in engineer_rows(c) if e["id"] == engineer_id), None)
        if (
            not engineer
            or not engineer["available"]
            or engineer["active_tickets"] >= engineer["capacity"]
        ):
            raise ValueError(
                "Engineer availability or capacity changed. Run routing again."
            )
        if engineer["team"] != ticket["recommendation"]["team"]:
            raise ValueError("Engineer no longer belongs to the recommended team")
        c.execute(
            "INSERT INTO assignments(ticket_id,engineer_id,approved_by,assigned_at) VALUES(?,?,?,?)",
            (ticket_id, engineer_id, approval["actor"], now()),
        )
        c.execute("UPDATE approvals SET consumed=1 WHERE ticket_id=?", (ticket_id,))
        c.execute(
            "UPDATE tickets SET status='assigned',updated_at=? WHERE id=?",
            (now(), ticket_id),
        )
        audit(
            c,
            approval["actor"],
            "ticket.assigned",
            ticket_id,
            {"engineer_id": engineer_id},
        )
        return {
            "assigned": True,
            "idempotent_replay": False,
            "ticket_id": ticket_id,
            "engineer_id": engineer_id,
            "name": engineer["name"],
        }


def resolve(ticket_id, actor):
    with db(True) as c:
        ticket = ticket_row(c, ticket_id)
        if ticket["status"] == "resolved":
            return ticket
        if ticket["status"] != "assigned":
            raise ValueError("Only assigned tickets can be resolved")
        c.execute(
            "UPDATE assignments SET completed_at=? WHERE ticket_id=?",
            (now(), ticket_id),
        )
        c.execute(
            "UPDATE tickets SET status='resolved',updated_at=? WHERE id=?",
            (now(), ticket_id),
        )
        audit(c, actor, "ticket.resolved", ticket_id)
        return ticket_row(c, ticket_id)
