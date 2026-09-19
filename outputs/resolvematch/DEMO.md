# ResolveMatch — hackathon demo kit

## One-liner
ResolveMatch routes an engineering incident to the individual most likely to solve it, using who actually resolved similar incidents before, then a human approves. The LLM interprets, tools retrieve, Python scores, the human approves.

## Setup (before going on stage)
1. TrueForge running (port 8790) and the agent's model key valid.
2. `bash scripts/dev.sh`, then open http://localhost:8000.
3. Do one full rehearsal run first (submit, approve, assign) so Operations has fresh numbers.
4. Keep a screen recording as a backup in case the network or provider fails.

## 3-minute script
1. **Problem (20s).** Ticket systems know which *team* owns an issue, not which *person* will fix it fastest.
2. **Submit (20s).** As Dana (Manager), New incident:
   - Title: `Databricks ingestion failing with CUSTOMER_ID type mismatch`
   - Description: `After today's Databricks schema deployment, the customer ingestion pipeline started failing with CUSTOMER_ID type mismatch.`
   - Team: Data Platform, Severity: High.
3. **Agent run (40s).** Show the Agent activity panel: `get_ticket`, `search_historical_tickets`, `rank_engineers` via MCP. Point out the score breakdown (history 50, skills 25, capacity 15, on-call 10), the evidence incident IDs and the previous fix. Say: "The model never invents the score; Python computes it."
4. **Approve (20s).** Click Approve. TrueForge pauses `assign_ticket` until the human decides. The backend re-checks availability and capacity.
5. **Engineer view (30s).** Switch to Kevin Shah in the bottom-left: the ticket is in his queue, with his resolved history. Reassign it to a same-team engineer with a reason; show that unavailable or full engineers are not offered.
6. **Guardrail beat (20s).** Mark Kevin unavailable, route a new ticket: Kevin is excluded with reason "Unavailable", Chris Lee is promoted.
7. **Production side (30s).** Open Operations: run time, tool latency, tokens, guardrails that fired, retries/fallbacks, hourly run budget. Mention the eval: `python -m scripts.eval` (10/10).

## Fallback demo (optional, strong)
Stop TrueForge, route a ticket: it retries once, then shows "Rules-only fallback" and still requires human approval. Restart TrueForge afterwards.

## Honest limits (say these before being asked)
- Data is synthetic (10 engineers, 50 incidents). The persona switcher is a demo picker, not authentication.
- Matching is weighted keyword overlap, not embeddings. Newly resolved tickets are not yet fed back into history.
- One model, no multi-provider routing. Token usage is shown; cost is not estimated.
- Jira integration is a next step, not built.

## Evidence for the submission
- `python -m pytest -q` (34 tests) and `python -m scripts.eval` (10 routing cases, 5 runs each for determinism).
- Operations page screenshot, audit trail screenshot, TrueForge run view.
