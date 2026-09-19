"""Explicit synthetic fixtures. Never silently substitutes for imported company data."""

import json

from .store import audit, db, initialize, now, uid

PEOPLE = [
    (
        "ENG-001",
        "Kevin Shah",
        "Data Platform",
        ["databricks", "spark", "schema", "etl", "delta"],
        True,
        True,
        2,
        6,
    ),
    (
        "ENG-002",
        "Chris Lee",
        "Data Platform",
        ["databricks", "spark", "pipeline", "schema"],
        True,
        False,
        1,
        5,
    ),
    (
        "ENG-003",
        "Sarah Chen",
        "Data Platform",
        ["kafka", "streaming", "schema"],
        False,
        False,
        1,
        5,
    ),
    (
        "ENG-004",
        "Aisha Patel",
        "Infrastructure",
        ["kubernetes", "memory", "pods", "deployment", "cpu"],
        True,
        True,
        2,
        5,
    ),
    (
        "ENG-005",
        "Mateo Rivera",
        "Infrastructure",
        ["kubernetes", "network", "dns", "timeout"],
        True,
        False,
        1,
        5,
    ),
    (
        "ENG-006",
        "Priya Rao",
        "Payments",
        ["payment", "webhook", "duplicate", "idempotency"],
        True,
        True,
        1,
        5,
    ),
    (
        "ENG-007",
        "Alex Morgan",
        "Payments",
        ["payment", "refund", "timeout", "webhook"],
        True,
        False,
        3,
        5,
    ),
    (
        "ENG-008",
        "Noah Kim",
        "Identity",
        ["oauth", "token", "login", "authentication", "sso"],
        True,
        True,
        1,
        5,
    ),
    (
        "ENG-009",
        "Emma Wilson",
        "Identity",
        ["oauth", "saml", "certificate", "login"],
        True,
        False,
        1,
        5,
    ),
    (
        "ENG-010",
        "Jordan Ellis",
        "Infrastructure",
        ["database", "postgres", "connection", "pool"],
        True,
        False,
        5,
        5,
    ),
]
CASES = [
    (
        "Data Platform",
        "ETL Pipeline",
        "Schema failure",
        "Databricks ingestion CUSTOMER_ID type mismatch after schema change",
        "Upstream CUSTOMER_ID type changed from string to integer.",
        "Validate schema contracts, update downstream mappings, and replay failed batches.",
        ["ENG-001", "ENG-002"],
    ),
    (
        "Data Platform",
        "Spark Jobs",
        "Resource exhaustion",
        "Spark executor memory exhaustion during delta ETL pipeline shuffle",
        "Skewed partitions exhausted executor heap.",
        "Repartition skewed data and tune executor memory after load testing.",
        ["ENG-002", "ENG-001"],
    ),
    (
        "Data Platform",
        "Event Streaming",
        "Consumer lag",
        "Kafka streaming consumer lag following schema registry update",
        "Consumers could not deserialize the new event schema.",
        "Restore a compatible schema and replay messages from the failed offset.",
        ["ENG-003", "ENG-002"],
    ),
    (
        "Infrastructure",
        "Kubernetes",
        "Resource exhaustion",
        "Kubernetes pods OOMKilled memory limit deployment restart",
        "A deployment increased memory usage beyond the container limit.",
        "Roll back the release, profile memory, and set tested resource limits.",
        ["ENG-004", "ENG-005"],
    ),
    (
        "Infrastructure",
        "Networking",
        "DNS failure",
        "Kubernetes service DNS lookup timeout network connections",
        "CoreDNS upstream resolver saturation caused lookup timeouts.",
        "Restore resolver capacity and verify service resolution from affected pods.",
        ["ENG-005", "ENG-004"],
    ),
    (
        "Infrastructure",
        "Database",
        "Connection exhaustion",
        "Postgres database connection pool exhausted request timeout",
        "Leaked database connections exhausted the pool.",
        "Release stuck connections, patch connection lifecycle, and verify pool metrics.",
        ["ENG-010", "ENG-005"],
    ),
    (
        "Payments",
        "Webhook Processing",
        "Duplicate processing",
        "Payment webhook duplicate charge missing idempotency key",
        "Webhook retries were processed without an idempotency check.",
        "Enforce unique event keys and reconcile affected transactions.",
        ["ENG-006", "ENG-007"],
    ),
    (
        "Payments",
        "Refund API",
        "Provider timeout",
        "Payment refund gateway timeout with uncertain transaction status",
        "The provider accepted a refund but the response timed out.",
        "Query provider status before any retry and reconcile the refund ledger.",
        ["ENG-007", "ENG-006"],
    ),
    (
        "Identity",
        "OAuth",
        "Token rejection",
        "OAuth login token authentication failed after signing key rotation",
        "The verifier cached an expired signing key.",
        "Refresh the JWKS cache and verify token signature and issuer.",
        ["ENG-008", "ENG-009"],
    ),
    (
        "Identity",
        "Enterprise SSO",
        "Certificate expiry",
        "SAML SSO login certificate expired authentication failure",
        "The identity provider signing certificate expired.",
        "Coordinate certificate rollover and validate the SAML assertion.",
        ["ENG-009", "ENG-008"],
    ),
]


def seed():
    initialize()
    with db(True) as c:
        if c.execute("SELECT COUNT(*) FROM engineers").fetchone()[0]:
            return False
        for ident, name, team, skills, available, on_call, load, capacity in PEOPLE:
            c.execute(
                "INSERT INTO engineers VALUES(?,?,?,?,?,?,?,?)",
                (
                    ident,
                    name,
                    team,
                    json.dumps(skills),
                    available,
                    on_call,
                    load,
                    capacity,
                ),
            )
        for index, (
            team,
            component,
            category,
            title,
            cause,
            resolution,
            resolvers,
        ) in enumerate(CASES):
            for variant in range(5):
                c.execute(
                    "INSERT INTO incidents VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
                    (
                        f"INC-{1000 + index * 5 + variant}",
                        f"{title} · service {variant + 1}",
                        f"{title}. Affected service {variant + 1}; incident verified after deployment.",
                        team,
                        component,
                        team,
                        category,
                        "High",
                        resolvers[0 if variant < 3 else 1],
                        cause,
                        resolution,
                        30 + index * 7 + variant * 11,
                    ),
                )
        c.execute("INSERT OR REPLACE INTO metadata VALUES('dataset','synthetic')")
        audit(
            c,
            "system",
            "dataset.seeded",
            details={"engineers": 10, "incidents": 50, "synthetic": True},
        )
    return True


if __name__ == "__main__":
    print("Synthetic dataset seeded." if seed() else "Existing data preserved.")


DEMO_TICKETS = {
    "Data Platform": [
        ("Databricks nightly job failing on schema drift", "Nightly customer ingestion job fails after an upstream schema change. Delta merge rejects CUSTOMER_ID."),
        ("Spark job out of memory on daily aggregate", "Daily aggregate Spark job fails with executor out-of-memory errors since the data volume increased."),
    ],
    "Infrastructure": [
        ("Kubernetes pods crash-looping after deploy", "Pods restart repeatedly after this morning's deployment. Readiness probe fails on the API service."),
        ("Intermittent network timeouts between services", "Services in the cluster report sporadic connection timeouts to the internal gateway."),
    ],
    "Payments": [
        ("Payment API returning 502 on checkout", "Checkout requests intermittently fail with 502 from the payment gateway after the latest release."),
        ("Billing reconciliation mismatch for last night", "Nightly reconciliation shows unmatched settlements against the processor report."),
    ],
    "Identity": [
        ("SSO login failing with SAML assertion error", "Users cannot sign in through SSO. The SAML assertion signature validation fails."),
        ("Permission changes not applying after role update", "Role updates are saved but users keep their old permissions until they log out."),
    ],
}


def seed_demo_tickets():
    """Give every engineer active and resolved tickets so profiles are populated. Runs once."""
    with db(True) as c:
        if c.execute("SELECT 1 FROM metadata WHERE key='demo_tickets_v2'").fetchone():
            return False
        engineers = c.execute(
            """SELECT e.id,e.team,e.capacity,e.baseline_load +
               (SELECT COUNT(*) FROM assignments a WHERE a.engineer_id=e.id AND a.completed_at IS NULL) AS load
               FROM engineers e ORDER BY e.id"""
        ).fetchall()
        used = {}
        for e in engineers:
            pool = DEMO_TICKETS.get(e["team"]) or [
                ("Investigate failing job", "Job failing since this morning; needs investigation.")
            ]
            active = min(2, max(e["capacity"] - e["load"], 0))
            for kind in ["active"] * active + ["resolved"] * 2:
                n = used.get(e["team"], 0)
                used[e["team"]] = n + 1
                title, desc = pool[n % len(pool)]
                done = kind == "resolved"
                ident = uid("RM")
                c.execute(
                    "INSERT INTO tickets(id,title,description,severity,team,status,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?)",
                    (ident, title, desc, ("High", "Medium", "Critical")[n % 3], e["team"], "resolved" if done else "assigned", now(), now()),
                )
                c.execute(
                    "INSERT INTO assignments(ticket_id,engineer_id,approved_by,assigned_at,completed_at) VALUES(?,?,?,?,?)",
                    (ident, e["id"], "Dana Whitfield (Manager)", now(), now() if done else None),
                )
                audit(c, "system", "ticket.resolved" if done else "ticket.assigned", ident, {"engineer_id": e["id"], "demo": True})
        c.execute("INSERT INTO metadata VALUES('demo_tickets_v2','1')")
    return True
