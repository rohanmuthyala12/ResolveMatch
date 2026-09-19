"""Operational metrics derived from stored agent run events and the audit trail."""

import json
from collections import Counter, defaultdict
from datetime import datetime

from . import config, trueforge
from .store import db

COUNTED = (
    "routing.started",
    "routing.retry",
    "routing.fallback",
    "routing.failed",
    "assignment.approved",
    "assignment.denied",
    "ticket.assigned",
    "ticket.reassigned",
)


def seconds(a, b):
    try:
        t = lambda s: datetime.fromisoformat(s.replace("Z", "+00:00"))
        return max((t(b) - t(a)).total_seconds(), 0)
    except (TypeError, ValueError, AttributeError):
        return None


def avg(values):
    values = [v for v in values if v is not None]
    return round(sum(values) / len(values), 2) if values else None


def run_stats(events):
    """Latency, tool calls and token usage from one run's persisted events."""
    times = {e["id"]: e.get("created_at") for e in events}
    calls, model_latency, tools, tokens = {}, [], [], Counter()
    previous = None
    for e in events:
        if e.get("type") == "model.message":
            if previous:
                model_latency.append(seconds(previous, e.get("created_at")))
            usage = e.get("usage") or {}
            tokens["input"] += usage.get("input_tokens", 0)
            tokens["output"] += usage.get("output_tokens", 0)
            tokens["cached"] += usage.get("cache_read_tokens", 0)
            for call in e.get("tool_calls") or []:
                name = (call.get("tool_info") or {}).get("name") or call.get(
                    "function", {}
                ).get("name", "unknown")
                calls[call.get("id")] = (name, e.get("created_at"))
        elif e.get("type") == "tool.response":
            name, started = calls.get(e.get("tool_call_id"), (None, None))
            if name:
                # assign_ticket pauses for a human, so its wall time is not tool latency.
                took = None if name.endswith("assign_ticket") else seconds(started, e.get("created_at"))
                tools.append((name, took))
        previous = e.get("created_at") or previous
    created = next((e["created_at"] for e in events if e.get("type") == "turn.created"), None)
    done = next((e["created_at"] for e in events if e.get("type") == "turn.done"), None)
    return {
        "duration": seconds(created, done) if created and done else None,
        "model_latency": model_latency,
        "tools": tools,
        "tokens": tokens,
        "model_calls": sum(1 for e in events if e.get("type") == "model.message"),
    }


def overview():
    with db() as c:
        audit = Counter(
            {r["action"]: r["n"] for r in c.execute("SELECT action,COUNT(*) n FROM audit GROUP BY action")}
        )
        tickets = c.execute("SELECT id,status,events,recommendation FROM tickets").fetchall()
        failures = [
            dict(r)
            for r in c.execute(
                """SELECT timestamp,action,ticket_id,details FROM audit
                   WHERE action IN ('routing.failed','routing.retry','routing.fallback')
                   ORDER BY id DESC LIMIT 15"""
            )
        ]
    durations, latencies, tokens = [], [], Counter()
    tool_time = defaultdict(list)
    runs = model_calls = 0
    guardrails = Counter()
    for t in tickets:
        events = json.loads(t["events"])
        if events:
            s = run_stats(events)
            runs += 1
            model_calls += s["model_calls"]
            durations.append(s["duration"])
            latencies += s["model_latency"]
            tokens.update(s["tokens"])
            for name, took in s["tools"]:
                tool_time[name].append(took)
        rec = json.loads(t["recommendation"]) if t["recommendation"] else None
        if rec:
            if rec.get("manual_review"):
                guardrails["Sent to manual review (weak evidence)"] += 1
            for ex in rec.get("excluded", []):
                for reason in ex["reasons"]:
                    guardrails[f"Engineer excluded: {reason}"] += 1
    guardrails["Assignments denied by a human"] = audit["assignment.denied"]
    for f in failures:
        f["details"] = json.loads(f["details"] or "{}")
    started = audit["routing.started"]
    with db() as c:
        used = trueforge.runs_this_hour(c)
    return {
        "budget": {"used": used, "limit": config.RUNS_PER_HOUR, "blocked": audit["budget.blocked"]},
        "runs": {
            "started": started,
            "with_agent_events": runs,
            "retries": audit["routing.retry"],
            "fallbacks": audit["routing.fallback"],
            "failures": audit["routing.failed"],
            "avg_run_seconds": avg(durations),
            "slowest_run_seconds": round(max((d for d in durations if d), default=0), 2) or None,
            "avg_model_call_seconds": avg(latencies),
            "model_calls": model_calls,
        },
        "tokens": dict(tokens),
        "tools": sorted(
            (
                {"name": n, "calls": len(v), "avg_seconds": avg(v)}
                for n, v in tool_time.items()
            ),
            key=lambda x: -x["calls"],
        ),
        "guardrails": [{"name": k, "count": v} for k, v in guardrails.items() if v],
        "approvals": {
            "approved": audit["assignment.approved"],
            "denied": audit["assignment.denied"],
            "assigned": audit["ticket.assigned"],
            "reassigned": audit["ticket.reassigned"],
        },
        "recent_failures": failures,
    }
