# Security and operational boundaries

## Implemented

- Localhost binding in the normal launcher; no public deployment performed.
- The manager/engineer persona switcher is a demo affordance and grants nothing: the selected persona travels in a request header, is used only as an audit label, falls back to `operator` when unrecognized, and is never a permission check. Manager-only controls are hidden in the interface, not enforced by the server.
- Separate randomly generated MCP bearer secret, persisted with mode 0600 and excluded from source control.
- OpenAI credentials stay in TrueForge. The browser receives no provider key or MCP secret.
- Optional operator password with constant-time comparison, signed eight-hour HttpOnly SameSite=Strict cookie, Secure flag when configured for HTTPS, and rate limiting on writes/login.
- Trusted-host checks; browser write requests require a custom header and approved Origin.
- Input schemas reject unknown fields; SQL uses bound parameters. React escapes text instead of injecting HTML.
- Assignment requires both TrueForge approval and a server-side grant bound to ticket, engineer, recommendation version, and expiration. The model cannot mint a grant through its exposed tools.
- Uniqueness and immediate database transactions prevent duplicate assignments and capacity races. Reads calculate active assignment load from the assignment table.
- Re-ranking invalidates existing grants. Assignment rechecks eligibility. Denial creates no assignment.
- Audit events are committed alongside mutations. They are persistent application audit records, not a tamper-proof external ledger.
- Max 12 agent iterations, three-minute run timeout, no blind mutation retries, bounded API inputs and search sizes.

## Before enterprise/public deployment

This project is **not certified production-ready**. Complete these environment-specific requirements:

1. Replace the single-operator password and the demo persona switcher with your OIDC/SSO identity, and enforce operator/admin roles server-side, with individual actor attribution, session revocation, and access reviews. Current local/password operators all share one role and can select any persona.
2. Run TrueForge in its authenticated hosted mode. Put both applications behind managed TLS and network controls; use a secret manager and rotate credentials.
3. Migrate SQLite and in-process monitoring to an appropriate shared database and durable job system for multiple workers/replicas. Add migrations, tenant isolation, measured SLOs, retry reconciliation, and tested disaster recovery.
4. Integrate the authoritative ticket and on-call systems. Define concurrency/version checks and reconciliation when external workload changes.
5. Perform dependency, penetration, threat-model, load, accessibility, and incident-response reviews. The included tests and local inspection do not replace those reviews.
6. Set retention, export, deletion, log-redaction, and model-provider data-handling policies before processing company or customer records. Apply least-privilege retrieval and exclude secrets from ticket bodies.
7. Establish routing evaluation data, escalation rules, fairness/rotation policy, severity handling, and threshold calibration with your engineering owners.

The local no-password mode assumes a trusted development machine. Never tunnel it onto the public internet. The configurable local password is a development control, not a substitute for enterprise identity or multi-tenant authorization.
