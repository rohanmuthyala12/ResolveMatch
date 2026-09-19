# ResolveMatch

Evidence-backed engineering incident routing, orchestrated by TrueForge and approved by a human.

Start with **[START_HERE.md](START_HERE.md)**.

## Architecture

```text
React / TypeScript dashboard
    │ same-origin JSON API; polls persisted state
    ▼
FastAPI application ──────────────► TrueForge saved agent
    │                                  │
    │                                  ▼
    │                           Configured model provider
    │                                  │
    ◄──── authenticated MCP tools ──────┘
    │
    ▼
SQLite: incidents, engineers, tickets, recommendations,
        expiring approvals, unique assignments, audit events
```

The agent interprets a ticket and retrieves evidence. Python ranks eligible engineers. TrueForge pauses `assign_ticket`; the dashboard records a version-bound approval and resumes that exact call. The assignment transaction checks the approval, engineer, team, availability, and capacity again. A unique ticket key makes repeated assignment calls idempotent.

## Features

- Incident submission and persistent queue, with retry after a failed model run.
- Weighted lexical incident retrieval with real supporting record IDs.
- Deterministic score breakdown: history 50, skills 25, remaining capacity 15, on-call 10.
- Eligibility filters before ranking; explicit manual review for weak or missing evidence.
- Primary and eligible backup; no fabricated backup when only one engineer qualifies.
- TrueForge run/session persistence, actual tool events, bounded execution, provider errors.
- Human approve/reject, server-side expiring approval, revalidation and duplicate protection.
- Team availability and on-call controls, live assignment workload, incident resolution.
- Searchable incident library and persistent audit trail.
- Input validation, parameterized SQL, separate MCP authentication, same-origin write protection, optional password sessions, security headers.
- Validated dataset import/export, consistent SQLite backup, container recipe, CI workflow.

## Structure

```text
backend/
  main.py             API, auth, dashboard serving, run monitor
  tools.py            MCP tool schemas and handlers
  routing.py          Retrieval and versioned ranking policy
  service.py          Ticket and assignment transactions
  store.py            Schema and database access
  trueforge.py        Harness API adapter and approval events
  setup_trueforge.py  Connector and saved-agent configuration
  seed.py             Explicit synthetic seed data
  data_cli.py         Import, export, backup
frontend/src/         React dashboard and responsive styles
tests/                Safety, API, integration-contract, data tests
scripts/              Startup, real MCP check, model smoke test
```

## Design choices and limits

Ranking uses weighted keyword overlap so results are reproducible and inspectable. It does not perform embedding-based semantic retrieval; synonyms and novel vocabulary can lower recall. The weighting and abstention thresholds are explicit initial policy, not calibrated estimates. Validate them against your own routing outcomes before making operational claims. “Routing score” and “lexical relevance” are not probabilities.

Availability and capacity are hard requirements. Team can be supplied by the operator or inferred only when retrieved evidence has a clear leading team. An engineer without relevant resolved incidents cannot become the primary solely from a skills label. Historical expertise and skills can be correlated; weights need evaluation on real data.

The application supports one local operator, one server process, and one workspace. The audit trail records `operator`, `agent`, and `system`, not enterprise identities. Data is persisted on disk and recoverable across restarts. It is not a multi-tenant SaaS service.

There is no external Jira/ServiceNow mutation, automated remediation, vector service, or custom model training. The delivered assignment lifecycle is fully functional inside ResolveMatch's database.

## Development

Run the Python API on port 8000. For frontend hot reload use `npm run dev` from `frontend`; Vite proxies `/api` to the local API. Rebuild using `npm run build` before serving the dashboard from the API. Keep one Uvicorn worker: the monitor and run locks are single-process.

Back up using:

```bash
.venv/bin/python -m backend.data_cli backup .local/backup-2026-09-19.sqlite3
```

The backup command refuses to overwrite existing files. Stop the app before restoring by selecting a backed-up database via `RESOLVEMATCH_DB`.

The Docker recipe is supplied for portability; the validated path is native Python/Node. Its default Compose port binding is loopback-only. Docker-to-host connectivity to a localhost-only TrueForge process depends on the host platform; verify that connection before using the container option. Do not expose either default local service publicly.

## Upstream references

- [TrueForge agent configuration](https://trueforge.dev/create-agent/overview)
- [TrueForge run and approval contract](https://trueforge.dev/api/use-agent)
- [MCP Python SDK](https://github.com/modelcontextprotocol/python-sdk)

MCP is pinned to the supported 1.x API used by this implementation. Upgrade to MCP 2.x only with a deliberate migration and transport tests.
