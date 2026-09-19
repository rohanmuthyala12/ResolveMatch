"""Run a real TrueForge routing request; never approves the assignment automatically."""

import json
import time

import httpx

with httpx.Client(
    base_url="http://127.0.0.1:8000", timeout=30, headers={"X-ResolveMatch": "1"}
) as c:
    response = c.post(
        "/api/tickets",
        json={
            "title": "Databricks ingestion schema mismatch",
            "description": "Customer ingestion ETL pipeline failed after a Databricks schema update. CUSTOMER_ID changed from STRING to INTEGER; downstream Delta mappings reject the type.",
            "severity": "High",
            "team": "Data Platform",
        },
    )
    response.raise_for_status()
    ticket = response.json()
    print("Ticket:", ticket["id"], flush=True)
    response = c.post("/api/tickets/" + ticket["id"] + "/route")
    response.raise_for_status()
    for _ in range(90):
        time.sleep(2)
        result = c.get("/api/tickets/" + ticket["id"]).json()
        if result["status"] not in ("routing", "approving"):
            print(
                json.dumps(
                    {
                        "id": ticket["id"],
                        "status": result["status"],
                        "error": result.get("error"),
                        "primary": (result.get("recommendation") or {}).get("primary"),
                        "pending_calls": result.get("pending_calls"),
                    },
                    indent=2,
                )
            )
            break
    else:
        raise SystemExit("Run did not finish within 180 seconds")
