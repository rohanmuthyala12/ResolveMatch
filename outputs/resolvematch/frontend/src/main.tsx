import React, { useEffect, useState } from "react";
import { createRoot } from "react-dom/client";
import {
  Activity,
  ArrowRight,
  ArrowUpRight,
  Check,
  CheckCircle2,
  ChevronRight,
  CircleDot,
  Clock3,
  FileText,
  GitBranch,
  Layers3,
  Loader2,
  Plus,
  Search,
  Settings2,
  ShieldCheck,
  Users,
  X,
  Zap,
  AlertCircle,
  RotateCcw,
  LogOut,
} from "lucide-react";
import "./style.css";

type Engineer = {
  id: string;
  name: string;
  team: string;
  skills: string[];
  available: boolean;
  on_call: boolean;
  active_tickets: number;
  capacity: number;
  resolved_count: number;
  score?: number;
  breakdown?: Record<string, number>;
  similar_resolved?: number;
  evidence_ids?: string[];
};
type Incident = {
  id: string;
  title: string;
  description: string;
  team: string;
  component: string;
  severity: string;
  root_cause: string;
  resolution: string;
  resolver_name: string;
  similarity?: number;
};
type Rec = {
  primary: Engineer | null;
  backup: Engineer | null;
  manual_review: boolean;
  reason: string;
  team: string;
  incidents: Incident[];
  excluded: { id: string; name: string; reasons: string[] }[];
  policy_version: string;
  version: number;
};
type Event = {
  id: string;
  type: string;
  created_at?: string;
  tool_calls?: { id: string; name?: string; function?: { name: string } }[];
  content?: string;
  state?: { status: string; required_actions?: unknown[] };
};
type Ticket = {
  id: string;
  title: string;
  description: string;
  severity: string;
  team: string;
  status: string;
  created_at: string;
  updated_at: string;
  recommendation: Rec | null;
  agent_output: string;
  error: string | null;
  events: Event[];
  version: number;
  assignment: { name: string; engineer_id: string; assigned_at: string } | null;
};
type Status = {
  connected: boolean;
  agent_ready: boolean;
  agent_name: string;
  message: string;
  dataset: string;
  incident_count: number;
  authentication: string;
};
type Audit = {
  id: number;
  timestamp: string;
  actor: string;
  action: string;
  ticket_id: string | null;
  details: string;
};

async function api<T>(
  path: string,
  method = "GET",
  body?: unknown,
): Promise<T> {
  const res = await fetch("/api" + path, {
    method,
    headers: { "Content-Type": "application/json", "X-ResolveMatch": "1" },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  const data = await res.json();
  if (!res.ok)
    throw new Error(
      typeof data.detail === "string"
        ? data.detail
        : "Request failed. Check the entered values.",
    );
  return data;
}
const initials = (name: string) =>
  name
    .split(" ")
    .map((n) => n[0])
    .slice(0, 2)
    .join("");
const label = (s: string) => s.replaceAll("_", " ");
const date = (s: string) =>
  new Date(s).toLocaleString(undefined, {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
function Badge({ text }: { text: string }) {
  return (
    <span className={"badge " + text.toLowerCase()}>
      <span />
      {label(text)}
    </span>
  );
}

function App() {
  const [page, setPage] = useState("Overview"),
    [tickets, setTickets] = useState<Ticket[]>([]),
    [engineers, setEngineers] = useState<Engineer[]>([]),
    [status, setStatus] = useState<Status | null>(null);
  const [selected, setSelected] = useState<Ticket | null>(null),
    [modal, setModal] = useState(false),
    [busy, setBusy] = useState(false),
    [error, setError] = useState(""),
    [query, setQuery] = useState("");
  const [incidents, setIncidents] = useState<Incident[]>([]),
    [audits, setAudits] = useState<Audit[]>([]),
    [auth, setAuth] = useState<{
      required: boolean;
      authenticated: boolean;
    } | null>(null),
    [password, setPassword] = useState("");
  const [form, setForm] = useState({
    title: "",
    description: "",
    severity: "High",
    team: "",
  });
  const [notice, setNotice] = useState("");
  async function refresh() {
    const [t, e, s] = await Promise.all([
      api<Ticket[]>("/tickets"),
      api<Engineer[]>("/engineers"),
      api<Status>("/status"),
    ]);
    setTickets(t);
    setEngineers(e);
    setStatus(s);
  }
  useEffect(() => {
    api<typeof auth>("/auth")
      .then(setAuth)
      .catch((e) => setError(e.message));
  }, []);
  useEffect(() => {
    if (auth?.authenticated) refresh().catch((e) => setError(e.message));
  }, [auth?.authenticated]);
  useEffect(() => {
    if (!auth?.authenticated) return;
    const interval = setInterval(() => {
      refresh().catch(() => {});
      if (selected)
        api<Ticket>("/tickets/" + selected.id)
          .then(setSelected)
          .catch(() => {});
    }, 2500);
    return () => clearInterval(interval);
  }, [auth?.authenticated, selected?.id]);
  useEffect(() => {
    if (!auth?.authenticated) return;
    if (page === "Incident library")
      api<Incident[]>("/incidents")
        .then(setIncidents)
        .catch((e) => setError(e.message));
    if (page === "Audit trail")
      api<Audit[]>("/audit")
        .then(setAudits)
        .catch((e) => setError(e.message));
  }, [page, auth?.authenticated]);
  async function act(fn: () => Promise<void>) {
    setBusy(true);
    setError("");
    try {
      await fn();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  async function open(id: string) {
    await act(async () => {
      setSelected(await api<Ticket>("/tickets/" + id));
      setPage("Ticket detail");
    });
  }
  async function submit(e: React.FormEvent) {
    e.preventDefault();
    await act(async () => {
      const t = await api<Ticket>("/tickets", "POST", form);
      setModal(false);
      setForm({ title: "", description: "", severity: "High", team: "" });
      setSelected(t);
      setPage("Ticket detail");
      await refresh();
      try {
        setSelected(await api<Ticket>(`/tickets/${t.id}/route`, "POST"));
      } catch (err) {
        setSelected(await api<Ticket>("/tickets/" + t.id));
        throw err;
      }
    });
  }
  async function decide(allow: boolean) {
    if (!selected) return;
    await act(async () => {
      setSelected(
        await api<Ticket>(`/tickets/${selected.id}/decision`, "POST", {
          allow,
          version: selected.version,
        }),
      );
      setNotice(
        allow
          ? "Approval recorded. TrueForge is completing the assignment."
          : "Assignment rejected. No ticket was assigned.",
      );
      await refresh();
    });
  }
  const filtered = tickets.filter((t) =>
    (t.title + " " + t.id).toLowerCase().includes(query.toLowerCase()),
  );
  const active = tickets.filter(
    (t) => !["resolved", "rejected"].includes(t.status),
  ).length;
  const pending = tickets.filter(
    (t) => t.status === "awaiting_approval",
  ).length;
  const available = engineers.filter(
    (e) => e.available && e.active_tickets < e.capacity,
  ).length;
  const nav = [
    { name: "Overview", icon: Layers3 },
    { name: "Engineers", icon: Users },
    { name: "Incident library", icon: FileText },
    { name: "Audit trail", icon: ShieldCheck },
  ];
  if (!auth)
    return (
      <div className="loading">
        <Loader2 className="spin" /> Connecting to ResolveMatch…
        {error && <p>{error}</p>}
      </div>
    );
  if (!auth.authenticated)
    return (
      <div className="login">
        <form
          onSubmit={(e) => {
            e.preventDefault();
            act(async () => {
              await api("/login", "POST", { password });
              setAuth({ required: true, authenticated: true });
            });
          }}
        >
          <div className="brand-icon">
            <GitBranch />
          </div>
          <h1>Welcome to ResolveMatch</h1>
          <p>Sign in to your incident command workspace.</p>
          <label>
            Workspace password
            <input
              type="password"
              autoComplete="current-password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required
            />
          </label>
          <button className="primary" disabled={busy}>
            Sign in <ArrowRight size={16} />
          </button>
          {error && <p role="alert">{error}</p>}
        </form>
      </div>
    );
  return (
    <div className="shell">
      <aside className="sidebar">
        <a
          className="brand"
          href="#"
          onClick={(e) => {
            e.preventDefault();
            setPage("Overview");
          }}
        >
          <span className="brand-icon">
            <GitBranch size={21} />
          </span>
          ResolveMatch
        </a>
        <div className="workspace">
          <span className="workspace-avatar">R</span>
          <div>
            Engineering workspace<small>Incident operations</small>
          </div>
          <ChevronRight size={15} />
        </div>
        <div className="nav-label">WORKSPACE</div>
        <nav>
          {nav.map((n) => (
            <button
              key={n.name}
              className={
                page === n.name ||
                (page === "Ticket detail" && n.name === "Overview")
                  ? "active"
                  : ""
              }
              onClick={() => {
                setPage(n.name);
                setQuery("");
              }}
            >
              <n.icon size={18} />
              {n.name}
              {n.name === "Overview" && pending > 0 && (
                <span className="count">{pending}</span>
              )}
            </button>
          ))}
        </nav>
        <div className="sidebar-bottom">
          <div className="harness">
            <Zap size={17} />
            <div>
              Powered by TrueForge<small>Evidence. Decisions. Oversight.</small>
            </div>
          </div>
          <div className="operator">
            <span className="avatar">OP</span>
            <div>
              Workspace operator
              <small>{status?.authentication || "Local workspace"}</small>
            </div>
            {auth.required && (
              <button
                aria-label="Sign out"
                onClick={() =>
                  act(async () => {
                    await api("/logout", "POST");
                    setAuth({ required: true, authenticated: false });
                  })
                }
              >
                <LogOut size={16} />
              </button>
            )}
          </div>
        </div>
      </aside>
      <div className="main">
        <header>
          <div className="breadcrumb">
            Workspace <ChevronRight size={14} />
            <strong>
              {page === "Ticket detail" ? "Incident review" : page}
            </strong>
          </div>
          <div className="header-right">
            <span
              className={"connection " + (status?.agent_ready ? "ready" : "")}
            >
              <i />
              {status?.agent_ready ? "Agent connected" : "Setup required"}
            </span>
            <span className="avatar small">OP</span>
          </div>
        </header>
        <main>
          {error && (
            <div className="alert error" role="alert">
              <AlertCircle size={18} />
              {error}
              <button onClick={() => setError("")} aria-label="Dismiss error">
                <X size={16} />
              </button>
            </div>
          )}
          {notice && (
            <div className="alert notice" role="status">
              <CheckCircle2 size={18} />
              {notice}
              <button onClick={() => setNotice("")} aria-label="Dismiss notice">
                <X size={16} />
              </button>
            </div>
          )}
          {status && !status.agent_ready && (
            <div className="alert setup">
              <Settings2 size={18} />
              <div>
                <strong>Connect your routing agent</strong>
                <p>
                  {status.message} See the project's START_HERE.md for the setup
                  command.
                </p>
              </div>
            </div>
          )}
          {page === "Overview" && (
            <>
              <div className="page-heading">
                <div>
                  <div className="eyebrow">INCIDENT COMMAND</div>
                  <h1>The right expert. Every incident.</h1>
                  <p>
                    Route with evidence, balance your team, and stay in control.
                  </p>
                </div>
                <button className="primary" onClick={() => setModal(true)}>
                  <Plus size={17} />
                  New incident
                </button>
              </div>
              <div className="metrics">
                <Metric
                  title="Open incidents"
                  value={active}
                  sub="Across your workspace"
                  icon={<Layers3 size={19} />}
                />
                <Metric
                  title="Awaiting approval"
                  value={pending}
                  sub="Your review makes the difference"
                  icon={<ShieldCheck size={19} />}
                />
                <Metric
                  title="Engineers available"
                  value={available}
                  sub={`Of ${engineers.length} team members`}
                  icon={<Users size={19} />}
                />
                <Metric
                  title="Resolved knowledge"
                  value={status?.incident_count || 0}
                  sub="Historical incidents to learn from"
                  icon={<GitBranch size={19} />}
                />
              </div>
              <div className="overview-grid">
                <section className="panel queue">
                  <div className="panel-heading">
                    <div>
                      <h2>
                        Incident queue{" "}
                        <span className="number">{tickets.length}</span>
                      </h2>
                      <p>Every recommendation has a reason.</p>
                    </div>
                    <label className="search">
                      <Search size={16} />
                      <input
                        aria-label="Search incidents"
                        placeholder="Search incidents…"
                        value={query}
                        onChange={(e) => setQuery(e.target.value)}
                      />
                    </label>
                  </div>
                  {filtered.length ? (
                    <div className="table-wrap">
                      <table>
                        <thead>
                          <tr>
                            <th>INCIDENT</th>
                            <th>PRIORITY</th>
                            <th>STATUS</th>
                            <th />
                          </tr>
                        </thead>
                        <tbody>
                          {filtered.map((t) => (
                            <tr key={t.id} onClick={() => open(t.id)}>
                              <td>
                                <button
                                  className="row-link"
                                  onClick={(e) => {
                                    e.stopPropagation();
                                    open(t.id);
                                  }}
                                >
                                  {t.title}
                                </button>
                                <small>
                                  {t.id} · {date(t.created_at)}
                                </small>
                              </td>
                              <td>
                                <Badge text={t.severity} />
                              </td>
                              <td>
                                <Badge text={t.status} />
                              </td>
                              <td>
                                <ArrowUpRight size={17} />
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  ) : (
                    <div className="empty">
                      <div className="empty-art">
                        <GitBranch size={32} />
                      </div>
                      <h3>
                        {query
                          ? "No matching incidents"
                          : "Your next incident starts here"}
                      </h3>
                      <p>
                        Describe the problem. ResolveMatch finds the evidence
                        <br />
                        and the engineer best placed to help.
                      </p>
                      <button
                        className="secondary"
                        onClick={() => setModal(true)}
                      >
                        Create an incident <ArrowRight size={16} />
                      </button>
                    </div>
                  )}
                </section>
                <aside className="right-column">
                  <section className="principle">
                    <div className="eyebrow">
                      <ShieldCheck size={15} /> HUMAN IN THE LOOP
                    </div>
                    <h2>
                      AI recommends.
                      <br />
                      You make the call.
                    </h2>
                    <p>
                      Assignments only happen after your approval. Every
                      decision is backed by incident history and current
                      capacity.
                    </p>
                    <div className="principle-line">
                      <Check size={15} /> Explicit approval on every assignment
                    </div>
                    <div className="principle-line">
                      <Check size={15} /> Traceable evidence and routing scores
                    </div>
                  </section>
                  <section className="panel team-snapshot">
                    <div className="panel-heading">
                      <h2>Team capacity</h2>
                      <button
                        className="text-button"
                        onClick={() => setPage("Engineers")}
                      >
                        View all <ArrowUpRight size={14} />
                      </button>
                    </div>
                    {engineers.slice(0, 5).map((e) => (
                      <div className="person-row" key={e.id}>
                        <span className="avatar">{initials(e.name)}</span>
                        <div>
                          <strong>{e.name}</strong>
                          <small>{e.team}</small>
                        </div>
                        <span className="load">
                          {e.active_tickets}
                          <span>/{e.capacity}</span>
                        </span>
                        <i
                          className={
                            "availability " +
                            (e.available && e.active_tickets < e.capacity
                              ? "yes"
                              : "")
                          }
                        />
                      </div>
                    ))}
                  </section>
                </aside>
              </div>
            </>
          )}
          {page === "Ticket detail" && selected && (
            <>
              <button
                className="text-button back"
                onClick={() => setPage("Overview")}
              >
                ← Back to incident queue
              </button>
              <div className="page-heading">
                <div>
                  <div className="eyebrow">
                    {selected.id} <Badge text={selected.severity} />
                  </div>
                  <h1 className="ticket-title">{selected.title}</h1>
                  <p>
                    Created {date(selected.created_at)} ·{" "}
                    {selected.recommendation?.team ||
                      selected.team ||
                      "Team being identified"}
                  </p>
                </div>
                <Badge text={selected.status} />
              </div>
              <div className="detail-grid">
                <div className="detail-main">
                  <section className="panel description">
                    <div className="panel-heading">
                      <h2>Incident brief</h2>
                      <FileText size={17} />
                    </div>
                    <p>{selected.description}</p>
                  </section>
                  {["routing", "approving"].includes(selected.status) && (
                    <div className="running">
                      <Loader2 className="spin" />
                      <div>
                        <strong>
                          {selected.status === "approving"
                            ? "Completing your approved assignment"
                            : "Finding the right engineer"}
                        </strong>
                        <p>
                          TrueForge is running the agent. You can leave this
                          page and return.
                        </p>
                      </div>
                    </div>
                  )}
                  {selected.error && (
                    <div className="alert error">
                      <AlertCircle size={18} />
                      {selected.error}
                    </div>
                  )}
                  {["new", "error", "manual_review"].includes(
                    selected.status,
                  ) && (
                    <button
                      className="secondary"
                      disabled={busy || !status?.agent_ready}
                      onClick={() =>
                        act(async () => {
                          setSelected(
                            await api<Ticket>(
                              `/tickets/${selected.id}/route`,
                              "POST",
                            ),
                          );
                        })
                      }
                    >
                      <RotateCcw size={16} />
                      Run routing{selected.status !== "new" ? " again" : ""}
                    </button>
                  )}
                  {selected.recommendation?.manual_review && (
                    <section className="panel manual">
                      <ShieldCheck />
                      <h2>Human review needed</h2>
                      <p>{selected.recommendation.reason}</p>
                      <p>
                        No assignment will be made. Clarify the incident or add
                        relevant historical evidence before rerunning.
                      </p>
                    </section>
                  )}
                  {selected.recommendation?.primary && (
                    <>
                      <div className="section-title">
                        <h2>Recommended ownership</h2>
                        <span>
                          Deterministic ·{" "}
                          {selected.recommendation.policy_version}
                        </span>
                      </div>
                      <div className="recommendations">
                        <EngineerCard
                          engineer={selected.recommendation.primary}
                          primary
                        />
                        {selected.recommendation.backup ? (
                          <EngineerCard
                            engineer={selected.recommendation.backup}
                          />
                        ) : (
                          <div className="panel no-backup">
                            <Users />
                            <h3>No eligible backup</h3>
                            <p>
                              Only one engineer meets the current routing
                              requirements.
                            </p>
                          </div>
                        )}
                      </div>
                    </>
                  )}
                  {selected.status === "awaiting_approval" && (
                    <section className="approval">
                      <ShieldCheck size={24} />
                      <div>
                        <h3>Ready for your review</h3>
                        <p>
                          Approve assignment to{" "}
                          {selected.recommendation?.primary?.name}. Availability
                          is checked again before assignment.
                        </p>
                      </div>
                      <div className="approval-actions">
                        <button
                          className="secondary"
                          disabled={busy}
                          onClick={() => decide(false)}
                        >
                          Reject
                        </button>
                        <button
                          className="primary"
                          disabled={busy}
                          onClick={() => decide(true)}
                        >
                          {busy ? (
                            <Loader2 className="spin" size={16} />
                          ) : (
                            <Check size={16} />
                          )}
                          Approve assignment
                        </button>
                      </div>
                    </section>
                  )}
                  {selected.assignment && (
                    <section className="assigned">
                      <CheckCircle2 />
                      <div>
                        <h3>
                          {selected.status === "resolved"
                            ? "Incident resolved"
                            : `Assigned to ${selected.assignment.name}`}
                        </h3>
                        <p>
                          Assignment recorded{" "}
                          {date(selected.assignment.assigned_at)}.
                        </p>
                      </div>
                      {selected.status === "assigned" && (
                        <button
                          className="secondary"
                          disabled={busy}
                          onClick={() =>
                            act(async () => {
                              setSelected(
                                await api<Ticket>(
                                  `/tickets/${selected.id}/resolve`,
                                  "POST",
                                ),
                              );
                              await refresh();
                            })
                          }
                        >
                          Mark resolved
                        </button>
                      )}
                    </section>
                  )}
                  {!!selected.recommendation?.incidents.length && (
                    <section className="panel evidence">
                      <div className="panel-heading">
                        <div>
                          <h2>Historical evidence</h2>
                          <p>The incidents behind the recommendation.</p>
                        </div>
                        <GitBranch size={18} />
                      </div>
                      {selected.recommendation.incidents.map((i, index) => (
                        <details key={i.id} open={index === 0}>
                          <summary>
                            <span className="evidence-id">{i.id}</span>
                            <span>{i.title}</span>
                            <ChevronRight size={15} />
                          </summary>
                          <div className="evidence-body">
                            <span className="evidence-meta">
                              Resolved by {i.resolver_name} ·{" "}
                              {Math.round((i.similarity || 0) * 100)} / 100
                              lexical relevance
                            </span>
                            <h4>Root cause</h4>
                            <p>{i.root_cause}</p>
                            <h4>Resolution</h4>
                            <p>{i.resolution}</p>
                          </div>
                        </details>
                      ))}
                    </section>
                  )}
                  {selected.agent_output && (
                    <section className="panel explanation">
                      <div className="panel-heading">
                        <h2>Agent explanation</h2>
                        <Zap size={17} />
                      </div>
                      <div className="prose">{selected.agent_output}</div>
                    </section>
                  )}
                </div>
                <aside>
                  <section className="panel trace">
                    <div className="panel-heading">
                      <h2>Agent activity</h2>
                      <span className="live-dot" />
                    </div>
                    <p className="trace-caption">
                      Actual events from your TrueForge run.
                    </p>
                    <div className="timeline">
                      {selected.events
                        .filter((e) => !e.type.endsWith(".delta"))
                        .map((e, i) => (
                          <div className="timeline-event" key={e.id || i}>
                            <span className="timeline-icon">
                              {e.type === "tool.approval_required" ? (
                                <ShieldCheck size={14} />
                              ) : e.type === "tool.response" ? (
                                <Check size={14} />
                              ) : (
                                <CircleDot size={14} />
                              )}
                            </span>
                            <div>
                              <strong>{eventLabel(e)}</strong>
                              {e.tool_calls?.map((c) => (
                                <small key={c.id}>
                                  {c.name ||
                                    c.function?.name ||
                                    "Tool approval requested"}
                                </small>
                              ))}
                              {e.created_at && (
                                <time>
                                  {new Date(e.created_at).toLocaleTimeString()}
                                </time>
                              )}
                            </div>
                          </div>
                        ))}
                      {!selected.events.length && (
                        <p className="muted">
                          Events appear when the agent starts.
                        </p>
                      )}
                    </div>
                  </section>
                  {!!selected.recommendation?.excluded.length && (
                    <section className="panel excluded">
                      <h3>Eligibility checks</h3>
                      {selected.recommendation.excluded.map((e) => (
                        <div key={e.id}>
                          <strong>{e.name}</strong>
                          <small>{e.reasons.join(" · ")}</small>
                        </div>
                      ))}
                    </section>
                  )}
                </aside>
              </div>
            </>
          )}
          {page === "Engineers" && (
            <>
              <div className="page-heading">
                <div>
                  <div className="eyebrow">PEOPLE & CAPACITY</div>
                  <h1>Your team's operational picture.</h1>
                  <p>
                    Availability and live workload are checked before every
                    assignment.
                  </p>
                </div>
              </div>
              <div className="engineer-grid">
                {engineers.map((e) => (
                  <section className="panel engineer-tile" key={e.id}>
                    <div className="engineer-top">
                      <span className="avatar large">{initials(e.name)}</span>
                      <Badge text={e.available ? "Available" : "Unavailable"} />
                    </div>
                    <h2>{e.name}</h2>
                    <p>{e.team}</p>
                    <div className="skills">
                      {e.skills.map((s) => (
                        <span key={s}>{s}</span>
                      ))}
                    </div>
                    <div className="capacity-label">
                      <span>Active workload</span>
                      <strong>
                        {e.active_tickets} / {e.capacity}
                      </strong>
                    </div>
                    <div className="capacity-bar">
                      <span
                        style={{
                          width:
                            Math.min(
                              100,
                              (e.active_tickets / e.capacity) * 100,
                            ) + "%",
                        }}
                      />
                    </div>
                    <div className="engineer-controls">
                      <label>
                        <input
                          type="checkbox"
                          checked={e.available}
                          disabled={busy}
                          onChange={(event) =>
                            act(async () => {
                              await api("/engineers/" + e.id, "PATCH", {
                                available: event.target.checked,
                                on_call: e.on_call,
                                capacity: e.capacity,
                              });
                              await refresh();
                            })
                          }
                        />
                        Available
                      </label>
                      <label>
                        <input
                          type="checkbox"
                          checked={e.on_call}
                          disabled={busy}
                          onChange={(event) =>
                            act(async () => {
                              await api("/engineers/" + e.id, "PATCH", {
                                available: e.available,
                                on_call: event.target.checked,
                                capacity: e.capacity,
                              });
                              await refresh();
                            })
                          }
                        />
                        On call
                      </label>
                    </div>
                    <small>
                      {e.resolved_count} resolved incidents in the knowledge
                      base
                    </small>
                  </section>
                ))}
              </div>
            </>
          )}
          {page === "Incident library" && (
            <>
              <div className="page-heading">
                <div>
                  <div className="eyebrow">INSTITUTIONAL KNOWLEDGE</div>
                  <h1>Past resolutions. Present advantage.</h1>
                  <p>Searchable evidence for every routing decision.</p>
                </div>
                <label className="search">
                  <Search size={16} />
                  <input
                    placeholder="Search knowledge…"
                    aria-label="Search knowledge"
                    value={query}
                    onChange={(e) => setQuery(e.target.value)}
                  />
                </label>
              </div>
              <section className="panel library">
                {incidents
                  .filter((i) =>
                    (i.title + " " + i.id + " " + i.team)
                      .toLowerCase()
                      .includes(query.toLowerCase()),
                  )
                  .map((i) => (
                    <details key={i.id}>
                      <summary>
                        <span className="evidence-id">{i.id}</span>
                        <span>{i.title}</span>
                        <Badge text={i.severity} />
                        <ChevronRight size={15} />
                      </summary>
                      <div className="evidence-body">
                        <span className="evidence-meta">
                          {i.team} · {i.component} · Resolved by{" "}
                          {i.resolver_name}
                        </span>
                        <h4>Root cause</h4>
                        <p>{i.root_cause}</p>
                        <h4>Resolution</h4>
                        <p>{i.resolution}</p>
                      </div>
                    </details>
                  ))}
              </section>
            </>
          )}
          {page === "Audit trail" && (
            <>
              <div className="page-heading">
                <div>
                  <div className="eyebrow">ACCOUNTABILITY</div>
                  <h1>A record of every decision.</h1>
                  <p>
                    Persistent application audit events, ordered most recent
                    first.
                  </p>
                </div>
              </div>
              <section className="panel">
                <div className="table-wrap">
                  <table>
                    <thead>
                      <tr>
                        <th>EVENT</th>
                        <th>ACTOR</th>
                        <th>TICKET</th>
                        <th>TIME</th>
                      </tr>
                    </thead>
                    <tbody>
                      {audits.map((a) => (
                        <tr key={a.id}>
                          <td>
                            <strong>{a.action}</strong>
                            <small>{a.details !== "{}" ? a.details : ""}</small>
                          </td>
                          <td>{a.actor}</td>
                          <td>
                            {a.ticket_id ? (
                              <button
                                className="text-button"
                                onClick={() => open(a.ticket_id!)}
                              >
                                {a.ticket_id}
                              </button>
                            ) : (
                              "—"
                            )}
                          </td>
                          <td>{date(a.timestamp)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </section>
            </>
          )}
          <footer>
            <span>ResolveMatch · Human-approved incident routing</span>
            <span>
              {status?.dataset === "synthetic"
                ? "Synthetic dataset · 10 engineers / 50 incidents"
                : status?.dataset === "empty"
                  ? "No dataset loaded"
                  : "Imported dataset"}{" "}
              <span className="footer-dot">·</span> {status?.agent_name}
            </span>
          </footer>
        </main>
      </div>
      {modal && (
        <div
          className="modal-backdrop"
          onClick={() => !busy && setModal(false)}
        >
          <section
            className="modal"
            role="dialog"
            aria-modal="true"
            aria-labelledby="new-title"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="modal-heading">
              <div>
                <div className="eyebrow">NEW INCIDENT</div>
                <h2 id="new-title">Let's find the right engineer.</h2>
              </div>
              <button
                className="icon-button"
                aria-label="Close"
                onClick={() => setModal(false)}
              >
                <X />
              </button>
            </div>
            <form onSubmit={submit}>
              <label>
                Incident title
                <input
                  autoFocus
                  required
                  minLength={5}
                  maxLength={180}
                  placeholder="e.g. Customer ingestion fails after schema update"
                  value={form.title}
                  onChange={(e) => setForm({ ...form, title: e.target.value })}
                />
              </label>
              <label>
                What happened?
                <textarea
                  required
                  minLength={15}
                  maxLength={12000}
                  rows={6}
                  placeholder="Include affected systems, error messages, and recent changes. More detail helps retrieve relevant evidence."
                  value={form.description}
                  onChange={(e) =>
                    setForm({ ...form, description: e.target.value })
                  }
                />
              </label>
              <div className="form-row">
                <label>
                  Severity
                  <select
                    value={form.severity}
                    onChange={(e) =>
                      setForm({ ...form, severity: e.target.value })
                    }
                  >
                    {["Low", "Medium", "High", "Critical"].map((s) => (
                      <option key={s}>{s}</option>
                    ))}
                  </select>
                </label>
                <label>
                  Owning team
                  <select
                    value={form.team}
                    onChange={(e) => setForm({ ...form, team: e.target.value })}
                  >
                    <option value="">Identify from evidence</option>
                    {[...new Set(engineers.map((e) => e.team))].map((t) => (
                      <option key={t}>{t}</option>
                    ))}
                  </select>
                </label>
              </div>
              <div className="form-note">
                <ShieldCheck size={16} />
                Submitting starts analysis. Assignment always requires your
                approval.
              </div>
              <div className="modal-actions">
                <button
                  type="button"
                  className="secondary"
                  onClick={() => setModal(false)}
                >
                  Cancel
                </button>
                <button
                  className="primary"
                  disabled={busy || !status?.agent_ready}
                >
                  {busy ? (
                    <Loader2 className="spin" size={16} />
                  ) : (
                    <Zap size={16} />
                  )}
                  Analyze & recommend
                </button>
              </div>
            </form>
          </section>
        </div>
      )}
    </div>
  );
}
function Metric({
  title,
  value,
  sub,
  icon,
}: {
  title: string;
  value: number;
  sub: string;
  icon: React.ReactNode;
}) {
  return (
    <section className="metric">
      <div className="metric-title">
        {title}
        {icon}
      </div>
      <strong>{value.toString().padStart(2, "0")}</strong>
      <small>{sub}</small>
    </section>
  );
}
function EngineerCard({
  engineer: e,
  primary = false,
}: {
  engineer: Engineer;
  primary?: boolean;
}) {
  return (
    <section className={"engineer-card " + (primary ? "primary-card" : "")}>
      <div className="card-role">
        {primary ? (
          <>
            <Zap size={14} /> PRIMARY RECOMMENDATION
          </>
        ) : (
          <>
            <Users size={14} /> BACKUP ENGINEER
          </>
        )}
      </div>
      <div className="candidate-heading">
        <span className="avatar large">{initials(e.name)}</span>
        <div>
          <h3>{e.name}</h3>
          <p>{e.team}</p>
        </div>
        <div className="score">
          {e.score}
          <small>/ 100</small>
        </div>
      </div>
      <div className="candidate-facts">
        <span>
          <GitBranch size={14} />
          {e.similar_resolved} similar incidents
        </span>
        <span>
          <Layers3 size={14} />
          {e.active_tickets}/{e.capacity} active
        </span>
      </div>
      <div className="score-parts">
        {Object.entries(e.breakdown || {}).map(([name, value]) => (
          <div key={name}>
            <span>{name}</span>
            <strong>{value}</strong>
          </div>
        ))}
      </div>
      <small className="score-note">
        Routing score · not a confidence probability
      </small>
    </section>
  );
}
function eventLabel(e: Event) {
  if (e.type === "turn.done") {
    if (e.state?.status === "error") return "Agent run failed";
    if (e.state?.status === "cancelled") return "Agent run cancelled";
    if (e.state?.required_actions?.length) return "Waiting for human action";
  }
  const names: Record<string, string> = {
    "turn.created": "Agent run started",
    "model.message": "Model response",
    "tool.response": "Tool result received",
    "tool.approval_required": "Human approval required",
    "turn.done": "Turn completed",
    "mcp.initialize": "Tools connected",
    "user.message": "Ticket submitted",
    "user.tool_approval": "Approval decision received",
  };
  return names[e.type] || label(e.type.replaceAll(".", " "));
}

createRoot(document.getElementById("root")!).render(<App />);
