from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations

from . import routing, service
from .store import db, engineer_rows, ticket_row

mcp = FastMCP(
    "ResolveMatch", stateless_http=True, json_response=True, streamable_http_path="/mcp"
)
READ = ToolAnnotations(
    readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False
)
WRITE = ToolAnnotations(
    readOnlyHint=False, destructiveHint=False, idempotentHint=True, openWorldHint=False
)


@mcp.tool(annotations=READ)
def get_ticket(ticket_id: str) -> dict:
    """Read authoritative ticket title, description, user severity, and owning-team hint."""
    with db() as c:
        t = ticket_row(c, ticket_id)
        return {
            k: t[k]
            for k in ("id", "title", "description", "severity", "team", "status")
        }


@mcp.tool(annotations=READ)
def search_historical_tickets(ticket_description: str, limit: int = 8) -> dict:
    """Search resolved incidents. Similarity is lexical relevance, not confidence. Cite returned IDs."""
    if len(ticket_description) > 14000:
        raise ValueError("Search text too long")
    with db() as c:
        return {
            "incidents": routing.search(c, ticket_description, limit),
            "method": "weighted keyword overlap",
        }


@mcp.tool(annotations=READ)
def get_engineer_history(engineer_id: str) -> dict:
    """Return real resolved incidents for one engineer. Never infer successful work from skills alone."""
    with db() as c:
        person = next((e for e in engineer_rows(c) if e["id"] == engineer_id), None)
        if person is None:
            raise ValueError("Unknown engineer")
        return {
            "engineer": person,
            "incidents": [
                dict(r)
                for r in c.execute(
                    "SELECT * FROM incidents WHERE resolved_by=? ORDER BY id LIMIT 100",
                    (engineer_id,),
                )
            ],
        }


@mcp.tool(annotations=READ)
def get_engineer_workload(engineer_id: str = "") -> dict:
    """Read current availability, capacity, active tickets, and on-call status; blank ID lists all."""
    with db() as c:
        rows = [
            e for e in engineer_rows(c) if not engineer_id or e["id"] == engineer_id
        ]
        if not rows:
            raise ValueError("Unknown engineer")
        return {"engineers": rows}


@mcp.tool(annotations=WRITE)
def rank_engineers(ticket_id: str) -> dict:
    """Compute and persist deterministic ranking using authoritative data. Run once before proposing assignment.
    Excludes unavailable, full, and wrong-team engineers. Returns evidence and primary/backup, or manual_review.
    Re-running invalidates prior approval. The score is not a probability.
    """
    return routing.rank(ticket_id)


@mcp.tool(annotations=WRITE)
def assign_ticket(ticket_id: str, engineer_id: str) -> dict:
    """Assign the ranked primary only after human approval in ResolveMatch dashboard.
    This tool MUST require TrueForge approval. Backend also requires a matching, unexpired human grant.
    Retries are idempotent; capacity is rechecked inside the database transaction.
    """
    return service.assign(ticket_id, engineer_id)
