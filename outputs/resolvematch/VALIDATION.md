# Validation record

Validated locally on macOS, Python 3.13, Node 24.

| Check | Result |
|---|---|
| Python test suite | 23 tests pass |
| Python static checks | Ruff passes |
| Frontend TypeScript check and production build | Pass |
| Frontend dependency audit at installation | Zero reported vulnerabilities |
| Live authenticated HTTP MCP connection | Pass |
| MCP tool discovery | All six expected tools discovered |
| Live MCP historical incident search | Pass |
| TrueForge connector initialization | Pass in actual model run |
| Live model-backed routing | Blocked: configured OpenAI credential returned HTTP 401 |
| Approval/resume integration contract | Pass with simulated TrueForge responses matching documented HTTP wire format |
| Browser inspection | Dashboard loads, navigation and incident error state checked |
| Docker execution | Recipe provided; not executed locally |
| CI execution | Workflow provided; checks run locally, not on GitHub |

Tests cover deterministic ranking, score explanations, unavailable/capacity/team filters, insufficient-evidence abstention, assignment without approval, expired and stale grants, idempotency, concurrent capacity races, resolution releasing workload, seed preservation, CSRF/origin checks, MCP auth rejection, 404 handling, duplicate approval, denial, password sessions, TrueForge approval/resume event handling, actionable provider errors, dataset import validation, and backup.

Two third-party deprecation warnings are emitted by Starlette's test client. They do not fail the tests. Runtime validation has not demonstrated a successful OpenAI response with the supplied credential; replace that credential and run the included smoke test before presenting the full AI workflow.
