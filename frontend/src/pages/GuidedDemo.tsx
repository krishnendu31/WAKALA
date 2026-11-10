/* eslint-disable @typescript-eslint/no-explicit-any */
/**
 * Guided demonstration for first-time, non-technical visitors.
 *
 * Every state shown here is read from the backend (portal case views, officer API). Every button calls the
 * same endpoint the existing Government AI Portal and Security Operations console call. Nothing is simulated
 * in the browser: officer actions require a real officer session, approvals are re-authorized by the gateway,
 * and success is shown only when the backend reports it.
 */
import clsx from "clsx";
import {
  AlertTriangle, ArrowLeft, ArrowRight, BadgeCheck, Bot, Building2, Check, CheckCircle2, ChevronDown, Circle, CircleDot,
  ClipboardCheck, ExternalLink, FlaskConical, KeyRound, LayoutDashboard, Loader2, LogOut, PauseCircle, Play, ReceiptText,
  RotateCcw, ShieldCheck, ShieldX, UserCog, UserRound, Wrench, type LucideIcon,
} from "lucide-react";
import { useCallback, useEffect, useState, type ReactNode } from "react";
import { Link } from "react-router-dom";
import { AiActivityReceipt } from "@/components/AiActivityReceipt";
import { BrandMark } from "@/layouts/AppLayout";
import { ApiError, apiGet, apiPost, hasOfficerToken, officerRequest, setOfficerToken } from "@/lib/api";

type Any = Record<string, any>;
const REQUEST_TEXT = "I want to renew my residency permit.";
/** Plain-language names for the gateway tool names shown to visitors (technical names stay in Technical details). */
const ACTION_LABEL: Record<string, string> = {
  "insurance.verify_case_eligibility": "Read a citizen's insurance record",
  "residency.register_renewal_case": "Register the renewal application",
  "residency.check_eligibility": "Check residency eligibility",
  "delegation.commission_task": "Hand a task to another agent",
  "payment.collect_renewal_fee": "Collect the renewal fee",
  "residency.complete_renewal": "Complete the renewal",
};

// ------------------------------------------------------------------------------------------------ data hooks
function usePoll<T>(path: string | null, ms: number): { data: T | null; error: string | null; reload: () => void } {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [n, setN] = useState(0);
  useEffect(() => {
    if (!path) { setData(null); setError(null); return; }
    let live = true;
    const tick = () => apiGet<T>(path).then((d) => { if (live) { setData(d); setError(null); } })
      .catch((e) => live && setError(errText(e)));
    tick();
    const id = setInterval(tick, ms);
    return () => { live = false; clearInterval(id); };
  }, [path, ms, n]);
  return { data, error, reload: useCallback(() => setN((x) => x + 1), []) };
}

function errText(e: unknown): string {
  if (e instanceof ApiError) {
    if (e.status === 0) return "The WAKALA backend is not reachable. Check that it is running, then try again.";
    if (e.status === 401) return "The officer session is missing or has expired. Please sign in again.";
    if (e.status === 403) return "This officer is not permitted to perform that action.";
    return `${e.message} (${e.code})`;
  }
  return String(e);
}

/** Runs one backend call with busy and error state, and remembers it so the visitor can retry. */
function useAction(after: () => void) {
  const [busy, setBusy] = useState<string | null>(null);
  const [failure, setFailure] = useState<{ label: string; message: string; retry: () => void } | null>(null);
  const run = useCallback(async (label: string, fn: () => Promise<unknown>) => {
    setBusy(label); setFailure(null);
    try { await fn(); return true; }
    catch (e) { setFailure({ label, message: errText(e), retry: () => void run(label, fn) }); return false; }
    finally { setBusy(null); after(); }
  }, [after]);
  return { busy, failure, run, clear: () => setFailure(null) };
}

// ------------------------------------------------------------------------------------------------ small UI
function PrimaryButton({ onClick, busy, disabled, children, tone = "trust", icon: Icon }:
  { onClick: () => void; busy?: boolean; disabled?: boolean; children: ReactNode; tone?: "trust" | "deny" | "navy"; icon?: LucideIcon }) {
  return (
    <button onClick={onClick} disabled={busy || disabled}
      className={clsx("inline-flex items-center gap-2 rounded-xl px-5 py-3 text-[16px] font-semibold text-ink-950 shadow-[var(--shadow-card)] transition-colors disabled:cursor-not-allowed disabled:opacity-40",
        tone === "deny" ? "bg-deny hover:bg-deny/90" : tone === "navy" ? "bg-navy hover:bg-navy/90" : "bg-trust hover:bg-trust-strong")}>
      {busy ? <Loader2 className="size-5 animate-spin" aria-hidden /> : Icon ? <Icon className="size-5" aria-hidden /> : null}
      {children}
    </button>
  );
}

function Failure({ failure, onDismiss }: { failure: { label: string; message: string; retry: () => void } | null; onDismiss: () => void }) {
  if (!failure) return null;
  return (
    <div role="alert" className="mt-4 rounded-xl border border-deny/40 bg-deny-soft p-4 text-[15px] text-fg">
      <p className="flex items-center gap-2 font-semibold text-deny"><AlertTriangle className="size-5" aria-hidden /> “{failure.label}” did not complete</p>
      <p className="mt-1">{failure.message}</p>
      <p className="mt-1 text-[13.5px] text-fg-muted">The status on this page is read from WAKALA, so it shows what actually happened. Check it, then try again.</p>
      <div className="mt-3 flex gap-2">
        <button onClick={failure.retry} className="rounded-lg bg-deny px-3.5 py-2 text-[14px] font-semibold text-ink-950">Try again</button>
        <button onClick={onDismiss} className="rounded-lg border border-line-strong px-3.5 py-2 text-[14px] text-fg-muted hover:bg-ink-800">Dismiss</button>
      </div>
    </div>
  );
}

function TechDetails({ children, label = "Technical details" }: { children: ReactNode; label?: string }) {
  return (
    <details className="group mt-5 rounded-xl border border-line bg-ink-800/60">
      <summary className="flex cursor-pointer list-none items-center gap-2 px-4 py-2.5 text-[14px] font-medium text-fg-muted hover:text-fg">
        <Wrench className="size-4" aria-hidden /> {label} <span className="text-fg-subtle">(optional)</span>
        <ChevronDown className="ml-auto size-4 transition-transform group-open:rotate-180" aria-hidden />
      </summary>
      <div className="space-y-2 border-t border-line px-4 py-3 font-mono text-[12.5px] leading-relaxed text-fg-muted">{children}</div>
    </details>
  );
}

function RoleTag({ role }: { role: "citizen" | "officer" }) {
  return role === "citizen"
    ? <span className="inline-flex items-center gap-1.5 rounded-full bg-trust-soft px-3 py-1 text-[13px] font-semibold text-trust"><UserRound className="size-4" aria-hidden /> Citizen view</span>
    : <span className="inline-flex items-center gap-1.5 rounded-full bg-navy-soft px-3 py-1 text-[13px] font-semibold text-navy"><UserCog className="size-4" aria-hidden /> Security officer view</span>;
}

function Waiting({ text }: { text: string }) {
  return <p className="flex items-center gap-2 py-3 text-[15px] text-fg-muted"><Loader2 className="size-4 animate-spin" aria-hidden /> {text}</p>;
}

const STATE_LABEL: Record<string, string> = {
  CREATED: "Received", VERIFYING: "In progress", AWAITING_PAYMENT: "Waiting for fee payment", PAUSED_FOR_REVIEW: "Paused for security review",
  COMPLETED: "Completed", FAILED: "Could not be completed",
};
function CaseStatus({ view }: { view: Any }) {
  const tone = view.state === "COMPLETED" ? "text-trust" : view.state === "PAUSED_FOR_REVIEW" ? "text-warn" : view.state === "FAILED" ? "text-deny" : "text-navy";
  return (
    <span className={clsx("font-semibold", tone)}>
      {STATE_LABEL[view.state] ?? view.state}{view.state === "COMPLETED" && view.recovery_status === "recovered" ? " — recovered after a security review" : ""}
    </span>
  );
}

function Progress({ steps }: { steps: Any[] }) {
  return (
    <ol className="space-y-2.5">
      {steps.map((s) => {
        const Icon = s.status === "done" ? CheckCircle2 : s.status === "blocked" ? PauseCircle : s.status === "active" ? CircleDot : Circle;
        return (
          <li key={s.key} className="flex items-start gap-2.5">
            <Icon className={clsx("mt-0.5 size-5 shrink-0", s.status === "done" ? "text-trust" : s.status === "blocked" ? "text-warn" : s.status === "active" ? "text-navy" : "text-fg-subtle")} aria-hidden />
            <span className={clsx("text-[15px]", s.status === "pending" ? "text-fg-subtle" : "text-fg")}>
              {s.label}{s.status === "blocked" && <span className="block text-[13px] text-warn">Paused for security review</span>}
            </span>
          </li>
        );
      })}
    </ol>
  );
}

function Decisions({ timeline }: { timeline: Any[] }) {
  if (!timeline.length) return <p className="text-[15px] text-fg-subtle">No agent actions yet.</p>;
  return (
    <ul className="space-y-2">
      {timeline.map((t) => {
        const ok = t.decision === "allowed";
        const Icon = ok ? ShieldCheck : t.decision === "denied" ? ShieldX : PauseCircle;
        return (
          <li key={t.event_id} className={clsx("flex gap-2.5 rounded-lg border px-3 py-2 text-[14.5px] leading-snug",
            ok ? "border-line bg-ink-850" : t.decision === "denied" ? "border-deny/40 bg-deny-soft" : "border-warn/40 bg-warn-soft")}>
            <Icon className={clsx("mt-0.5 size-[18px] shrink-0", ok ? "text-trust" : t.decision === "denied" ? "text-deny" : "text-warn")} aria-hidden />
            <span>{t.plain_english}</span>
          </li>
        );
      })}
    </ul>
  );
}

/** Messages from the most recent assistant run, exactly as the backend recorded them. */
function LatestRun({ view }: { view: Any }) {
  const run = view.agent_runs?.at(-1);
  if (!run) return null;
  const lines: { text: string; tone: "ok" | "deny" | "hold" }[] = [];
  for (const t of run.transcript ?? []) {
    if (t.role === "assistant") lines.push({ text: t.text, tone: "ok" });
    if (t.role === "tool") {
      const inner = t.output?.insurance_check ?? t.output ?? {};
      const held = (inner.reason_codes ?? []).includes("ESCALATE_HUMAN_REVIEW");
      const text = inner.plain_english ?? t.output?.error;
      if (text) lines.push({ text, tone: held ? "hold" : t.is_error ? "deny" : "ok" });
    }
  }
  if (!lines.length) return null;
  return (
    <div className="mt-4">
      <p className="eyebrow mb-2">What the AI assistant reported</p>
      <ul className="space-y-1.5">
        {lines.slice(-4).map((l, i) => (
          <li key={i} className={clsx("flex gap-2 rounded-lg px-3 py-2 text-[14.5px]", l.tone === "hold" ? "bg-warn-soft" : l.tone === "deny" ? "bg-deny-soft" : "bg-ink-800")}>
            <Bot className={clsx("mt-0.5 size-4 shrink-0", l.tone === "hold" ? "text-warn" : l.tone === "deny" ? "text-deny" : "text-trust")} aria-hidden />{l.text}
          </li>
        ))}
      </ul>
      <p className="mt-1.5 text-[12.5px] text-fg-subtle">{run.mode?.startsWith("model") ? "AI model" : "Deterministic offline assistant (no AI model)"} · run {run.run_id}</p>
    </div>
  );
}

function CitizenCard({ view, children }: { view: Any; children?: ReactNode }) {
  return (
    <section className="card p-5">
      <div className="flex items-center justify-between gap-3"><RoleTag role="citizen" /><span className="font-mono text-[12.5px] text-fg-subtle">{view.case_id}</span></div>
      <div className="mt-4 flex items-center gap-3">
        <span className="flex size-11 items-center justify-center rounded-full bg-ink-700 text-[17px] font-semibold text-fg">{(view.citizen_name ?? "?").slice(0, 1)}</span>
        <div>
          <p className="text-[17px] font-semibold text-fg">{view.citizen_name} <span className="font-mono text-[13px] font-normal text-fg-subtle">{view.citizen_ref}</span></p>
          <p className="text-[14.5px] text-fg-muted">Residency permit renewal · AED 500 · <CaseStatus view={view} /></p>
        </div>
      </div>
      {view.banner?.text && (
        <p className={clsx("mt-4 rounded-lg px-3.5 py-2.5 text-[15px]",
          view.banner.kind === "success" ? "bg-trust-soft text-trust" : view.banner.kind === "review" ? "bg-warn-soft text-warn" : "bg-ink-800 text-fg")}>{view.banner.text}</p>
      )}
      {children}
    </section>
  );
}

// ------------------------------------------------------------------------------------------------ officer session
function useOfficer() {
  const [officer, setOfficer] = useState<Any | null>(null);
  const [checked, setChecked] = useState(false);
  const [expired, setExpired] = useState(false);
  const refresh = useCallback(() => {
    if (!hasOfficerToken()) { setOfficer(null); setChecked(true); return; }
    officerRequest<Any>("/api/officer/me").then((o) => { setOfficer(o); setExpired(false); })
      .catch(() => { setOfficer(null); setExpired(true); }).finally(() => setChecked(true));
  }, []);
  useEffect(refresh, [refresh]);
  return { officer, checked, expired, setOfficer, refresh };
}

function OfficerSignIn({ onSignedIn, expired }: { onSignedIn: (o: Any) => void; expired: boolean }) {
  const [id, setId] = useState("OFF-0101");
  const [pw, setPw] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const submit = async (e: React.FormEvent) => {
    e.preventDefault(); setBusy(true); setErr(null);
    try {
      const r = await officerRequest<{ token: string; officer: Any }>("/api/officer/session", "POST", { officer_id: id, password: pw });
      setOfficerToken(r.token); setPw(""); onSignedIn(r.officer);
    } catch (x) {
      setErr(x instanceof ApiError && x.status === 401 ? "Officer ID or password is not correct." : errText(x));
    } finally { setBusy(false); }
  };
  return (
    <form onSubmit={submit} className="space-y-3">
      {expired && <p className="rounded-lg bg-warn-soft px-3 py-2 text-[14px] text-warn">Your officer session expired or was signed out. Please sign in again.</p>}
      <p className="text-[15px] text-fg">Only an authenticated security officer can investigate and intervene. Citizens cannot do this.</p>
      <div className="grid gap-3 sm:grid-cols-2">
        <label className="text-[13.5px] text-fg-muted">Officer ID
          <input value={id} onChange={(e) => setId(e.target.value)} className="mt-1 w-full rounded-lg border border-line-strong bg-ink-850 px-3 py-2.5 font-mono text-[15px] text-fg" autoComplete="username" />
        </label>
        <label className="text-[13.5px] text-fg-muted">Password
          <input type="password" value={pw} onChange={(e) => setPw(e.target.value)} className="mt-1 w-full rounded-lg border border-line-strong bg-ink-850 px-3 py-2.5 text-[15px] text-fg" autoComplete="current-password" />
        </label>
      </div>
      {err && <p role="alert" className="rounded-lg bg-deny-soft px-3 py-2 text-[14px] text-deny">{err}</p>}
      <PrimaryButton onClick={() => undefined} busy={busy} disabled={!pw} tone="navy" icon={KeyRound}>Sign in as officer</PrimaryButton>
      <p className="text-[13px] text-fg-subtle">Demo officer passwords are issued by the person running the demo (see the demo runbook). The browser never stores them.</p>
    </form>
  );
}

// ------------------------------------------------------------------------------------------------ checklist
type Task = { key: string; who: "citizen" | "officer"; title: string; why: string; done: boolean; ready: boolean; button: string;
              icon: LucideIcon; tone?: "trust" | "deny" | "navy"; onClick: () => void; blockedReason?: string };

function Checklist({ tasks, busy, showRoles = true }: { tasks: Task[]; busy: string | null; showRoles?: boolean }) {
  const next = tasks.find((t) => !t.done);
  return (
    <ol className="space-y-2.5">
      {tasks.map((t, i) => {
        const current = t === next;
        return (
          <li key={t.key} className={clsx("rounded-xl border p-4", t.done ? "border-line bg-ink-850" : current ? "border-trust/50 bg-trust-soft" : "border-line bg-ink-800/50")}>
            <div className="flex items-start gap-3">
              <span className={clsx("mt-0.5 flex size-7 shrink-0 items-center justify-center rounded-full text-[13px] font-semibold",
                t.done ? "bg-trust text-ink-950" : current ? "bg-navy text-ink-950" : "bg-ink-700 text-fg-muted")}>
                {t.done ? <Check className="size-4" aria-hidden /> : i + 1}
              </span>
              <div className="min-w-0 flex-1">
                <p className="flex flex-wrap items-center gap-2 text-[16px] font-semibold text-fg">{t.title}{showRoles && <RoleTag role={t.who} />}</p>
                <p className="mt-0.5 text-[14.5px] text-fg-muted">{t.why}</p>
                {current && (
                  <div className="mt-3">
                    {t.ready
                      ? <PrimaryButton onClick={t.onClick} busy={busy === t.key} disabled={busy !== null} tone={t.tone ?? (t.who === "officer" ? "navy" : "trust")} icon={t.icon}>{t.button}</PrimaryButton>
                      : <p className="text-[14px] text-fg-subtle">{t.blockedReason ?? "Waiting for the previous step."}</p>}
                  </div>
                )}
                {t.done && <p className="mt-1 text-[13.5px] font-medium text-trust">Done — confirmed by WAKALA</p>}
              </div>
            </div>
          </li>
        );
      })}
    </ol>
  );
}

// ------------------------------------------------------------------------------------------------ page
const SCENES = [
  { n: 1, title: "Normal service", goal: "See AI agents complete a citizen's request, with WAKALA checking every action before it runs." },
  { n: 2, title: "Unauthorized access", goal: "Watch WAKALA stop an AI agent that tries to read another citizen's record." },
  { n: 3, title: "Officer intervention", goal: "A security officer investigates and replaces only the agent that misbehaved." },
  { n: 4, title: "Safe recovery", goal: "The citizen's service continues, with an officer approving the sensitive step." },
  { n: 5, title: "Results and evidence", goal: "Check the outcome for every citizen, the AI activity receipt and the security evidence." },
];

export function GuidedDemo() {
  useEffect(() => { document.title = "Guided demo · WAKALA | وكالة"; }, []);
  const demo = usePoll<Any>("/api/portal/demo", 4000);
  const ids = demo.data?.cases ?? {};
  const s1 = usePoll<Any>(ids.scene1?.case_id ? `/api/portal/cases/${ids.scene1.case_id}` : null, 2500);
  const s2 = usePoll<Any>(ids.scene2_mariam?.case_id ? `/api/portal/cases/${ids.scene2_mariam.case_id}` : null, 2500);
  const other = usePoll<Any>(ids.scene2_unrelated?.case_id ? `/api/portal/cases/${ids.scene2_unrelated.case_id}` : null, 4000);
  const reloadAll = useCallback(() => { demo.reload(); s1.reload(); s2.reload(); other.reload(); }, [demo.reload, s1.reload, s2.reload, other.reload]); // eslint-disable-line react-hooks/exhaustive-deps
  const act = useAction(reloadAll);
  const off = useOfficer();

  // incident and approvals for the scene-2 case (officer API: requires a real session)
  const v2 = s2.data;
  const incidentId: string | null = v2?.active_incident?.incident_id ?? v2?.incidents?.find((i: Any) => i.rule_id === "CROSS_CITIZEN_ACCESS")?.incident_id ?? null;
  const [inv, setInv] = useState<Any | null>(null);
  const [approvals, setApprovals] = useState<Any[]>([]);
  const [officerErr, setOfficerErr] = useState<string | null>(null);
  const loadOfficer = useCallback(async () => {
    if (!off.officer || !incidentId || !v2) return;
    try {
      const [i, a] = await Promise.all([
        officerRequest<Any>(`/api/officer/incidents/${incidentId}`),
        officerRequest<Any[]>("/api/officer/approvals"),
      ]);
      setInv(i); setApprovals(a.filter((x) => x.case_id === v2.case_id)); setOfficerErr(null);
    } catch (e) {
      setOfficerErr(errText(e));
      if (e instanceof ApiError && e.status === 401) off.refresh();
    }
  }, [off.officer, incidentId, v2?.case_id, v2?.state, v2?.pending_approvals?.length]); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => { void loadOfficer(); const id = setInterval(() => void loadOfficer(), 4000); return () => clearInterval(id); }, [loadOfficer]);
  const officerAct = (key: string, fn: () => Promise<unknown>) => act.run(key, async () => { await fn(); await loadOfficer(); });

  // ---- progress derived from backend state
  const denied = v2?.timeline?.find((t: Any) => t.decision === "denied") ?? null;
  const incident = inv?.incident ?? v2?.active_incident ?? null;
  const incStatus: string | null = inv?.incident?.status ?? v2?.incidents?.find((i: Any) => i.incident_id === incidentId)?.status ?? null;
  const badAgent: string | null = incident?.agent_id ?? denied?.agent_id ?? null;
  const reassigned = !!v2 && Object.values(v2.task_assignments ?? {}).some((a) => a !== badAgent);
  const caseApproval = approvals.find((a) => a.status === "pending") ?? approvals.at(-1) ?? null;
  const approvedOk = approvals.some((a) => String(a.status).startsWith("approved"));
  const s1Done = s1.data?.state === "COMPLETED";
  const s2Done = !!denied;
  const s3Done = s2Done && reassigned && v2?.state !== "PAUSED_FOR_REVIEW";
  const s4Done = s2Done && v2?.state === "COMPLETED" && v2?.recovery_status === "recovered";
  const doneFlags = [s1Done, s2Done, s3Done, s4Done, s4Done];

  const firstOpen = doneFlags.findIndex((d) => !d);
  const [scene, setScene] = useState<number | null>(null);
  const current = scene ?? (firstOpen === -1 ? 5 : firstOpen + 1);
  useEffect(() => { act.clear(); }, [current]); // eslint-disable-line react-hooks/exhaustive-deps
  const [receiptFor, setReceiptFor] = useState<string | null>(null);
  const evidence = usePoll<Any>(current === 5 ? "/api/evidence/summary" : null, 120000);

  const restart = () => act.run("restart", async () => {
    await apiPost("/api/portal/demo/reset"); setScene(1); setInv(null); setApprovals([]);
  });

  const meta = SCENES[current - 1]!;
  const loadingDemo = !demo.data && !demo.error;

  return (
    <div className="min-h-screen bg-ink-900">
      {/* focused header: no console navigation while in the guided demo */}
      <header className="sticky top-0 z-20 border-b border-line bg-ink-850">
        <div className="mx-auto flex max-w-[1240px] items-center justify-between gap-4 px-5 py-3">
          <Link to="/" className="flex items-center gap-3" title="Back to the welcome page">
            <BrandMark />
            <span className="text-[17px] font-semibold tracking-[0.08em] text-navy">WAKALA</span>
            <span className="hidden text-[15px] text-fg-muted sm:inline">· Guided demo</span>
          </Link>
          <div className="flex items-center gap-2">
            <span className="hidden items-center gap-1.5 rounded-full border border-gold/35 bg-gold-soft px-3 py-1 text-[12px] font-medium uppercase tracking-wider text-gold-strong md:inline-flex">
              <FlaskConical className="size-3.5" aria-hidden /> Fictional citizens · synthetic data
            </span>
            <button onClick={restart} disabled={act.busy !== null} title="Start a new demo session. Nothing is deleted; earlier records stay in the audit history."
              className="inline-flex items-center gap-1.5 rounded-lg border border-line-strong px-3 py-2 text-[14px] text-fg-muted hover:bg-ink-800 disabled:opacity-40">
              {act.busy === "restart" ? <Loader2 className="size-4 animate-spin" /> : <RotateCcw className="size-4" aria-hidden />} Restart demo
            </button>
            <Link to="/command-center" className="inline-flex items-center gap-1.5 rounded-lg border border-line-strong px-3 py-2 text-[14px] font-medium text-navy hover:bg-ink-800">
              <LayoutDashboard className="size-4" aria-hidden /> Advanced tools
            </Link>
          </div>
        </div>
        {/* stepper */}
        <nav aria-label="Demo steps" className="mx-auto max-w-[1240px] px-5 pb-3">
          <ol className="grid grid-cols-5 gap-2">
            {SCENES.map((s, i) => {
              const done = doneFlags[i];
              const active = s.n === current;
              return (
                <li key={s.n}>
                  <button onClick={() => setScene(s.n)} aria-current={active ? "step" : undefined}
                    className={clsx("flex w-full items-center gap-2 rounded-lg border px-2.5 py-2 text-left text-[14px] transition-colors",
                      active ? "border-trust bg-trust-soft font-semibold text-trust" : done ? "border-line bg-ink-850 text-fg" : "border-line bg-ink-850 text-fg-subtle hover:text-fg")}>
                    <span className={clsx("flex size-6 shrink-0 items-center justify-center rounded-full text-[12px] font-semibold",
                      done ? "bg-trust text-ink-950" : active ? "bg-navy text-ink-950" : "bg-ink-700 text-fg-muted")}>{done ? <Check className="size-3.5" /> : s.n}</span>
                    <span className="truncate">{s.title}</span>
                  </button>
                </li>
              );
            })}
          </ol>
        </nav>
      </header>

      <main className="mx-auto max-w-[1240px] px-5 pb-16 pt-6">
        <div className="mb-5">
          <p className="eyebrow">Step {current} of 5</p>
          <h1 className="mt-1 text-[28px] font-semibold tracking-tight text-navy">{meta.title}</h1>
          <p className="mt-1 text-[17px] text-fg-muted">{meta.goal}</p>
        </div>

        {demo.error && <div role="alert" className="mb-4 rounded-xl border border-deny/40 bg-deny-soft p-4 text-[15px] text-deny">{demo.error}</div>}
        {loadingDemo && <Waiting text="Connecting to WAKALA…" />}

        {current === 1 && <SceneNormal view={s1.data} loading={!!ids.scene1 && !s1.data} busy={act.busy}
          start={() => act.run("start", () => apiPost("/api/portal/requests", { citizen_ref: "C-1001", message: REQUEST_TEXT, use_model: true }))} />}

        {current === 2 && <SceneAttack view={v2} loading={!!ids.scene2_mariam && !v2} busy={act.busy} s1Case={ids.scene1?.case_id}
          run={() => act.run("attack", () => apiPost("/api/portal/scenes/incident"))} />}

        {current === 3 && (
          v2 ? (
            <div className="grid gap-5 lg:grid-cols-[minmax(0,5fr)_minmax(0,7fr)]">
              <CitizenCard view={v2}><div className="mt-4"><Progress steps={v2.steps} /></div></CitizenCard>
              <section className="card p-5">
                <div className="flex items-center justify-between gap-3"><RoleTag role="officer" />
                  {off.officer && <OfficerBadge officer={off.officer} onSignOut={async () => { try { await officerRequest("/api/officer/session", "DELETE"); } catch { /* expired */ } setOfficerToken(null); off.setOfficer(null); }} />}</div>
                {v2.state === "PAUSED_FOR_REVIEW" && !s3Done && (
                  <p className="mt-4 flex items-center gap-2 rounded-lg border border-warn/40 bg-warn-soft px-3.5 py-2.5 text-[16px] font-semibold text-warn">
                    <UserCog className="size-5" aria-hidden /> Security review required. Switch to the officer console.
                  </p>
                )}
                <div className="mt-4">
                  {!off.checked ? <Waiting text="Checking officer session…" /> : !off.officer
                    ? <OfficerSignIn expired={off.expired} onSignedIn={(o) => { off.setOfficer(o); }} />
                    : <OfficerIntervention inv={inv} view={v2} incStatus={incStatus} badAgent={badAgent} reassigned={reassigned} busy={act.busy} error={officerErr}
                        can={(p: string) => (off.officer?.permissions ?? []).includes(p)}
                        act={officerAct} />}
                </div>
              </section>
            </div>
          ) : <NeedsEarlier text="Run step 2 first: there is no incident to investigate yet." go={() => setScene(2)} />
        )}

        {current === 4 && (
          v2 ? <SceneRecovery view={v2} other={other.data} officer={off.officer} busy={act.busy} s3Done={s3Done}
            incStatus={incStatus} approval={caseApproval} approvedOk={approvedOk}
            continueMariam={(key: string) => act.run(key, () => apiPost(`/api/portal/cases/${v2.case_id}/continue`, { use_model: false }))}
            continueOther={() => act.run("other", () => apiPost(`/api/portal/cases/${ids.scene2_unrelated.case_id}/continue`, { use_model: false }))}
            approve={() => officerAct("approve", () => officerRequest(`/api/officer/approvals/${caseApproval!.approval_id}/approve`, "POST", { note: "approved after review (guided demo)" }))}
            resolve={() => officerAct("resolve", () => officerRequest(`/api/officer/incidents/${incidentId}/status`, "POST", { status: "resolved", note: "recovered via standby authority (guided demo)" }))}
            goSignIn={() => setScene(3)} />
            : <NeedsEarlier text="Run steps 2 and 3 first." go={() => setScene(2)} />
        )}

        {current === 5 && (
          v2 ? <SceneResults view={v2} other={other.data} s1={s1.data} evidence={evidence.data} recovered={s4Done} openReceipt={setReceiptFor} />
            : <NeedsEarlier text="Run the earlier steps first." go={() => setScene(1)} />
        )}

        <Failure failure={act.failure} onDismiss={act.clear} />

        <div className="mt-8 flex items-center justify-between">
          <button onClick={() => setScene(Math.max(1, current - 1))} disabled={current === 1}
            className="inline-flex items-center gap-1.5 rounded-lg px-3 py-2 text-[15px] text-fg-muted hover:bg-ink-800 disabled:opacity-30"><ArrowLeft className="size-4" /> Previous step</button>
          {current < 5 && (
            <button onClick={() => setScene(current + 1)}
              className={clsx("inline-flex items-center gap-1.5 rounded-lg px-4 py-2 text-[15px] font-semibold",
                doneFlags[current - 1] ? "bg-navy text-ink-950 hover:bg-navy/90" : "text-fg-muted hover:bg-ink-800")}>
              {doneFlags[current - 1] ? "Next step" : "Skip to next step"} <ArrowRight className="size-4" />
            </button>
          )}
        </div>
      </main>
      {receiptFor && <AiActivityReceipt caseId={receiptFor} onClose={() => setReceiptFor(null)} />}
    </div>
  );
}

function NeedsEarlier({ text, go }: { text: string; go: () => void }) {
  return (
    <div className="card p-6 text-[16px] text-fg">
      {text} <button onClick={go} className="ml-2 font-semibold text-trust underline-offset-2 hover:underline">Go there</button>
    </div>
  );
}

function OfficerBadge({ officer, onSignOut }: { officer: Any; onSignOut: () => void }) {
  return (
    <span className="flex items-center gap-2 text-[13.5px] text-fg-muted">
      Signed in: <b className="text-fg">{officer.name}</b> ({officer.officer_id})
      <button onClick={onSignOut} className="inline-flex items-center gap-1 rounded-md px-2 py-1 hover:bg-ink-800" title="Sign out"><LogOut className="size-3.5" /> Sign out</button>
    </span>
  );
}

// ------------------------------------------------------------------------------------------------ scenes
function SceneNormal({ view, loading, busy, start }: { view: Any | null; loading: boolean; busy: string | null; start: () => void }) {
  const completed = view?.state === "COMPLETED";
  return (
    <div className="grid gap-5 lg:grid-cols-2">
      <section className="card p-5">
        <RoleTag role="citizen" />
        <p className="mt-4 text-[16px] text-fg">Mariam Al Hashimi (a fictional citizen) asks the government AI assistant:</p>
        <blockquote className="mt-2 rounded-lg border-l-4 border-trust bg-ink-800 px-4 py-3 text-[17px] text-fg">“{REQUEST_TEXT}”</blockquote>
        <p className="mt-3 text-[15px] text-fg-muted">The Residency Agent registers the request and checks eligibility, hands the insurance check to an Insurance Agent,
          and the Payment Agent collects the AED 500 fee. Every action is a signed request that WAKALA checks first.</p>
        <div className="mt-5">
          <PrimaryButton onClick={start} busy={busy === "start"} disabled={busy !== null} icon={ArrowRight}>{view ? "Submit the request again (new case)" : "Submit Mariam's request"}</PrimaryButton>
        </div>
      </section>
      <section className="card p-5">
        <p className="eyebrow mb-3">What happened</p>
        {loading ? <Waiting text="Loading the case from WAKALA…" /> : !view ? <p className="text-[15px] text-fg-subtle">Nothing yet. Click “Submit Mariam's request”.</p> : (
          <>
            <p className="text-[16px]">Case status: <CaseStatus view={view} /></p>
            {completed && <p className="mt-2 flex items-center gap-2 text-[16px] font-semibold text-trust"><BadgeCheck className="size-5" /> {view.timeline.filter((t: Any) => t.decision === "allowed").length} agent actions, each checked and allowed by WAKALA.</p>}
            {view.state === "FAILED" && <p className="mt-2 text-[15px] text-deny">The service could not be completed. See the details below, then submit again.</p>}
            <div className="mt-4"><Decisions timeline={view.timeline} /></div>
            {view.ledger?.length > 0 && <p className="mt-3 text-[14px] text-fg-muted">Fee recorded: {view.ledger.map((l: Any) => `AED ${l.amount ?? l.amount_aed ?? "?"} → ${l.recipient ?? l.recipient_account ?? "?"}`).join(", ")} (synthetic treasury)</p>}
            {completed && <p className="mt-4 rounded-lg bg-trust-soft px-3.5 py-2.5 text-[15px] text-trust">Next: see what happens when an agent oversteps. Click “Next step”.</p>}
            <TechDetails>
              <p>case {view.case_id} · state {view.state}</p>
              {view.timeline.map((t: Any) => <p key={t.event_id}>{t.event_id} · {t.agent_id} · {t.tool_name} · {t.decision} · {t.reason_codes.join(", ")}</p>)}
            </TechDetails>
          </>
        )}
      </section>
    </div>
  );
}

function SceneAttack({ view, loading, busy, run, s1Case }: { view: Any | null; loading: boolean; busy: string | null; run: () => void; s1Case?: string }) {
  const denied = view?.timeline?.find((t: Any) => t.decision === "denied");
  const inc = view?.active_incident ?? null;
  const incRow = view?.incidents?.find((i: Any) => i.rule_id === "CROSS_CITIZEN_ACCESS");
  const insuranceStep = view?.steps?.find((s: Any) => s.key === "insurance_verified");
  return (
    <div className="space-y-5">
      {!denied && (
        <section className="card p-5">
          <RoleTag role="citizen" />
          <p className="mt-4 text-[16px] text-fg">This opens a <b>new case</b> for Mariam{ s1Case ? ` (separate from step 1's case ${s1Case})` : ""} and a case for another citizen, Omar.
            During Mariam's case, the Insurance Agent asks for the insurance record of a <b>different citizen (C-1003)</b>. It was only authorized for Mariam.</p>
          <div className="mt-5"><PrimaryButton onClick={run} busy={busy === "attack"} disabled={busy !== null} tone="deny" icon={ShieldX}>Run the unauthorized request</PrimaryButton></div>
          {loading && <Waiting text="Loading the case from WAKALA…" />}
          {view && !denied && <p className="mt-4 text-[15px] text-warn">WAKALA has not recorded a blocked request on this case. Check the details, or run the request again.</p>}
        </section>
      )}
      {denied && (
        <section className="rounded-2xl border-2 border-deny bg-ink-850 p-6 shadow-[var(--shadow-card)]">
          <p className="flex items-center gap-3 text-[30px] font-semibold text-deny"><ShieldX className="size-9" aria-hidden /> Unauthorized access blocked.</p>
          <p className="mt-2 max-w-[920px] text-[18px] leading-relaxed text-fg">
            The {denied.agent_name} was authorized to check {view!.citizen_name?.split(" ")[0] ?? "the applicant"}'s insurance, but attempted to access a different citizen's record.
          </p>
          <p className="mt-1 text-[15px] text-fg-muted">WAKALA's explanation: “{denied.plain_english}”</p>
          <dl className="mt-5 grid gap-3 sm:grid-cols-2 lg:grid-cols-5">
            <Fact label="Attempted action" value={`${denied.agent_name}: ${ACTION_LABEL[denied.tool_name] ?? denied.tool_name}`} />
            <Fact label="Authorization decision" value="Denied by the gateway" tone="deny" />
            <Fact label="Executed?" value={insuranceStep && insuranceStep.status !== "done" ? "No — stopped before execution" : "No — denied before execution"} tone="trust" />
            <Fact label="Protected data returned?" value="None — the request never reached the insurance service" tone="trust" />
            <Fact label="Incident" value={inc ? `${inc.severity?.toUpperCase()} · ${inc.status}` : incRow ? `${incRow.severity?.toUpperCase()} · ${incRow.status}` : "Not recorded yet"} tone="warn" />
          </dl>
          <p className="mt-5 text-[16px] text-fg">Mariam's case is now <CaseStatus view={view!} />. Nothing was charged. Only an authenticated security officer can continue it.</p>
          <p className="mt-3 rounded-lg bg-navy-soft px-3.5 py-2.5 text-[15px] font-medium text-navy">Next: a security officer reviews the incident. Click “Next step”.</p>
          <TechDetails>
            <p>case {view!.case_id} · gateway event {denied.event_id} · mandate {denied.mandate_id}</p>
            <p>reason codes: {denied.reason_codes.join(", ")}</p>
            {inc && <p>incident {inc.incident_id} · rule {inc.rule_id} · {inc.summary}</p>}
            {inc?.responses?.filter((r: Any) => r.applied).map((r: Any, k: number) => <p key={k}>response {r.action} · {r.detail}</p>)}
            <p>“Executed” and “data returned” follow from the gateway decision: a denied request is never dispatched to the protected service (enforced and tested in the backend).</p>
          </TechDetails>
        </section>
      )}
      {denied && (
        <div className="flex flex-wrap items-center gap-3">
          <button onClick={run} disabled={busy !== null} className="text-[14px] text-fg-muted underline-offset-2 hover:underline">Run it again on a new case</button>
        </div>
      )}
    </div>
  );
}

function Fact({ label, value, tone }: { label: string; value: string; tone?: "deny" | "trust" | "warn" }) {
  return (
    <div className="rounded-xl border border-line bg-ink-800/60 p-3.5">
      <dt className="text-[12.5px] font-semibold uppercase tracking-wider text-fg-subtle">{label}</dt>
      <dd className={clsx("mt-1 text-[16px] font-semibold", tone === "deny" ? "text-deny" : tone === "trust" ? "text-trust" : tone === "warn" ? "text-warn" : "text-fg")}>{value}</dd>
    </div>
  );
}

function OfficerIntervention({ inv, view, incStatus, badAgent, reassigned, busy, error, can, act }:
  { inv: Any | null; view: Any; incStatus: string | null; badAgent: string | null; reassigned: boolean; busy: string | null; error: string | null;
    can: (p: string) => boolean; act: (key: string, fn: () => Promise<unknown>) => void }) {
  if (error) return <p role="alert" className="rounded-lg bg-deny-soft px-3 py-2 text-[14.5px] text-deny">{error}</p>;
  if (!inv) return <Waiting text="Loading the incident…" />;
  const i = inv.incident;
  const caseId = view.case_id;
  const tasks: Record<string, string[]> = inv.reassignable_tasks ?? {};
  const options = Object.entries(tasks).flatMap(([task, rs]) => rs.filter((r) => r !== view.task_assignments?.[task] && r !== badAgent).map((r) => ({ task, r })));
  const opt = options[0];
  const chain: Any[] = inv.authority_graph?.nodes?.filter((n: Any) => n.kind === "mandate") ?? [];
  const paused = view.state === "PAUSED_FOR_REVIEW";
  const tasksList: Task[] = [
    { key: "review", who: "officer", title: "Open the investigation", icon: ClipboardCheck, button: "Mark incident under review",
      why: "Records that an officer is now responsible for this incident.",
      done: incStatus !== "open", ready: can("incidents.update"), blockedReason: "This officer cannot update incidents.",
      onClick: () => act("review", () => officerRequest(`/api/officer/incidents/${i.incident_id}/status`, "POST", { status: "under_review", note: "investigating (guided demo)" })) },
    { key: "reassign", who: "officer", title: "Replace only the agent that overstepped", icon: UserCog,
      button: opt ? `Reassign the insurance check to ${opt.r} (standby)` : "Reassign",
      why: "The other agents keep their authority. Only the misbehaving agent's delegated task moves to a standby agent.",
      done: reassigned, ready: incStatus !== "open" && !!opt && can("cases.reassign"),
      blockedReason: !opt ? "No standby agent is available for this task." : !can("cases.reassign") ? "This officer cannot reassign tasks." : "Mark the incident under review first.",
      onClick: () => act("reassign", () => officerRequest(`/api/officer/cases/${caseId}/reassign`, "POST", { task: opt!.task, receiving_agent_id: opt!.r, note: `replace ${badAgent} (guided demo)` })) },
    { key: "resume", who: "officer", title: "Resume the citizen's case", icon: Play, button: "Resume Mariam's case",
      why: "Lets the service continue. Sensitive steps will still need officer approval while the incident is open.",
      done: !paused && reassigned, ready: reassigned && paused && can("cases.resume"), blockedReason: !can("cases.resume") ? "This officer cannot resume cases." : "Reassign the task first.",
      onClick: () => act("resume", () => officerRequest(`/api/officer/cases/${caseId}/resume`, "POST", { note: "review complete; affected authority contained (guided demo)" })) },
  ];
  return (
    <div>
      <div className="rounded-xl border border-deny/30 bg-deny-soft p-4">
        <p className="text-[16px] font-semibold text-fg">{i.title}</p>
        <p className="mt-0.5 text-[14.5px] text-fg-muted">{i.summary} · agent {i.agent_id} · severity {i.severity} · status <b>{i.status.replace("_", " ")}</b></p>
        <p className="mt-1 text-[14.5px] text-fg">{i.interpretation}</p>
      </div>
      <div className="mt-4"><Checklist tasks={tasksList} busy={busy} showRoles={false} /></div>
      {tasksList.every((t) => t.done) && <p className="mt-4 rounded-lg bg-trust-soft px-3.5 py-2.5 text-[15px] text-trust">Intervention complete. Next: continue Mariam's service. Click “Next step”.</p>}
      <TechDetails label="Technical details: delegated authority and evidence">
        <p>incident {i.incident_id} · rule {i.rule_id} · violated {inv.violated_rules?.join(", ")}</p>
        {chain.map((n: Any) => <p key={n.id}>{n.status.toUpperCase()} · {n.label} · {n.sublabel}</p>)}
        {i.responses?.map((r: Any, k: number) => <p key={k}>{r.applied ? "applied" : "available"} · {r.action} · {r.detail}</p>)}
        <p>The full investigation is in <Link to="/soc" className="text-trust underline">Security Operations</Link>.</p>
      </TechDetails>
    </div>
  );
}

function SceneRecovery({ view, other, officer, busy, s3Done, incStatus, approval, approvedOk, continueMariam, continueOther, approve, resolve, goSignIn }:
  { view: Any; other: Any | null; officer: Any | null; busy: string | null; s3Done: boolean; incStatus: string | null; approval: Any | null; approvedOk: boolean;
    continueMariam: (key: string) => void; continueOther: () => void; approve: () => void; resolve: () => void; goSignIn: () => void }) {
  const completed = view.state === "COMPLETED";
  const held = (view.pending_approvals?.length ?? 0) > 0 || !!approval;
  const tasks: Task[] = [
    { key: "cont1", who: "citizen", title: "Mariam continues her application", icon: ArrowRight, button: "Continue Mariam's renewal",
      why: "The Residency Agent tries to hand the insurance check to the standby agent. Because the incident is still open, WAKALA holds this step for an officer.",
      done: held || completed, ready: s3Done, blockedReason: "Finish the officer intervention in step 3 first.", onClick: () => continueMariam("cont1") },
    { key: "approve", who: "officer", title: "Officer approves the held step", icon: BadgeCheck, button: "Approve & re-authorize",
      why: "WAKALA re-checks the original signed request against the current rules before it runs. Approval cannot widen the agent's authority.",
      done: approvedOk || completed, ready: !!officer && approval?.status === "pending",
      blockedReason: !officer ? "Sign in as an officer (step 3) to approve." : "Waiting for the held step to appear.", onClick: approve },
    { key: "resolve", who: "officer", title: "Officer resolves the incident", icon: ShieldCheck, button: "Resolve incident",
      why: "Closes the incident now that the affected authority is contained.",
      done: incStatus === "resolved" || completed, ready: !!officer && approvedOk, blockedReason: !officer ? "Sign in as an officer (step 3)." : "Approve the held step first.", onClick: resolve },
    { key: "cont2", who: "citizen", title: "Mariam's service finishes", icon: ArrowRight, button: "Continue Mariam's renewal",
      why: "The standby Insurance Agent checks insurance, the fee is paid and the renewal completes — each step checked by WAKALA.",
      done: completed, ready: incStatus === "resolved", blockedReason: "Resolve the incident first.", onClick: () => continueMariam("cont2") },
  ];
  return (
    <div className="grid gap-5 lg:grid-cols-[minmax(0,5fr)_minmax(0,7fr)]">
      <div className="space-y-5">
        <CitizenCard view={view}><div className="mt-4"><Progress steps={view.steps} /></div><LatestRun view={view} /></CitizenCard>
        {other && (
          <section className="card p-5">
            <p className="eyebrow">Another citizen, same time</p>
            <p className="mt-2 text-[16px] text-fg">{other.citizen_name} ({other.citizen_ref}) · <CaseStatus view={other} /></p>
            <p className="mt-1 text-[14.5px] text-fg-muted">Omar's case was opened alongside Mariam's. The incident did not pause it.</p>
            {other.state !== "COMPLETED" && (
              <button onClick={continueOther} disabled={busy !== null} className="mt-3 inline-flex items-center gap-1.5 rounded-lg border border-trust/50 px-3.5 py-2 text-[14.5px] font-medium text-trust hover:bg-trust-soft disabled:opacity-40">
                {busy === "other" && <Loader2 className="size-4 animate-spin" />} Continue Omar's case
              </button>
            )}
          </section>
        )}
      </div>
      <section className="card p-5">
        <p className="flex flex-wrap items-center gap-2 text-[15px] text-fg-muted"><RoleTag role="citizen" /> and <RoleTag role="officer" /> take turns, in the order WAKALA requires.</p>
        {!officer && !completed && <p className="mt-3 rounded-lg bg-warn-soft px-3.5 py-2.5 text-[15px] text-warn">An officer must be signed in for this step. <button onClick={goSignIn} className="font-semibold underline">Sign in on step 3</button></p>}
        <div className="mt-4"><Checklist tasks={tasks} busy={busy} /></div>
        {completed && view.recovery_status === "recovered" && <p className="mt-4 rounded-lg bg-trust-soft px-3.5 py-2.5 text-[16px] font-semibold text-trust">Mariam's renewal completed, recovered after a security review. Click “Next step” for the results.</p>}
        <TechDetails>
          {approval && <p>approval {approval.approval_id} · {approval.status} · {approval.tool_name} · re-authorization {approval.reauthorization_codes?.join(", ") || "—"} · execution {approval.execution_status ?? "—"}</p>}
          {view.timeline.slice(-5).map((t: Any) => <p key={t.event_id}>{t.event_id} · {t.agent_id} · {t.tool_name} · {t.decision}</p>)}
        </TechDetails>
      </section>
    </div>
  );
}

function SceneResults({ view, other, s1, evidence, recovered, openReceipt }:
  { view: Any; other: Any | null; s1: Any | null; evidence: Any | null; recovered: boolean; openReceipt: (id: string) => void }) {
  const standby = view.timeline.filter((t: Any) => t.agent_id === "AGT-INS-002" && t.decision === "allowed");
  const C = evidence?.configurations?.C;
  const A = evidence?.configurations?.A;
  const frac = (x: Any) => (x ? `${x.numerator} / ${x.denominator}` : "—");
  return (
    <div className="space-y-5">
      {!recovered && <p className="rounded-xl border border-warn/40 bg-warn-soft p-4 text-[15px] text-warn">Mariam's case has not finished recovery yet, so the results below are still in progress.</p>}
      <div className="grid gap-4 md:grid-cols-3">
        <ResultCard icon={Building2} title="Mariam's case" ok={recovered}>
          <CaseStatus view={view} /><span className="block font-mono text-[12.5px] text-fg-subtle">{view.case_id}</span>
        </ResultCard>
        <ResultCard icon={UserCog} title="Replacement agent" ok={standby.length > 0}>
          {standby.length ? <>The standby Insurance Agent completed the task: “{standby[0].plain_english}”</> : "No action by the standby agent recorded yet."}
        </ResultCard>
        <ResultCard icon={UserRound} title="Unrelated citizen" ok={other?.state === "COMPLETED"}>
          {other ? <>{other.citizen_name}: <CaseStatus view={other} /></> : "Not available."}
        </ResultCard>
      </div>
      <section className="card p-5">
        <p className="text-[17px] font-semibold text-fg">See it from the citizen's side</p>
        <p className="mt-1 text-[15px] text-fg-muted">A privacy-filtered receipt of what each AI agent did, generated from the audit trail. Other citizens' details and officer identities are removed.</p>
        <div className="mt-3 flex flex-wrap gap-2">
          <PrimaryButton onClick={() => openReceipt(view.case_id)} icon={ReceiptText}>Open Mariam's AI Activity receipt</PrimaryButton>
          {s1?.state === "COMPLETED" && <button onClick={() => openReceipt(s1.case_id)} className="rounded-xl border border-line-strong px-4 py-3 text-[15px] text-fg-muted hover:bg-ink-800">Receipt for the normal case (step 1)</button>}
        </div>
      </section>
      <section className="card p-5">
        <p className="text-[17px] font-semibold text-fg">Security evidence <span className="ml-2 align-middle text-[12px] font-medium uppercase tracking-wider text-gold-strong">synthetic benchmark</span></p>
        {!evidence ? <Waiting text="Loading the benchmark results…" /> : (
          <dl className="mt-3 grid gap-3 sm:grid-cols-3">
            <Fact label="Requests tested" value={String(evidence.dataset?.total_requests ?? "—")} />
            <Fact label="Unauthorized executed · WAKALA" value={frac(C?.unauthorized_operations_executed)} tone="trust" />
            <Fact label="Unauthorized executed · weak baseline" value={frac(A?.unauthorized_operations_executed)} tone="deny" />
          </dl>
        )}
        <p className="mt-2 text-[13.5px] text-fg-subtle">Labelled synthetic requests run on a single developer machine; not production government statistics.</p>
        <div className="mt-4 flex flex-wrap gap-2 text-[15px]">
          <Link to="/evidence" className="inline-flex items-center gap-1.5 rounded-lg border border-line-strong px-3.5 py-2 font-medium text-navy hover:bg-ink-800">Full security evidence <ExternalLink className="size-4" /></Link>
          <Link to={`/delegation?case=${view.case_id}`} className="inline-flex items-center gap-1.5 rounded-lg border border-line-strong px-3.5 py-2 font-medium text-navy hover:bg-ink-800">Who was authorized (Case View) <ExternalLink className="size-4" /></Link>
          <Link to="/attack-lab" className="inline-flex items-center gap-1.5 rounded-lg border border-line-strong px-3.5 py-2 font-medium text-navy hover:bg-ink-800">Try 8 attacks (Attack Lab) <ExternalLink className="size-4" /></Link>
        </div>
      </section>
    </div>
  );
}

function ResultCard({ icon: Icon, title, ok, children }: { icon: LucideIcon; title: string; ok: boolean; children: ReactNode }) {
  return (
    <section className={clsx("card p-5", ok ? "border-trust/40" : "")}>
      <p className="flex items-center gap-2 text-[15px] font-semibold text-fg"><Icon className="size-5 text-navy" aria-hidden /> {title}
        {ok ? <CheckCircle2 className="ml-auto size-5 text-trust" aria-label="confirmed" /> : <Circle className="ml-auto size-5 text-fg-subtle" aria-label="not yet" />}</p>
      <div className="mt-2 text-[15px] leading-relaxed text-fg">{children}</div>
    </section>
  );
}

