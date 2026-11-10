import clsx from "clsx";
import {
  Radar,
  Activity, BadgeCheck, Ban, CheckCircle2, CircleSlash, ClipboardCheck, Clock, FileSignature, History, KeyRound, Loader2, LogOut,
  Pause, Play, RefreshCw, Scale, ShieldAlert, ShieldCheck, UserCheck, UserCog, XCircle, type LucideIcon,
} from "lucide-react";
import { useCallback, useEffect, useState, type ReactNode } from "react";
import { BehaviourWatch } from "@/components/BehaviourWatch";
import { Badge, Card, CardHeader, EmptyState, Notice, PageHeader, SyntheticBadge } from "@/components/ui";
import { invalidate, useApi } from "@/hooks/useApi";
import { ApiError, apiPost, hasOfficerToken, officerRequest, setOfficerToken } from "@/lib/api";
import { humanize, type Tone } from "@/lib/format";
import type { AuditEvent, SystemCapabilities, WorkflowRun } from "@/types/api";

// --- types (mirror backend officer API) -------------------------------------------------
type Officer = { officer_id: string; name: string; title: string; entity: string; role: string; permissions: string[];
                 all_entities: boolean; session_expires_at: string };
type ResponseRecord = { at: string; action: string; reason: string; target: string | null; applied: boolean; detail: string };
type Incident = { incident_id: string; rule_id: string; title: string; severity: string; classification: string; status: string;
                  agent_id: string | null; case_id: string | null; mandate_id: string | null; first_seen: string; last_seen: string;
                  occurrences: number; summary: string; interpretation: string; responses: ResponseRecord[];
                  notes: { at: string; officer: string; status: string; note: string }[] };
type Approval = { approval_id: string; status: string; created_at: string; expires_at: string; case_id: string | null; agent_id: string;
                  tool_name: string; mandate_id: string; reason: string; incident_id: string | null; decided_by: string | null;
                  reauthorization_codes: string[]; execution_status: string | null };
type GraphNode = { id: string; kind: string; label: string; sublabel: string; status: string; data: Record<string, any> }; // eslint-disable-line @typescript-eslint/no-explicit-any
type Investigation = {
  incident: Incident; evidence: AuditEvent[]; violated_rules: string[];
  case?: { case_id: string; state: string; citizen_ref: string; paused_from: string | null; task_assignments: Record<string, string>;
           service_owner: string; recovery_status: string; authority_revoked: boolean };
  citizen_request?: { citizen_ref: string; citizen_name: string | null; service: string; purpose: string; request_id: string; opened_at: string };
  completed_actions?: { at: string; actor: string; kind: string; detail: string }[];
  incomplete_requirements?: string[];
  authority_graph?: { nodes: GraphNode[] };
  approvals?: Approval[];
  reassignable_tasks?: Record<string, string[]>;
};
type Overview = {
  incidents: { total: number; by_status: Record<string, number>; by_severity: Record<string, number> };
  approvals_pending: number; suspended_mandates: number; revoked_mandates: number;
  cases: { total: number; by_state: Record<string, number>; under_review: number; recovered: number; authority_revoked: number };
  decisions: { allowed: number; denied: number; escalated: number }; audit_chain_valid: boolean; detection: string;
};
type CaseRow = { case_id: string; citizen_ref: string; state: string; incident_policy: string; authority_model: string;
                 recovery_status: string; authority_revoked: boolean; task_assignments: Record<string, string>;
                 completed_prerequisites: string[]; active_incident: string | null };

const SEV_TONE: Record<string, Tone> = { low: "neutral", medium: "warn", high: "deny", critical: "deny" };
const time = (iso: string) => new Date(iso).toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit", second: "2-digit" });

/** The five operational states the console shows, each derived from backend state. */
function caseStatus(c: CaseRow): { label: "AUTHORIZED" | "DENIED" | "UNDER REVIEW" | "SUSPENDED" | "RECOVERED" | "COMPLETED"; tone: Tone } {
  if (c.authority_revoked) return { label: "SUSPENDED", tone: "deny" };
  if (c.state === "PAUSED_FOR_REVIEW") return { label: "UNDER REVIEW", tone: "warn" };
  if (c.state === "FAILED") return { label: "DENIED", tone: "deny" };
  if (c.recovery_status === "recovered") return { label: "RECOVERED", tone: "trust" };
  if (c.state === "COMPLETED") return { label: "COMPLETED", tone: "trust" };
  return { label: "AUTHORIZED", tone: "trust" };
}
function nodeStatus(s: string): { label: string; tone: Tone } {
  if (s === "active" || s === "verified") return { label: "AUTHORIZED", tone: "trust" };
  if (s === "suspended") return { label: "SUSPENDED", tone: "warn" };
  if (s === "revoked" || s === "invalid" || s === "denied") return { label: s === "denied" ? "DENIED" : s.toUpperCase(), tone: "deny" };
  return { label: s.toUpperCase(), tone: "neutral" };
}

function Btn({ onClick, children, tone = "neutral", disabled, icon: Icon }: { onClick: () => void; children: ReactNode; tone?: Tone; disabled?: boolean; icon?: LucideIcon }) {
  return (
    <button onClick={onClick} disabled={disabled} className={clsx(
      "inline-flex items-center gap-1.5 rounded-lg border px-2.5 py-1.5 text-[12.5px] transition-colors disabled:cursor-not-allowed disabled:opacity-40",
      tone === "trust" && "border-trust/40 text-trust hover:bg-trust-soft", tone === "warn" && "border-warn/40 text-warn hover:bg-warn-soft",
      tone === "deny" && "border-deny/40 text-deny hover:bg-deny-soft", tone === "neutral" && "border-line text-fg-muted hover:bg-ink-750 hover:text-fg",
      tone === "plan" && "border-plan/40 text-plan hover:bg-plan-soft")}>
      {Icon && <Icon className="size-3.5" aria-hidden />} {children}
    </button>
  );
}

// --- sign-in ------------------------------------------------------------------------------------
function SignIn({ onSignedIn }: { onSignedIn: (o: Officer) => void }) {
  const [officerId, setOfficerId] = useState("OFF-0101");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const r = await officerRequest<{ token: string; officer: Officer }>("/api/officer/session", "POST", { officer_id: officerId, password });
      setOfficerToken(r.token);
      setPassword("");
      onSignedIn(r.officer);
    } catch (err) {
      setError(err instanceof ApiError ? `${err.code}: ${err.message}` : (err as Error).message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <Card className="mx-auto max-w-lg">
      <CardHeader icon={KeyRound} title="Officer sign-in" subtitle="Authenticated by the WAKALA backend; roles enforced server-side" />
      <form onSubmit={submit} className="space-y-4 p-5">
        <label className="block text-[12.5px] text-fg-muted">Officer ID
          <input value={officerId} onChange={(e) => setOfficerId(e.target.value.toUpperCase())} autoComplete="username"
            className="mt-1 block w-full rounded-lg border border-line bg-ink-900 px-3 py-2 font-mono text-[13px] text-fg focus:border-trust" />
        </label>
        <label className="block text-[12.5px] text-fg-muted">Password
          <input type="password" value={password} onChange={(e) => setPassword(e.target.value)} autoComplete="current-password"
            className="mt-1 block w-full rounded-lg border border-line bg-ink-900 px-3 py-2 font-mono text-[13px] text-fg focus:border-trust" />
        </label>
        {error && <p className="rounded-lg border border-deny/30 bg-deny-soft px-3 py-2 text-[12.5px] text-deny">{error}</p>}
        <button disabled={busy || !password} className="inline-flex w-full items-center justify-center gap-2 rounded-lg border border-trust/50 bg-trust-soft px-3 py-2 text-[13.5px] font-medium text-trust disabled:opacity-50">
          {busy ? <Loader2 className="size-4 animate-spin" aria-hidden /> : <UserCheck className="size-4" aria-hidden />} Sign in
        </button>
        <p className="text-[12px] leading-relaxed text-fg-subtle">
          Development-only passwords are never stored in clear or shipped to the browser. Issue one (shown once) with{" "}
          <span className="font-mono">.venv\Scripts\python -m app.devtools.cli officers set-password OFF-0101</span> in <span className="font-mono">backend/</span>.
          Roles: OFF-0101 / OFF-0202 case officers, OFF-0900 security supervisor, OFF-0950 read-only auditor.
        </p>
      </form>
    </Card>
  );
}

// --- overview -------------------------------------------------------------------------------------------
function Tile({ label, value, note, tone }: { label: string; value: ReactNode; note: string; tone?: Tone }) {
  return (
    <div className="card p-4">
      <p className="text-[12.5px] text-fg-muted">{label}</p>
      <p className={clsx("mt-2 text-[28px] font-semibold leading-none tabular-nums", tone === "deny" ? "text-deny" : tone === "warn" ? "text-warn" : tone === "trust" ? "text-trust" : "text-fg")}>{value}</p>
      <p className="mt-2 text-[11.5px] text-fg-subtle">{note}</p>
    </div>
  );
}

function OverviewPanel({ ov, cases }: { ov: Overview | null; cases: CaseRow[] }) {
  if (!ov) return null;
  return (
    <div className="space-y-6">
      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-6">
        <Tile label="Open incidents" value={(ov.incidents.by_status.open ?? 0) + (ov.incidents.by_status.under_review ?? 0)}
              note={`${ov.incidents.total} total · ${ov.incidents.by_severity.high ?? 0} high · ${ov.incidents.by_severity.critical ?? 0} critical`}
              tone={(ov.incidents.by_status.open ?? 0) ? "deny" : undefined} />
        <Tile label="Approvals pending" value={ov.approvals_pending} note="held; nothing executed" tone={ov.approvals_pending ? "warn" : undefined} />
        <Tile label="Suspended mandates" value={ov.suspended_mandates} note={`${ov.revoked_mandates} revoked`} tone={ov.suspended_mandates ? "warn" : undefined} />
        <Tile label="Cases under review" value={ov.cases.under_review} note={`${ov.cases.total} cases · ${ov.cases.recovered} recovered`} />
        <Tile label="Gateway decisions" value={ov.decisions.allowed + ov.decisions.denied + ov.decisions.escalated}
              note={`${ov.decisions.allowed} allowed · ${ov.decisions.denied} denied · ${ov.decisions.escalated} held`} />
        <Tile label="Audit chain" value={ov.audit_chain_valid ? "Intact" : "Broken"} note="hash chain verified now" tone={ov.audit_chain_valid ? "trust" : "deny"} />
      </div>
      <Card>
        <CardHeader icon={Activity} title="Government service continuity" subtitle="Every case, with its operational status derived from backend state" />
        {cases.length === 0 ? <p className="px-5 py-4 text-[13px] text-fg-subtle">No cases yet.</p> : (
          <div className="overflow-x-auto">
            <table className="w-full min-w-[760px] text-left text-[12.5px]">
              <thead><tr className="border-b border-line text-[11px] uppercase tracking-wider text-fg-subtle">
                {["Status", "Case", "Citizen", "State", "Prerequisites", "Policy", "Assignments", "Incident"].map((h) => <th key={h} className="px-4 py-2.5 font-medium">{h}</th>)}
              </tr></thead>
              <tbody>{cases.map((c) => {
                const st = caseStatus(c);
                return (
                  <tr key={c.case_id} className="border-b border-line/60">
                    <td className="px-4 py-2"><Badge tone={st.tone} dot>{st.label}</Badge></td>
                    <td className="px-4 py-2 font-mono">{c.case_id}</td>
                    <td className="px-4 py-2 font-mono">{c.citizen_ref}</td>
                    <td className="px-4 py-2 font-mono text-[11.5px] text-fg-muted">{c.state}</td>
                    <td className="px-4 py-2 text-fg-muted">{c.completed_prerequisites.length}/3</td>
                    <td className="px-4 py-2 font-mono text-[11.5px] text-fg-subtle">{c.incident_policy}</td>
                    <td className="px-4 py-2 font-mono text-[11px] text-fg-subtle">{Object.entries(c.task_assignments).map(([t, a]) => `${t}→${a}`).join(" ") || "default"}</td>
                    <td className="px-4 py-2 font-mono text-[11px] text-deny">{c.active_incident ?? ""}</td>
                  </tr>
                );
              })}</tbody>
            </table>
          </div>
        )}
      </Card>
    </div>
  );
}

// --- investigation -----------------------------------------------------------------------------------------
function InvestigationPanel({ id, officer, onChanged }: { id: string; officer: Officer; onChanged: () => void }) {
  const [inv, setInv] = useState<Investigation | null>(null);
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null);
  const [busy, setBusy] = useState(false);
  const can = (perm: string) => officer.permissions.includes(perm);
  const load = useCallback(async () => setInv(await officerRequest<Investigation>(`/api/officer/incidents/${id}`)), [id]);
  useEffect(() => {
    load().catch((e) => setMsg({ ok: false, text: (e as Error).message }));
    const id = setInterval(() => { load().catch(() => undefined); }, 4000);
    return () => clearInterval(id);
  }, [load]);

  async function act(label: string, path: string, body: unknown) {
    setBusy(true);
    setMsg(null);
    try {
      await officerRequest(path, "POST", body);
      setMsg({ ok: true, text: `${label}: done (audited as ${officer.officer_id}).` });
      await load();
      onChanged();
    } catch (e) {
      setMsg({ ok: false, text: e instanceof ApiError ? `${label} refused: ${e.code}` : (e as Error).message });
    } finally {
      setBusy(false);
    }
  }
  if (!inv) return <p className="p-5 text-[13px] text-fg-subtle">Loading investigation…</p>;
  const i = inv.incident;
  const mandates = (inv.authority_graph?.nodes ?? []).filter((n) => n.kind === "mandate" || n.kind === "child_mandate");
  const tasks = inv.reassignable_tasks ?? {};
  return (
    <div className="space-y-5 p-5">
      <div className="flex flex-wrap items-center gap-2">
        <Badge tone={SEV_TONE[i.severity] ?? "neutral"} dot>{i.severity.toUpperCase()}</Badge>
        <Badge tone="neutral">{i.status.replace("_", " ")}</Badge>
        <span className="font-mono text-[12px] text-fg-subtle">{i.rule_id} · {i.classification.replace(/_/g, " ")}</span>
      </div>
      <div>
        <p className="text-[15px] font-semibold text-fg">{i.title}</p>
        <p className="mt-1 text-[13px] text-fg-muted">{i.summary} · agent <span className="font-mono">{i.agent_id}</span> · {i.occurrences} occurrence(s)</p>
        <p className="mt-2 rounded-lg border border-line bg-ink-900/60 px-3 py-2 text-[12.5px] text-fg-muted">{i.interpretation}</p>
      </div>

      {inv.citizen_request && (
        <div className="grid gap-4 lg:grid-cols-3">
          <div className="rounded-xl border border-line bg-ink-800/60 p-4">
            <p className="eyebrow mb-2">Original citizen request</p>
            <p className="text-[13px] text-fg">{inv.citizen_request.citizen_name} <span className="font-mono text-fg-subtle">{inv.citizen_request.citizen_ref}</span></p>
            <p className="mt-1 text-[12.5px] text-fg-muted">{inv.citizen_request.purpose}</p>
            <p className="mt-1 font-mono text-[11px] text-fg-subtle">{inv.citizen_request.request_id} · case {inv.case?.case_id} · {inv.case?.state}</p>
          </div>
          <div className="rounded-xl border border-line bg-ink-800/60 p-4">
            <p className="eyebrow mb-2">Completed actions</p>
            <ul className="space-y-1">{(inv.completed_actions ?? []).map((a, k) => (
              <li key={k} className="flex gap-2 text-[12px]"><CheckCircle2 className="mt-0.5 size-3.5 shrink-0 text-trust" aria-hidden /><span className="text-fg-muted">{a.detail}</span></li>
            ))}</ul>
          </div>
          <div className="rounded-xl border border-line bg-ink-800/60 p-4">
            <p className="eyebrow mb-2">Incomplete requirements</p>
            <ul className="space-y-1">{(inv.incomplete_requirements ?? []).map((r) => (
              <li key={r} className="flex gap-2 text-[12px]"><CircleSlash className="mt-0.5 size-3.5 shrink-0 text-warn" aria-hidden /><span className="text-fg-muted">{humanize(r)}</span></li>
            ))}{inv.incomplete_requirements?.length === 0 && <li className="text-[12px] text-trust">All satisfied</li>}</ul>
          </div>
        </div>
      )}

      <div className="grid gap-4 xl:grid-cols-2">
        <div>
          <p className="eyebrow mb-2">Violated rule — gateway evidence</p>
          <p className="mb-2 font-mono text-[11.5px] text-deny">{inv.violated_rules.join(" · ")}</p>
          <ul className="space-y-1.5">{inv.evidence.map((e) => (
            <li key={e.event_id} className="rounded-md border border-line bg-ink-900/60 px-2.5 py-1.5 font-mono text-[11px]">
              {(e as any).plain_english && <span className="mb-1 block font-sans text-[12.5px] text-fg">{(e as any).plain_english}</span>}
              <span className={e.decision === "denied" ? "text-deny" : "text-fg-subtle"}>#{e.sequence} {e.decision}</span> <span className="text-fg">{e.action}</span>
              <span className="block text-fg-subtle">{e.actor} · target {String(e.evidence_metadata.target_resource ?? "—")} · {e.related_mandate} · {time(e.timestamp)}</span>
            </li>
          ))}</ul>
        </div>
        <div>
          <p className="eyebrow mb-2">Delegated authority chain (verified now)</p>
          <ul className="space-y-1.5">{mandates.map((n) => {
            const st = nodeStatus(n.status);
            const m = n.data.mandate as { mandate_id: string; agent_id: string; parent_mandate_id: string | null; delegated_task: string | null } | undefined;
            return (
              <li key={n.id} className="flex flex-wrap items-center gap-2 rounded-md border border-line bg-ink-900/60 px-2.5 py-2">
                <Badge tone={st.tone}>{st.label}</Badge>
                <span className="font-mono text-[11.5px] text-fg">{n.label}</span>
                <span className="text-[11.5px] text-fg-subtle">{n.sublabel}{m?.delegated_task ? ` · ${m.delegated_task}` : ""}{m?.parent_mandate_id ? ` · parent ${m.parent_mandate_id}` : " · root"}</span>
                <span className="ml-auto flex gap-1.5">
                  {can("mandates.suspend") && n.status !== "suspended" && n.status !== "revoked" && (
                    <Btn tone="warn" icon={Pause} disabled={busy} onClick={() => act("Suspend", `/api/officer/mandates/${n.label}/suspend`, { reason: "officer suspension during review", incident_id: i.incident_id })}>Suspend</Btn>)}
                  {can("mandates.reinstate") && n.status === "suspended" && (
                    <Btn tone="trust" icon={Play} disabled={busy} onClick={() => act("Reinstate", `/api/officer/mandates/${n.label}/reinstate`, { reason: "cleared by officer" })}>Reinstate</Btn>)}
                  {can("mandates.revoke") && n.status !== "revoked" && (
                    <Btn tone="deny" icon={Ban} disabled={busy} onClick={() => act("Revoke", `/api/officer/mandates/${n.label}/revoke`, { reason: "revoked by security supervisor" })}>Revoke</Btn>)}
                </span>
              </li>
            );
          })}</ul>
        </div>
      </div>

      <div>
        <p className="eyebrow mb-2">Graduated response applied</p>
        <ul className="grid gap-1.5 md:grid-cols-2">{i.responses.map((r, k) => (
          <li key={k} className={clsx("rounded-md border px-2.5 py-1.5 text-[11.5px]", r.applied ? "border-line bg-ink-900/60" : "border-dashed border-line-strong")}>
            <span className={clsx("font-mono", r.applied ? "text-fg" : "text-fg-subtle")}>{r.action}</span>
            <span className="ml-1 font-mono text-fg-subtle">{r.reason}</span>
            <span className="block text-fg-muted">{r.detail}</span>
          </li>
        ))}</ul>
      </div>

      <div className="rounded-xl border border-trust/25 bg-ink-800/60 p-4">
        <p className="eyebrow mb-3">Officer intervention — {officer.name} ({officer.role.replace("_", " ")})</p>
        <div className="flex flex-wrap gap-2">
          {can("incidents.update") && i.status === "open" && <Btn tone="plan" icon={ClipboardCheck} disabled={busy} onClick={() => act("Under review", `/api/officer/incidents/${i.incident_id}/status`, { status: "under_review", note: "investigating" })}>Mark under review</Btn>}
          {can("cases.reassign") && inv.case && Object.entries(tasks).map(([task, receivers]) => receivers.filter((r) => r !== inv.case?.task_assignments[task] && r !== i.agent_id).map((r) => (
            <Btn key={task + r} tone="trust" icon={UserCog} disabled={busy} onClick={() => act("Reassign", `/api/officer/cases/${inv.case!.case_id}/reassign`, { task, receiving_agent_id: r, note: `replace ${i.agent_id}` })}>
              Reassign {humanize(task.replace(/_/g, " "))} → {r}
            </Btn>
          )))}
          {can("cases.resume") && inv.case?.state === "PAUSED_FOR_REVIEW" && <Btn tone="trust" icon={Play} disabled={busy} onClick={() => act("Resume", `/api/officer/cases/${inv.case!.case_id}/resume`, { note: "review complete; affected authority contained" })}>Resume case</Btn>}
          {can("incidents.update") && ["open", "under_review", "contained"].includes(i.status) && <Btn tone="trust" icon={BadgeCheck} disabled={busy} onClick={() => act("Resolve", `/api/officer/incidents/${i.incident_id}/status`, { status: "resolved", note: "recovered via standby authority" })}>Resolve incident</Btn>}
        </div>
        {msg && <p className={clsx("mt-3 text-[12.5px]", msg.ok ? "text-trust" : "text-deny")}>{msg.text}</p>}
        <p className="mt-3 text-[11.5px] text-fg-subtle">These actions change authority only. The case advances solely through signed agent requests checked by the gateway.</p>
      </div>
    </div>
  );
}

// --- main page ------------------------------------------------------------------------------------------
type Tab = "overview" | "watch" | "incidents" | "approvals" | "recovery" | "oversight" | "audit";

export function SecurityOperations() {
  const caps = useApi<SystemCapabilities>("/api/system/capabilities", { live: true });
  const devMode = caps.status === "success" && caps.data.developer_demo_enabled;
  const [officer, setOfficer] = useState<Officer | null>(null);
  const [checking, setChecking] = useState(hasOfficerToken());
  const [tab, setTab] = useState<Tab>("overview");
  const [ov, setOv] = useState<Overview | null>(null);
  const [cases, setCases] = useState<CaseRow[]>([]);
  const [incidents, setIncidents] = useState<Incident[]>([]);
  const [approvals, setApprovals] = useState<Approval[]>([]);
  const [audit, setAudit] = useState<AuditEvent[]>([]);
  const [selected, setSelected] = useState<string | null>(null);
  const [run, setRun] = useState<WorkflowRun | null>(null);
  const [comparison, setComparison] = useState<Record<string, any> | null>(null); // eslint-disable-line @typescript-eslint/no-explicit-any
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    try {
      const [o, c, i, a, au] = await Promise.all([
        officerRequest<Overview>("/api/officer/overview"), officerRequest<CaseRow[]>("/api/officer/cases"),
        officerRequest<Incident[]>("/api/officer/incidents"), officerRequest<Approval[]>("/api/officer/approvals"),
        officerRequest<AuditEvent[]>("/api/officer/audit")]);
      setOv(o); setCases(c); setIncidents(i); setApprovals(a); setAudit(au);
      invalidate("/api/audit", "/api/mandates", "/api/workflow");
    } catch (e) {
      if (e instanceof ApiError && e.status === 401) setOfficer(null);
      else setError((e as Error).message);
    }
  }, []);

  useEffect(() => {
    if (!hasOfficerToken()) return;
    officerRequest<Officer>("/api/officer/me").then(setOfficer).catch(() => setOfficer(null)).finally(() => setChecking(false));
  }, []);
  useEffect(() => {  // live: the portal and this console read the same backend state
    if (!officer) return;
    refresh();
    const id = setInterval(() => refresh(), 3000);
    return () => clearInterval(id);
  }, [officer, refresh]);

  async function signOut() {
    try { await officerRequest("/api/officer/session", "DELETE"); } catch { /* already expired */ }
    setOfficerToken(null);
    setOfficer(null);
  }
  async function step(label: string, fn: () => Promise<void>) {
    setBusy(label); setError(null);
    try { await fn(); await refresh(); } catch (e) { setError(e instanceof ApiError ? `${e.code}: ${e.message}` : (e as Error).message); } finally { setBusy(null); }
  }
  const startRecovery = () => step("setup", async () => { const r = await apiPost<WorkflowRun>("/api/workflow/scenarios/safe_recovery/run", { citizen_ref: "C-1001" }); setRun(r); setTab("incidents"); });
  const continueCase = (cid: string) => step("continue", async () => { const r = await apiPost<WorkflowRun>(`/api/workflow/recovery/${cid}/continue`); setRun(r); });
  const decide = (id: string, approve: boolean) => step(id, async () => { await officerRequest(`/api/officer/approvals/${id}/${approve ? "approve" : "reject"}`, "POST", { note: approve ? "approved after review" : "rejected" }); });
  const compare = () => step("compare", async () => { setComparison(await apiPost<Record<string, any>>("/api/workflow/oversight-comparison", { clean_cases: 4, violating_cases: 1, minutes_per_review: 2 })); }); // eslint-disable-line @typescript-eslint/no-explicit-any

  const TABS: [Tab, string, LucideIcon][] = [["overview", "Overview", Activity], ["watch", "Behaviour Watch", Radar], ["incidents", "Incidents", ShieldAlert], ["approvals", "Approvals", ClipboardCheck],
    ["recovery", "Recovery", RefreshCw], ["oversight", "Oversight comparison", Scale], ["audit", "Officer audit", History]];
  const recoveryCases = run ? [run.case, ...run.related_cases] : [];

  return (
    <>
      <PageHeader eyebrow="Phase 4 · Continuous assurance" title="Security Operations" titleAr="العمليات الأمنية"
        description="Deterministic behavioural rules watch every audited gateway and delegation decision. Exceptions become incidents with graduated, mandate-level responses; authenticated officers investigate, intervene and recover the service — which still completes only through the gateway."
        actions={<SyntheticBadge />} />
      {checking && !officer ? <p className="text-[13px] text-fg-subtle">Checking session…</p> : !officer ? (
        <>
          <Notice tone="plan" icon={KeyRound} title="Officer console requires sign-in">
            Incident evidence and every intervention are served only to an authenticated officer session. The browser never
            holds administrative credentials; permissions and entity scope are enforced by the backend.
          </Notice>
          <SignIn onSignedIn={setOfficer} />
        </>
      ) : (
        <>
          <div className="mb-5 flex flex-wrap items-center gap-3 rounded-xl border border-line bg-ink-850/80 px-4 py-3">
            <ShieldCheck className="size-5 text-trust" aria-hidden />
            <div className="min-w-0">
              <p className="text-[13.5px] font-medium text-fg">{officer.name} · {officer.title}</p>
              <p className="font-mono text-[11.5px] text-fg-subtle">{officer.officer_id} · {officer.role} · {officer.entity} · session until {time(officer.session_expires_at)}</p>
            </div>
            <span className="ml-auto flex gap-2">
              <Btn icon={RefreshCw} onClick={() => refresh()}>Refresh</Btn>
              <Btn icon={LogOut} onClick={signOut}>Sign out</Btn>
            </span>
          </div>
          <div className="mb-5 flex flex-wrap gap-1 border-b border-line" role="tablist">
            {TABS.map(([k, label, Icon]) => (
              <button key={k} role="tab" aria-selected={tab === k} onClick={() => setTab(k)}
                className={clsx("inline-flex items-center gap-1.5 border-b-2 px-3 pb-2.5 pt-1 text-[13px]", tab === k ? "border-trust text-fg" : "border-transparent text-fg-subtle hover:text-fg-muted")}>
                <Icon className="size-3.5" aria-hidden /> {label}
                {k === "incidents" && incidents.filter((x) => x.status === "open" || x.status === "under_review").length > 0 && <span className="rounded-full bg-deny-soft px-1.5 text-[10.5px] text-deny">{incidents.filter((x) => x.status === "open" || x.status === "under_review").length}</span>}
                {k === "approvals" && approvals.filter((x) => x.status === "pending").length > 0 && <span className="rounded-full bg-warn-soft px-1.5 text-[10.5px] text-warn">{approvals.filter((x) => x.status === "pending").length}</span>}
              </button>
            ))}
          </div>
          {error && <p className="mb-4 rounded-xl border border-deny/30 bg-deny-soft px-4 py-3 text-[13px] text-deny">{error}</p>}

          {tab === "overview" && <OverviewPanel ov={ov} cases={cases} />}
          {tab === "watch" && <BehaviourWatch />}

          {tab === "incidents" && (
            <div className="grid gap-6 2xl:grid-cols-[380px_1fr]">
              <Card className="min-w-0">
                <CardHeader icon={Clock} title="Live incident timeline" subtitle="Deterministic rules · newest first" />
                {incidents.length === 0 ? <EmptyState icon={ShieldCheck} title="No incidents">Rules fire only on real audited decisions.</EmptyState> : (
                  <ul className="divide-y divide-line">{incidents.map((x) => (
                    <li key={x.incident_id}>
                      <button onClick={() => setSelected(x.incident_id)} className={clsx("w-full px-4 py-3 text-left hover:bg-ink-800", selected === x.incident_id && "bg-ink-750")}>
                        <span className="flex items-center gap-2">
                          <Badge tone={SEV_TONE[x.severity] ?? "neutral"}>{x.severity}</Badge>
                          <span className="text-[13px] font-medium text-fg">{x.title}</span>
                        </span>
                        <span className="mt-1 block font-mono text-[11px] text-fg-subtle">{x.incident_id} · {x.status} · {x.agent_id} · {x.case_id ?? "no case"} · {time(x.last_seen)}</span>
                      </button>
                    </li>
                  ))}</ul>
                )}
              </Card>
              <Card className="min-w-0">
                <CardHeader icon={ShieldAlert} title="Investigation" subtitle={selected ?? "Select an incident"} />
                {selected ? <InvestigationPanel key={selected} id={selected} officer={officer} onChanged={refresh} /> : <p className="p-5 text-[13px] text-fg-subtle">Select an incident to see the citizen request, delegated chain, violated rule, completed actions and open requirements.</p>}
              </Card>
            </div>
          )}

          {tab === "approvals" && (
            <Card>
              <CardHeader icon={ClipboardCheck} title="Human approval queue" subtitle="Held requests never execute while pending. Approval re-runs all current authorization checks." />
              {approvals.length === 0 ? <EmptyState icon={ClipboardCheck} title="No approvals" /> : (
                <ul className="divide-y divide-line">{[...approvals].sort((x, y) => Number(y.status === "pending") - Number(x.status === "pending")).map((a) => (
                  <li key={a.approval_id} className="flex flex-wrap items-center gap-3 px-5 py-3">
                    <Badge tone={a.status === "pending" ? "warn" : a.status === "approved_executed" ? "trust" : a.status === "approved_denied" ? "deny" : "neutral"}>{a.status.replace(/_/g, " ")}</Badge>
                    <div className="min-w-0">
                      <p className="font-mono text-[12.5px] text-fg">{a.tool_name} · {a.agent_id}</p>
                      <p className="font-mono text-[11px] text-fg-subtle">{a.approval_id} · case {a.case_id} · incident {a.incident_id} · expires {time(a.expires_at)}</p>
                      {a.reauthorization_codes.length > 0 && <p className="font-mono text-[11px] text-fg-muted">re-authorization: {a.reauthorization_codes.join(" · ")}</p>}
                    </div>
                    {a.status === "pending" && officer.permissions.includes("approvals.decide") && (
                      <span className="ml-auto flex gap-2">
                        <Btn tone="trust" icon={CheckCircle2} disabled={busy !== null} onClick={() => decide(a.approval_id, true)}>Approve &amp; re-authorize</Btn>
                        <Btn tone="deny" icon={XCircle} disabled={busy !== null} onClick={() => decide(a.approval_id, false)}>Reject</Btn>
                      </span>
                    )}
                  </li>
                ))}</ul>
              )}
            </Card>
          )}

          {tab === "recovery" && (
            <div className="space-y-6">
              <Card>
                <CardHeader icon={RefreshCw} title="Safe service recovery" subtitle="Simulated agents · real gateway · real officer actions" right={<Badge tone="warn">Development only</Badge>} />
                <div className="space-y-3 p-5 text-[13px] text-fg-muted">
                  <p>1 · Start the scenario: Mariam's and Omar's delegated cases; the Insurance Agent requests another citizen's record on Mariam's case.</p>
                  <p>2 · In <b className="text-fg">Incidents</b>: review, reassign insurance verification to the standby agent, resume the case.</p>
                  <p>3 · Continue the case with agents; approve held sensitive steps in <b className="text-fg">Approvals</b>; resolve the incident; continue until complete.</p>
                  <div className="flex flex-wrap gap-2 pt-1">
                    <Btn tone="trust" icon={Play} disabled={!devMode || busy !== null} onClick={startRecovery}>{busy === "setup" ? "Running…" : "Start safe-recovery scenario"}</Btn>
                    {cases.filter((c) => c.incident_policy === "contain" && c.state !== "COMPLETED").slice(0, 4).map((c) => (
                      <Btn key={c.case_id} icon={FileSignature} disabled={!devMode || busy !== null} onClick={() => continueCase(c.case_id)}>Continue {c.case_id} ({c.citizen_ref})</Btn>
                    ))}
                  </div>
                  {!devMode && <p className="text-warn">Developer mode is off — start the backend with run_dev.py.</p>}
                </div>
              </Card>
              {run && (
                <Card>
                  <CardHeader icon={History} title={`Latest agent run · ${recoveryCases.map((c) => c.case_id).join(", ")}`} subtitle="Each step is a signed request through Gateway.execute()" />
                  {run.steps.length === 0 ? <p className="px-5 py-4 text-[13px] text-fg-subtle">No step could run (e.g. the case is paused for review).</p> : (
                    <ol className="divide-y divide-line">{run.steps.map((s) => (
                      <li key={s.index} className="flex flex-wrap items-start gap-3 px-5 py-3">
                        <span className="font-mono text-[11px] text-fg-subtle">{s.index}</span>
                        {s.decision ? <Badge tone={s.decision.allowed ? "trust" : s.execution_status === "pending_approval" ? "warn" : "deny"}>{s.decision.allowed ? "AUTHORIZED" : s.execution_status === "pending_approval" ? "UNDER REVIEW" : "DENIED"}</Badge> : <Badge tone="warn">CONTROL</Badge>}
                        <div className="min-w-0">
                          <p className="text-[13px] text-fg">{s.title}</p>
                          <p className="font-mono text-[11px] text-fg-subtle">{s.agent_id} · {s.tool_name} · {s.case_state_before} → {s.case_state_after}</p>
                          {s.decision && !s.decision.allowed && <p className="font-mono text-[11px] text-deny">{s.decision.reason_codes.join(" · ")}</p>}
                        </div>
                      </li>
                    ))}</ol>
                  )}
                </Card>
              )}
            </div>
          )}

          {tab === "oversight" && (
            <Card>
              <CardHeader icon={Scale} title="Human oversight workload — controlled comparison" subtitle="Same synthetic workload, isolated in-memory environment, real gateway decisions" />
              <div className="p-5">
                <Btn tone="trust" icon={Play} disabled={!devMode || busy !== null} onClick={compare}>{busy === "compare" ? "Running…" : "Run comparison"}</Btn>
                {comparison && (
                  <div className="mt-5 space-y-4">
                    <p className="rounded-lg border border-warn/30 bg-warn-soft px-3 py-2 text-[12.5px] text-warn">{comparison.assumptions.baseline_A} {comparison.assumptions.note}</p>
                    <div className="overflow-x-auto">
                      <table className="w-full min-w-[640px] text-left text-[13px]">
                        <thead><tr className="border-b border-line text-[11px] uppercase tracking-wider text-fg-subtle"><th className="px-3 py-2">Measure</th><th className="px-3 py-2">A · hypothetical manual review</th><th className="px-3 py-2">B · WAKALA exceptions only</th></tr></thead>
                        <tbody>{([
                          ["Requests processed", "requests_processed"], ["Requests requiring officer review", "requests_requiring_officer_review"],
                          ["Officer interventions", "officer_interventions"], ["Legitimate actions completed", "legitimate_actions_completed"],
                          ["Security decisions preserved", "security_decisions_preserved"],
                          [`Review time (assumed ${comparison.assumptions.minutes_per_human_review} min/review)`, "review_workflow_minutes_assumed"],
                        ] as [string, string][]).map(([label, key]) => (
                          <tr key={key} className="border-b border-line/60">
                            <td className="px-3 py-2 text-fg-muted">{label}</td>
                            <td className="px-3 py-2 font-mono text-fg">{String(comparison.A_manual_review_heavy[key])}</td>
                            <td className="px-3 py-2 font-mono text-trust">{String(comparison.B_wakala_automatic_with_exceptions[key])}</td>
                          </tr>
                        ))}</tbody>
                      </table>
                    </div>
                    <p className="font-mono text-[11.5px] text-fg-subtle">
                      Measured: {comparison.B_wakala_automatic_with_exceptions.incidents_escalated} incident(s), {comparison.B_wakala_automatic_with_exceptions.approvals_held} held approval(s),
                      {" "}{comparison.B_wakala_automatic_with_exceptions.cases_completed} cases completed, gateway time {comparison.B_wakala_automatic_with_exceptions.measured_gateway_decision_ms_total} ms total ·
                      audit chain {comparison.audit_chain_valid ? "valid" : "INVALID"}. No staffing or approval-rate claims are made.
                    </p>
                  </div>
                )}
              </div>
            </Card>
          )}

          {tab === "audit" && (
            <Card>
              <CardHeader icon={History} title="Officer decisions and automated responses" subtitle="Hash-chained audit events (actor = officer or WAKALA-GATEWAY)" />
              {audit.length === 0 ? <EmptyState icon={History} title="No officer or response events yet" /> : (
                <ul className="divide-y divide-line">{audit.map((e) => (
                  <li key={e.event_id} className="px-5 py-2.5 font-mono text-[11.5px]">
                    <span className="text-fg-subtle">#{e.sequence} {time(e.timestamp)}</span> <span className="text-fg">{e.actor}</span> <span className="text-cyan">{e.action}</span>
                    <span className="block text-fg-subtle">{Object.entries(e.evidence_metadata).filter(([k]) => k !== "origin").map(([k, v]) => `${k}=${String(v)}`).join(" · ")}</span>
                  </li>
                ))}</ul>
              )}
            </Card>
          )}
        </>
      )}
    </>
  );
}
