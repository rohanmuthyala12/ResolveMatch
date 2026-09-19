"""TrueForge HTTP adapter. Persists turn IDs so browser refreshes do not lose runs."""

import json
import time
from urllib.parse import urlencode

import httpx

from . import config
from .store import audit, db, now, ticket_row


class ForgeError(Exception):
    pass


async def request(method, path, payload=None):
    headers = (
        {"Authorization": f"Bearer {config.TRUEFORGE_TOKEN}"}
        if config.TRUEFORGE_TOKEN
        else {}
    )
    try:
        async with httpx.AsyncClient(timeout=20, headers=headers) as client:
            response = await client.request(
                method, config.TRUEFORGE_URL + "/api/v1" + path, json=payload
            )
        if response.is_error:
            raise ForgeError(
                f"TrueForge returned HTTP {response.status_code}. Check its model, agent, and connector settings."
            )
        return response.json()
    except httpx.HTTPError as exc:
        raise ForgeError(
            "Cannot reach TrueForge. Start it on port 8790 and retry."
        ) from exc


async def connection_status():
    try:
        agents = (await request("GET", "/agents")).get("data", [])
        agent = next((a for a in agents if a["name"] == config.AGENT_NAME), None)
        return {
            "connected": True,
            "agent_ready": bool(agent),
            "agent_name": config.AGENT_NAME,
            "message": "Ready to route"
            if agent
            else "Run the TrueForge setup script to attach ResolveMatch tools.",
        }
    except ForgeError as exc:
        return {
            "connected": False,
            "agent_ready": False,
            "agent_name": config.AGENT_NAME,
            "message": str(exc),
        }


async def start(ticket_id, actor="operator"):
    with db(True) as c:
        t = ticket_row(c, ticket_id)
        if t["status"] not in ("new", "error", "manual_review"):
            raise ValueError("This ticket cannot start a new run in its current state")
        c.execute(
            "UPDATE tickets SET status='routing',error=NULL,recommendation=NULL,events='[]',agent_output='',run_started=?,session_id=NULL,turn_id=NULL WHERE id=?",
            (time.time(), ticket_id),
        )
        c.execute("DELETE FROM approvals WHERE ticket_id=?", (ticket_id,))
        audit(c, actor, "routing.started", ticket_id)
    try:
        session = (
            await request("POST", "/sessions", {"agent": {"name": config.AGENT_NAME}})
        )["data"]
        with db(True) as c:
            c.execute(
                "UPDATE tickets SET session_id=? WHERE id=?", (session["id"], ticket_id)
            )
        turn = (
            await request(
                "POST",
                f"/sessions/{session['id']}/turns",
                {
                    "stream": False,
                    "input": [
                        {
                            "type": "user.message",
                            "content": f"Route ticket {ticket_id}. Read it using get_ticket, use the evidence and ranking tools, then propose the primary assign_ticket call for human approval. Never assign without approval.",
                        }
                    ],
                },
            )
        )["data"]
        with db(True) as c:
            c.execute(
                "UPDATE tickets SET turn_id=? WHERE id=?", (turn["id"], ticket_id)
            )
    except Exception as exc:
        fail(ticket_id, str(exc))
        raise


def fail(ticket_id, message):
    with db(True) as c:
        c.execute(
            "UPDATE tickets SET status='error',error=?,updated_at=?,run_started=NULL WHERE id=? AND status NOT IN ('assigned','resolved','rejected')",
            (message[:500], now(), ticket_id),
        )
        c.execute(
            "DELETE FROM approvals WHERE ticket_id=? AND consumed=0", (ticket_id,)
        )
        c.execute("UPDATE tickets SET run_started=NULL WHERE id=?", (ticket_id,))
        audit(c, "system", "routing.failed", ticket_id, {"message": message[:500]})


def pending_calls(events):
    calls = {}
    pending = []
    for event in events:
        if event.get("type") == "model.message":
            for call in event.get("tool_calls", []):
                calls[call["id"]] = call
        if event.get("type") == "tool.approval_required":
            for ref in event.get("tool_calls", []):
                call = calls.get(ref["id"], {})
                fn = call.get("function", {})
                args = call.get("arguments", fn.get("arguments", {}))
                if isinstance(args, str):
                    try:
                        args = json.loads(args)
                    except ValueError:
                        args = {}
                pending.append(
                    {
                        "id": ref["id"],
                        "thread_id": event.get("thread_id", "main"),
                        "name": call.get("name", fn.get("name", "")),
                        "arguments": args,
                    }
                )
    return pending


async def sync(ticket_id):
    with db() as c:
        t = ticket_row(c, ticket_id)
    if t["run_started"] is None:
        return t
    if time.time() - (t["run_started"] or time.time()) > 180:
        try:
            await request("POST", f"/sessions/{t['session_id']}/cancel", {})
        except ForgeError:
            pass
        fail(
            ticket_id,
            "Routing exceeded the three-minute time limit. Inspect TrueForge and retry.",
        )
        with db() as c:
            return ticket_row(c, ticket_id)
    if not t["turn_id"]:
        return t
    turn = (await request("GET", f"/sessions/{t['session_id']}/turns/{t['turn_id']}"))[
        "data"
    ]
    current_events = []
    page_token = None
    for _ in range(20):
        params = {"limit": 100}
        if page_token:
            params["page_token"] = page_token
        result = await request(
            "GET",
            f"/sessions/{t['session_id']}/turns/{t['turn_id']}/events?"
            + urlencode(params),
        )
        current_events.extend(
            item.get("event", item) for item in result.get("data", [])
        )
        page_token = result.get("pagination", {}).get("next_page_token")
        if not page_token:
            break
    else:
        raise ForgeError("Agent emitted too many events. Inspect the TrueForge run.")
    merged = {e["id"]: e for e in t["events"]}
    merged.update({e["id"]: e for e in current_events})
    events = list(merged.values())
    state = turn["state"]
    output = (state.get("output") or {}).get("content", "") or ""
    if not output:
        output = "\n\n".join(
            e.get("content", "")
            for e in events
            if e.get("type") == "model.message" and isinstance(e.get("content"), str)
        )
    with db(True) as c:
        current = ticket_row(c, ticket_id)
        status = current["status"]
        error = None
        if status not in ("assigned", "resolved", "rejected"):
            if state["status"] in ("error", "cancelled"):
                status = "error"
                error = "TrueForge run failed or was cancelled. Inspect its session for details."
                message = str(state.get("message", ""))
                if "401" in message or "Incorrect API key" in message:
                    error = "OpenAI rejected the API key configured in TrueForge. Replace it in Settings → Models → OpenAI → Edit, then run routing again."
                elif "429" in message:
                    error = "The model provider reported a quota or rate limit. Check provider billing and limits, then retry."
            elif state["status"] == "done":
                if pending_calls(current_events):
                    status = "awaiting_approval"
                elif (
                    current["recommendation"]
                    and current["recommendation"]["manual_review"]
                ):
                    status = "manual_review"
                else:
                    status = "error"
                    error = "Agent ended without an assignment approval request. Check its instructions and tool configuration."
        c.execute(
            "UPDATE tickets SET events=?,agent_output=?,status=?,error=?,updated_at=?,run_started=? WHERE id=?",
            (
                json.dumps(events),
                output,
                status,
                error,
                now(),
                t["run_started"] if state["status"] == "running" else None,
                ticket_id,
            ),
        )
        return ticket_row(c, ticket_id)


async def resume(ticket_id, call, allow):
    with db() as c:
        t = ticket_row(c, ticket_id)
    try:
        turn = (
            await request(
                "POST",
                f"/sessions/{t['session_id']}/turns",
                {
                    "stream": False,
                    "input": [
                        {
                            "type": "user.tool_approval",
                            "thread_id": call["thread_id"],
                            "tool_call_id": call["id"],
                            "approval": {"status": "allow" if allow else "deny"},
                        }
                    ],
                },
            )
        )["data"]
        with db(True) as c:
            # Preserve the routing trace, removing only the fulfilled approval request.
            retained = [
                e for e in t["events"] if e.get("type") != "tool.approval_required"
            ]
            c.execute(
                "UPDATE tickets SET turn_id=?,run_started=?,updated_at=?,events=? WHERE id=?",
                (turn["id"], time.time(), now(), json.dumps(retained), ticket_id),
            )
    except Exception:
        fail(
            ticket_id,
            "Approval delivery was interrupted. Check the recorded assignment before retrying.",
        )
        raise
