"""Explainable lexical retrieval and versioned deterministic routing, not probability."""

import json
import math
import re
from collections import Counter

from .store import audit, db, engineer_rows, now, ticket_row

POLICY = "routing-v1"
STOP = {
    "the",
    "a",
    "an",
    "is",
    "in",
    "on",
    "at",
    "to",
    "for",
    "of",
    "and",
    "or",
    "with",
    "after",
    "before",
    "from",
    "our",
    "this",
    "that",
    "has",
    "have",
    "was",
    "were",
    "started",
    "during",
    "following",
    "failure",
    "failed",
    "error",
    "issue",
    "service",
    "affected",
    "incident",
    "verified",
    "deployment",
}


def tokens(text):
    return [
        t
        for t in re.findall(r"[a-z0-9_]+", text.lower())
        if len(t) > 1 and t not in STOP
    ]


def search(c, description, limit=8):
    if not 1 <= limit <= 20:
        raise ValueError("limit must be between 1 and 20")
    query = set(tokens(description))
    rows = [
        dict(r)
        for r in c.execute(
            "SELECT i.*,e.name AS resolver_name FROM incidents i JOIN engineers e ON e.id=i.resolved_by"
        )
    ]
    docs = [
        set(
            tokens(
                r["title"]
                + " "
                + r["description"]
                + " "
                + r["component"]
                + " "
                + r["category"]
            )
        )
        for r in rows
    ]
    frequency = Counter(t for doc in docs for t in doc)
    weights = {t: math.log(1 + len(rows) / (1 + frequency[t])) for t in query}
    total = sum(weights.values()) or 1
    matches = []
    for row, doc in zip(rows, docs):
        overlap = sorted(query & doc)
        similarity = sum(weights[t] for t in overlap) / total
        if len(overlap) >= 2 and similarity >= 0.18:
            matches.append(
                {**row, "similarity": round(similarity, 4), "matched_terms": overlap}
            )
    return sorted(matches, key=lambda r: (-r["similarity"], r["id"]))[:limit]


def recommendation(c, ticket):
    matches = search(c, ticket["title"] + " " + ticket["description"], 20)
    useful = [m for m in matches if m["similarity"] >= 0.25]
    team = ticket["team"]
    if not team and useful:
        support = Counter()
        for m in useful:
            support[m["team"]] += m["similarity"]
        leaders = support.most_common()
        if len(leaders) == 1 or leaders[0][1] >= leaders[1][1] * 1.25:
            team = leaders[0][0]
    candidates, excluded = [], []
    query = set(tokens(ticket["title"] + " " + ticket["description"]))
    for engineer in engineer_rows(c):
        reasons = []
        if not engineer["available"]:
            reasons.append("Unavailable")
        if engineer["active_tickets"] >= engineer["capacity"]:
            reasons.append("At capacity")
        if not team or engineer["team"] != team:
            reasons.append(
                "Owning team not confirmed" if not team else "Different owning team"
            )
        if reasons:
            excluded.append(
                {"id": engineer["id"], "name": engineer["name"], "reasons": reasons}
            )
            continue
        history = [m for m in useful if m["resolved_by"] == engineer["id"]]
        # Best match plus bounded repeated experience; samples cannot grow the score without limit.
        historical = (
            max((m["similarity"] for m in history), default=0) * 0.7
            + min(len(history) / 5, 1) * 0.3
        )
        relevant = [skill for skill in engineer["skills"] if set(tokens(skill)) & query]
        technical = min(len(relevant) / 3, 1)
        capacity = max(0, 1 - engineer["active_tickets"] / engineer["capacity"])
        parts = {
            "Historical evidence": round(historical * 50, 1),
            "Technical overlap": round(technical * 25, 1),
            "Remaining capacity": round(capacity * 15, 1),
            "On-call coverage": 10 if engineer["on_call"] else 0,
        }
        candidates.append(
            {
                **engineer,
                "score": round(sum(parts.values()), 1),
                "breakdown": parts,
                "similar_resolved": len(history),
                "evidence_ids": [m["id"] for m in history],
                "relevant_skills": relevant,
            }
        )
    candidates.sort(key=lambda e: (-e["score"], e["active_tickets"], e["id"]))
    actionable = bool(
        useful
        and candidates
        and candidates[0]["evidence_ids"]
        and candidates[0]["score"] >= 35
    )
    reason = (
        ""
        if actionable
        else "Insufficient relevant evidence or no eligible engineer. A human must review this ticket."
    )
    result = {
        "policy_version": POLICY,
        "team": team or "Unconfirmed",
        "manual_review": not actionable,
        "reason": reason,
        "primary": candidates[0] if actionable else None,
        "backup": candidates[1] if actionable and len(candidates) > 1 else None,
        "candidates": candidates,
        "excluded": excluded,
        "incidents": matches[:5],
        "score_label": "Routing score / 100 — not a probability",
        "computed_at": now(),
    }
    return result


def rank(ticket_id):
    with db(True) as c:
        ticket = ticket_row(c, ticket_id)
        if ticket["status"] in ("assigned", "resolved", "rejected"):
            raise ValueError("This ticket is already finalized")
        result = recommendation(c, ticket)
        # Existing grant is invalid whenever ranking is recomputed.
        version = ticket["version"] + 1
        result["version"] = version
        c.execute("DELETE FROM approvals WHERE ticket_id=?", (ticket_id,))
        c.execute(
            "UPDATE tickets SET recommendation=?,version=?,updated_at=? WHERE id=?",
            (json.dumps(result), version, now(), ticket_id),
        )
        audit(
            c,
            "agent",
            "engineers.ranked",
            ticket_id,
            {
                "policy": POLICY,
                "version": version,
                "manual_review": result["manual_review"],
            },
        )
        return result
