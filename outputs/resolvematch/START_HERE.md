# ResolveMatch — start here

The complete application lives in this folder: React/TypeScript dashboard, Python API, authenticated MCP server, SQLite persistence, deterministic routing, approval enforcement, audit history, tests, and TrueForge setup.

## Current handoff

- Dashboard: **http://localhost:8000** while the backend is running.
- TrueForge: **http://localhost:8790**.
- Agent: **resolve-match**.
- Connector: **resolvematch**, with six tools attached and explicit approval on `assign_ticket`.
- OpenAI keys remain in TrueForge. ResolveMatch never needs your OpenAI key.
- The initial live test reached the MCP server but the model provider rejected the configured key with **HTTP 401 / Incorrect API key**. Replace that key in TrueForge → Settings → Models → OpenAI → Edit. Do not send the key in chat or put it in frontend code.
- The local server initially returned no saved agents, so setup created `resolve-match` with the full integration instructions. If your original agent exists under another name or in another TrueForge instance, see “Use your existing agent” below.

## Your next steps

1. Fix the OpenAI credential in TrueForge and confirm a normal chat response works there.
2. Keep TrueForge running.
3. Open **http://localhost:8000**, open the existing Databricks incident, and select **Run routing again**. Or choose **New incident** to submit a new one.
4. Watch the actual agent activity. Review the primary, backup, score breakdown, and historical evidence.
5. Select **Approve assignment** or **Reject** in ResolveMatch. Approved assignments persist and increase active workload. **Mark resolved** releases that capacity.

Use this incident for the presentation:

> Databricks customer ingestion failed after a schema update. CUSTOMER_ID changed from STRING to INTEGER and downstream Delta mappings now reject the type. The production ETL pipeline cannot process new customer records.

Set the owning team to **Data Platform**, severity **High**. The result is calculated from current data, so scores may change when workload or availability changes.

## Start again after closing the app

Open a terminal in this `resolvematch` folder. Python 3.13 and Node 24 were used for validation.

Terminal 1 — TrueForge (skip this if it is already running):

```bash
npx @truefoundry/trueforge
```

Terminal 2 — install and start ResolveMatch:

```bash
bash scripts/dev.sh
```

The script creates a project virtual environment and installs locked dependencies, builds the frontend if missing, and runs the app on port 8000. It does not overwrite or reseed an existing database.

For a fresh checkout, initialize the clearly labeled synthetic dataset once, then configure the connector and agent while the backend and TrueForge are running:

```bash
.venv/bin/python -m backend.seed
.venv/bin/python -m backend.setup_trueforge
```

The setup script creates a narrowly scoped MCP credential in `.local/mcp-token` and registers it with the local TrueForge connector. It never prints that secret. Keep `.local` and `.env` out of Git.

## Use your existing agent

Set `TRUEFORGE_AGENT_NAME` to its exact saved name in `.env` before starting the backend or running setup. The default is `resolve-match`. Copy `.env.example` to `.env` if needed.

The setup command preserves the existing agent's instructions and appends the project's integration contract. It configures this agent to use only ResolveMatch tools, disables sandbox and subagents, limits the loop to 12 iterations, and requires approval for `assign_ticket`. Use a dedicated ResolveMatch agent rather than an unrelated general-purpose agent.

## Use your real data

The application is functional; its included **10 engineers and 50 historical records are synthetic**, not a claim about your company. This label is visible in the dashboard.

Export the current dataset to see the exact import schema:

```bash
.venv/bin/python -m backend.data_cli export dataset-template.json
```

Replace the records with your authorized engineer and incident data. Preserve engineer IDs in `resolved_by`. Set `baseline_load` to active work managed outside ResolveMatch; newly approved assignments are added dynamically. Import into a fresh database so no existing tickets or audit history are destroyed:

```bash
RESOLVEMATCH_DB="$PWD/.local/company.sqlite3" .venv/bin/python -m backend.data_cli import company-data.json
```

Then set `RESOLVEMATCH_DB` to that same absolute path in `.env` and restart the server. Import validates the entire dataset before committing it. This version records assignments locally; a live Jira/ServiceNow write adapter is a separate integration that requires your destination and authorized access.

## Verify the project

```bash
.venv/bin/python -m pytest -q
.venv/bin/python -m scripts.check_mcp
cd frontend
npm ci
npm run build
```

The MCP check requires the app running. To test a real model-backed routing request without automatically approving it:

```bash
.venv/bin/python scripts/smoke.py
```

This creates a synthetic Databricks incident and uses your configured model, so normal provider usage charges apply.

## What I still need from you

**Required now:** a working provider key entered directly into TrueForge.

**Only if the hackathon requires it:** your original rules document (especially deployment/evaluation requirements), authorized company data instead of synthetic data, and the target ticket system if assignments must be written outside this app.

For a public enterprise deployment, decide the identity provider, hosting environment, role model, data retention rules, and ticket-system integration. The current app is a complete local hackathon build with tested safeguards; it has not been certified or independently audited for enterprise production. Read `SECURITY.md` for the precise deployment boundaries.
