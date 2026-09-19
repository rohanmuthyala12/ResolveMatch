"""Explicit synthetic fixtures. Never silently substitutes for imported company data."""

import json

from .store import audit, db, initialize

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
