"""Demo persona identity.

This is deliberately not authentication: any viewer can act as any persona.
It exists so the dashboard and the audit trail name a real person instead of a
single anonymous operator. Real deployments bind these ids to an identity
provider; see SECURITY.md.
"""

from .store import engineer_rows

MANAGER_ID = "MGR-001"
MANAGER_NAME = "Dana Whitfield"
MANAGER_TITLE = "Engineering Manager"
FALLBACK = "operator"


def personas(c):
    """Every persona the switcher may offer: one manager plus each engineer."""
    people = [
        {
            "id": MANAGER_ID,
            "name": MANAGER_NAME,
            "role": "manager",
            "team": "Engineering",
            "title": MANAGER_TITLE,
        }
    ]
    people += [
        {
            "id": e["id"],
            "name": e["name"],
            "role": "engineer",
            "team": e["team"],
            "title": e["team"] + " engineer",
        }
        for e in engineer_rows(c)
    ]
    return people


def actor_label(c, persona_id):
    """Audit label for a persona id. Unknown ids fall back to the shared operator."""
    if persona_id == MANAGER_ID:
        return MANAGER_NAME + " (Manager)"
    row = c.execute("SELECT name FROM engineers WHERE id=?", (persona_id,)).fetchone()
    return row["name"] + " (" + persona_id + ")" if row else FALLBACK
