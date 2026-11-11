/* eslint-disable @typescript-eslint/no-explicit-any */
/**
 * Judge experience: one connected story on one screen.
 *
 * Every state on this page is read from the running backend and every button calls the same endpoint the Government
 * AI Portal and the officer console call (no browser-side simulation):
 *   demo session ........ GET  /api/portal/demo, POST /api/portal/demo/reset
 *   stage 1 ............. POST /api/portal/requests            → GET /api/portal/cases/{id}
 *   stage 2 ............. POST /api/portal/scenes/incident     → GET /api/portal/cases/{id}
 *   map lanes ........... GET  /api/workflow/cases/{id}/case-view
 *   stage 3 / 4 officer . POST /api/officer/session, GET /api/officer/incidents/{id}, GET /api/officer/approvals,
 *                         POST /api/officer/incidents/{id}/status, /cases/{id}/reassign, /cases/{id}/resume,
 *                         /approvals/{id}/approve
 *   stage 4 citizen ..... POST /api/portal/cases/{id}/continue
 * Officer actions require a real officer session; nothing is skipped or auto-approved.
 */
import clsx from "clsx";
import {
  AlertTriangle, ArrowRight, BadgeCheck, BarChart3, Bot, Check, ChevronDown, Circle, ClipboardCheck, Compass, Eye, FilePen,
  FileSearch, KeyRound, LayoutDashboard, Loader2, LogOut, Network, Play, RotateCcw, ShieldAlert, ShieldCheck, ShieldX, Swords,
  UserCog, Wrench, X, type LucideIcon,
} from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { Link } from "react-router-dom";
import { AuthorityMap, AGENT, buildAuthorityMap } from "@/components/AuthorityMap";
import { BrandMark } from "@/layouts/AppLayout";
import { ApiError, apiGet, apiPost, hasOfficerToken, officerRequest, setOfficerToken } from "@/lib/api";

type Any = Record<string, any>;
const REQUEST_TEXT = "I want to renew my residency permit.";

// ------------------------------------------------------------------------------------------------ data
function usePoll<T>(path: string | null, ms: number) {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [n, setN] = useState(0);
  useEffect(() => {
    if (!path) { setData(null); setError(null); return; }
    let live = true;
    const tick = () => apiGet<T>(path).then((d) => { if (live) { setData(d); setError(null); } }).catch((e) => live && setError(plain(e)));
    tick();
    const id = setInterval(tick, ms);
    return () => { live = false; clearInterval(id); };
  }, [path, ms, n]);
  return { data, error, reload: useCallback(() => setN((x) => x + 1), []) };
}

/** Genuine backend errors, in plain language (the code is kept for experts). */
function plain(e: unknown): string {
  if (e instanceof ApiError) {
    if (e.status === 0) return "WAKALA's backend is not reachable. Check that it is running, then try again.";
    if (e.status === 401) return "The officer session is missing or has expired. Please sign in again.";
    if (e.status === 403) return `WAKALA refused this action for this user (${e.code}).`;
    if (e.status === 409) return `WAKALA refused this action in the current state (${e.code}).`;
    return `${e.message} (${e.code})`;
  }
  return String(e);
}

function useOfficer() {
  const [officer, setOfficer] = useState<Any | null>(null);
  const [checked, setChecked] = useState(false);
  const refresh = useCallback(() => {
    if (!hasOfficerToken()) { setOfficer(null); setChecked(true); return; }
    officerRequest<Any>("/api/officer/me").then(setOfficer).catch(() => setOfficer(null)).finally(() => setChecked(true));
  }, []);
  useEffect(refresh, [refresh]);
  return { officer, checked, setOfficer, refresh };
}

// ------------------------------------------------------------------------------------------------ small UI
function MainButton({ onClick, busy, disabled, children, tone = "trust", icon: Icon = ArrowRight, type = "button" }:
  { onClick?: () => void; busy?: boolean; disabled?: boolean; children: ReactNode; tone?: "trust" | "deny" | "navy"; icon?: LucideIcon; type?: "button" | "submit" }) {
  return (
    <button type={type} onClick={onClick} disabled={busy || disabled}
      className={clsx("inline-flex w-full items-center justify-center gap-2.5 rounded-xl px-5 py-3.5 text-[17px] font-semibold text-white shadow-[var(--shadow-card)] transition-colors disabled:cursor-not-allowed disabled:opacity-45",
        tone === "deny" ? "bg-deny hover:bg-deny/90" : tone === "navy" ? "bg-navy hover:bg-navy/90" : "bg-trust hover:bg-trust-strong")}>
      {busy ? <Loader2 className="size-5 animate-spin" aria-hidden /> : <Icon className="size-5" aria-hidden />}
      {children}
    </button>
  );
}

function Bridge({ children }: { children: ReactNode }) {
  return <p className="mt-3 border-l-[3px] border-gold pl-3 text-[15.5px] italic leading-snug text-fg">{children}</p>;
}

function Outcome({ tone, title, children }: { tone: "ok" | "deny" | "hold"; title: string; children?: ReactNode }) {
  const Icon = tone === "ok" ? ShieldCheck : tone === "deny" ? ShieldX : AlertTriangle;
  return (
    <div className={clsx("mt-3 rounded-xl border-2 p-3.5", tone === "ok" ? "border-trust/40 bg-trust-soft" : tone === "deny" ? "border-deny bg-deny-soft" : "border-warn/50 bg-warn-soft")}>
      <p className={clsx("flex items-start gap-2.5 text-[18px] font-semibold leading-snug", tone === "ok" ? "text-trust" : tone === "deny" ? "text-deny" : "text-warn")}>
        <Icon className="mt-0.5 size-6 shrink-0" aria-hidden />{title}
      </p>
      {children && <div className="mt-2 text-[14.5px] leading-snug text-fg">{children}</div>}
    </div>
  );
}

function MiniSteps({ steps }: { steps: { label: string; done: boolean }[] }) {
  const next = steps.findIndex((s) => !s.done);
  return (
    <ol className="mt-4 flex flex-wrap gap-1.5" aria-label="Actions in this stage">
      {steps.map((s, i) => (
        <li key={s.label} className={clsx("inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-[12.5px] font-medium",
          s.done ? "border-trust/30 bg-trust-soft text-trust" : i === next ? "border-navy/40 bg-navy-soft text-navy" : "border-line text-fg-subtle")}>
          {s.done ? <Check className="size-3.5" aria-hidden /> : <Circle className="size-3" aria-hidden />}{s.label}
        </li>
      ))}
    </ol>
  );
}

function ErrorNote({ failure, onDismiss }: { failure: { label: string; message: string; retry: () => void } | null; onDismiss: () => void }) {
  if (!failure) return null;
  return (
    <div role="alert" className="mt-4 rounded-xl border border-deny/40 bg-deny-soft p-3.5 text-[14.5px]">
      <p className="font-semibold text-deny">“{failure.label}” did not complete</p>
      <p className="mt-0.5 text-fg">{failure.message}</p>
      <div className="mt-2 flex gap-2">
        <button onClick={failure.retry} className="rounded-lg bg-deny px-3 py-1.5 text-[13.5px] font-semibold text-white">Try again</button>
        <button onClick={onDismiss} className="rounded-lg border border-line-strong px-3 py-1.5 text-[13.5px] text-fg-muted">Dismiss</button>
      </div>
    </div>
  );
}

const ADVANCED: { section: string; items: { to: string; label: string; note: string; icon: LucideIcon }[] }[] = [
  { section: "Explore the security features", items: [
    { to: "/soc", label: "Security Operations & Behaviour Watch", note: "Incidents, officer console, behaviour signals", icon: ShieldAlert },
    { to: "/attack-lab", label: "Attack Lab", note: "Eight attacks run against the real gateway", icon: Swords },
    { to: "/documents", label: "Document Shield", note: "Hidden-instruction detection in PDFs", icon: FileSearch },
    { to: "/delegation", label: "Delegation Network", note: "Full signed mandate chains", icon: Network },
    { to: "/shadow", label: "Shadow Mode", note: "Observe agents before enforcing", icon: Eye },
    { to: "/policies", label: "Policy Drafting", note: "AI-drafted, human-approved policies", icon: FilePen },
    { to: "/evidence", label: "Security Evidence", note: "Benchmark results (synthetic dataset)", icon: BarChart3 },
  ] },
  { section: "Consoles", items: [
    { to: "/command-center", label: "Full Security Console", note: "Every page, agent registry, mandates, audit", icon: LayoutDashboard },
    { to: "/portal", label: "Government AI Portal", note: "The citizen-side portal", icon: Bot },
    { to: "/demo/classic", label: "Step-by-step demo (detailed)", note: "The original five-scene walkthrough", icon: Compass },
  ] },
];

function AdvancedTools({ open, onClose }: { open: boolean; onClose: () => void }) {
  if (!open) return null;
  return (
    <div className="fixed inset-0 z-40 flex justify-end bg-[#1d304033]" onClick={onClose}>
      <aside className="h-full w-full max-w-[420px] overflow-y-auto bg-ink-850 p-5 shadow-2xl" onClick={(e) => e.stopPropagation()} aria-label="Advanced tools">
        <div className="flex items-center justify-between">
          <p className="text-[18px] font-semibold text-navy">Advanced tools</p>
          <button onClick={onClose} className="rounded-lg p-2 text-fg-muted hover:bg-ink-800" aria-label="Close"><X className="size-5" /></button>
        </div>
        <p className="mt-1 text-[13.5px] text-fg-muted">Every feature of the prototype remains available here.</p>
        {ADVANCED.map((g) => (
          <div key={g.section} className="mt-5">
            <p className="eyebrow mb-2">{g.section}</p>
            <ul className="space-y-1.5">
              {g.items.map((i) => (
                <li key={i.to}>
                  <Link to={i.to} className="flex items-center gap-3 rounded-xl border border-line px-3 py-2.5 hover:border-line-strong hover:bg-ink-800">
                    <i.icon className="size-5 shrink-0 text-navy" aria-hidden />
                    <span className="min-w-0"><span className="block text-[14.5px] font-semibold text-fg">{i.label}</span><span className="block text-[12.5px] text-fg-muted">{i.note}</span></span>
                  </Link>
                </li>
              ))}
            </ul>
          </div>
        ))}
      </aside>
    </div>
  );
}

// ------------------------------------------------------------------------------------------------ page
const STAGES = ["Normal service", "Unauthorized access", "Officer intervention", "Safe recovery"];

export function JudgeExperience() {
  useEffect(() => { document.title = "WAKALA | وكالة — Autonomous AI. Accountable actions."; }, []);
  const demo = usePoll<Any>("/api/portal/demo", 4000);
  const ids = demo.data?.cases ?? {};
  const s1 = usePoll<Any>(ids.scene1?.case_id ? `/api/portal/cases/${ids.scene1.case_id}` : null, 2500);
  const s2 = usePoll<Any>(ids.scene2_mariam?.case_id ? `/api/portal/cases/${ids.scene2_mariam.case_id}` : null, 2500);
  const other = usePoll<Any>(ids.scene2_unrelated?.case_id ? `/api/portal/cases/${ids.scene2_unrelated.case_id}` : null, 4000);
  const off = useOfficer();
  const [advOpen, setAdvOpen] = useState(false);

  // officer reads for the security-test case
  const v2 = s2.data;
  const incidentId: string | null = v2?.active_incident?.incident_id ?? v2?.incidents?.find((i: Any) => i.rule_id === "CROSS_CITIZEN_ACCESS")?.incident_id ?? null;
  const [inv, setInv] = useState<Any | null>(null);
  const [approvals, setApprovals] = useState<Any[]>([]);
  const [officerErr, setOfficerErr] = useState<string | null>(null);
  const loadOfficer = useCallback(async () => {
    if (!off.officer || !incidentId || !v2) return;
    try {
      const [i, a] = await Promise.all([officerRequest<Any>(`/api/officer/incidents/${incidentId}`), officerRequest<Any[]>("/api/officer/approvals")]);
      setInv(i); setApprovals(a.filter((x) => x.case_id === v2.case_id)); setOfficerErr(null);
    } catch (e) {
      setOfficerErr(plain(e));
      if (e instanceof ApiError && e.status === 401) off.refresh();
    }
  }, [off.officer, incidentId, v2?.case_id, v2?.state, v2?.pending_approvals?.length]); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => { void loadOfficer(); const id = setInterval(() => void loadOfficer(), 4000); return () => clearInterval(id); }, [loadOfficer]);

  // action runner: busy + genuine error + retry; always re-reads backend state afterwards
  const [busy, setBusy] = useState<string | null>(null);
  const [failure, setFailure] = useState<{ label: string; message: string; retry: () => void } | null>(null);
  const reloadAll = useCallback(() => { demo.reload(); s1.reload(); s2.reload(); other.reload(); void loadOfficer(); }, [demo.reload, s1.reload, s2.reload, other.reload, loadOfficer]); // eslint-disable-line react-hooks/exhaustive-deps
  const run = useCallback(async (label: string, fn: () => Promise<unknown>): Promise<boolean> => {
    setBusy(label); setFailure(null);
    try { await fn(); return true; }
    catch (e) { setFailure({ label, message: plain(e), retry: () => void run(label, fn) }); if (e instanceof ApiError && e.status === 401) off.refresh(); return false; }
    finally { setBusy(null); reloadAll(); }
  }, [reloadAll]); // eslint-disable-line react-hooks/exhaustive-deps

  // ---- progress, derived only from backend records
  const s1v = s1.data;
  const s1Done = s1v?.state === "COMPLETED";
  const denied = v2?.timeline?.find((t: Any) => t.decision === "denied") ?? null;
  const incStatus: string | null = inv?.incident?.status ?? v2?.incidents?.find((i: Any) => i.incident_id === incidentId)?.status ?? null;
  const badAgent: string | null = inv?.incident?.agent_id ?? denied?.agent_id ?? null;
  const reassigned = !!v2 && Object.values(v2.task_assignments ?? {}).some((a) => a !== badAgent);
  const paused = v2?.state === "PAUSED_FOR_REVIEW";
  const reviewed = !!incStatus && incStatus !== "open";
  const resumed = reassigned && !!v2 && !paused;
  const v2Done = v2?.state === "COMPLETED";
  const recovered = v2Done && v2?.recovery_status === "recovered";
  const pendingApproval = approvals.find((a) => a.status === "pending") ?? null;
  const heldNow = (v2?.pending_approvals?.length ?? 0) > 0 || !!pendingApproval;
  const approvedOk = approvals.some((a) => String(a.status).startsWith("approved")) || v2Done;
  const everHeld = heldNow || approvedOk || !!v2?.timeline?.some((t: Any) => t.decision === "escalated");
  const resolved = incStatus === "resolved" || incStatus === "closed";
  const standbyDone = v2?.timeline?.some((t: Any) => t.agent_id === AGENT.sb && t.decision === "allowed" && String(t.tool_name).startsWith("insurance.")) ?? false;

  const progress = !s1Done ? 1 : !denied ? 2 : !resumed ? 3 : 4;
  // The stage is chosen once from backend progress (so a reload lands in the right place) and afterwards only moves
  // when the visitor presses a Next button, so each result and its explanation stay on screen.
  const [stage, setStage] = useState<number | null>(() => {
    const q = Number(new URLSearchParams(window.location.search).get("stage"));
    return q >= 1 && q <= 4 ? q : null; // optional deep link for the presenter, e.g. /?stage=2
  });
  const loaded = !!demo.data && (!ids.scene1 || !!s1.data) && (!ids.scene2_mariam || !!s2.data);
  useEffect(() => { if (stage === null && loaded) setStage(progress); }, [stage, loaded, progress]);
  const current = stage ?? progress;
  useEffect(() => setFailure(null), [current]);

  // which case the map shows
  const [mapCase, setMapCase] = useState<"normal" | "test" | "other" | null>(null);
  const mapKey = mapCase ?? (current === 1 ? "normal" : "test");
  const mapPortal = mapKey === "normal" ? s1v : mapKey === "test" ? v2 : other.data;
  const cv = usePoll<Any>(mapPortal?.case_id ? `/api/workflow/cases/${mapPortal.case_id}/case-view` : null, 3000);
  const cvData = cv.data?.case_id === mapPortal?.case_id ? cv.data : null;
  const model = useMemo(() => buildAuthorityMap(mapPortal ?? null, cvData, { showStandby: mapKey === "test" }), [mapPortal, cvData, mapKey]);
  useEffect(() => { setMapCase(null); }, [current]);
  const [selected, setSelected] = useState<string | null>(null);
  const techRef = useRef<HTMLDetailsElement>(null);
  const select = (id: string) => { setSelected(id); if (techRef.current) techRef.current.open = true; };

  const restart = () => run("Restart guided demo", async () => {
    await apiPost("/api/portal/demo/reset"); setStage(1); setInv(null); setApprovals([]); setSelected(null);
  });
  const signOut = async () => { try { await officerRequest("/api/officer/session", "DELETE"); } catch { /* already expired */ } setOfficerToken(null); off.setOfficer(null); };
  const can = (p: string) => (off.officer?.permissions ?? []).includes(p);

  const tabs: { key: "normal" | "test" | "other"; label: string; show: boolean }[] = [
    { key: "normal", label: "Normal case", show: !!s1v },
    { key: "test", label: "Security test", show: !!v2 },
    { key: "other", label: `${other.data?.citizen_name?.split(" ")[0] ?? "Omar"} (unrelated)`, show: !!other.data && current === 4 },
  ];
  const visibleTabs = tabs.filter((t) => t.show);
  const caseState = mapPortal?.state as string | undefined;
  const stageNav = (
    <nav aria-label="Demo stages">
            <ol className="flex flex-wrap gap-1.5">
              {STAGES.map((s, i) => {
                const n = i + 1;
                const done = n < progress || (n === 4 && recovered);
                const active = n === current;
                return (
                  <li key={s}>
                    <button onClick={() => setStage(n)} aria-current={active ? "step" : undefined}
                      className={clsx("inline-flex items-center gap-2 rounded-full border px-3 py-1.5 text-[13px] font-medium transition-colors",
                        active ? "border-navy bg-navy text-white" : done ? "border-trust/40 bg-trust-soft text-trust" : "border-line bg-ink-850 text-fg-subtle hover:text-fg")}>
                      <span className={clsx("flex size-5 items-center justify-center rounded-full text-[11px] font-bold", active ? "bg-white/20" : done ? "bg-trust text-white" : "bg-ink-750")}>{done && !active ? <Check className="size-3" /> : n}</span>{s}
                    </button>
                  </li>
                );
              })}
            </ol>
          </nav>
  );

  return (
    <div className="min-h-screen bg-ink-900">
      <header className="sticky top-0 z-30 border-b border-line bg-ink-850/95 backdrop-blur">
        <div className="mx-auto flex max-w-[1600px] items-center justify-between gap-3 px-4 py-2.5 sm:px-6">
          <div className="flex min-w-0 items-center gap-3">
            <BrandMark />
            <div className="min-w-0">
              <p className="flex items-baseline gap-2 text-[17px] font-semibold tracking-[0.08em] text-navy">WAKALA <span lang="ar" className="hidden tracking-normal text-gold sm:inline">وكالة</span></p>
              <p className="hidden truncate text-[12.5px] text-fg-muted sm:block">Autonomous AI. Accountable Actions.</p>
            </div>
          </div>
          <div className="flex shrink-0 items-center gap-2">
            <span className="hidden whitespace-nowrap rounded-full border border-gold/40 bg-gold-soft px-3 py-1 text-[12.5px] font-medium text-gold-strong lg:inline">Demonstration environment · Fictional government services</span>
            <button onClick={restart} disabled={busy !== null} className="inline-flex items-center gap-1.5 rounded-lg border border-line-strong px-3 py-2 text-[13.5px] text-fg-muted hover:bg-ink-800 disabled:opacity-40" title="Start a new demo session. Earlier records stay in the audit history.">
              {busy === "Restart guided demo" ? <Loader2 className="size-4 animate-spin" /> : <RotateCcw className="size-4" aria-hidden />}<span className="hidden sm:inline">Restart</span>
            </button>
            <button onClick={() => setAdvOpen(true)} className="inline-flex items-center gap-1.5 whitespace-nowrap rounded-lg border border-navy/30 bg-navy-soft px-3 py-2 text-[13.5px] font-semibold text-navy hover:bg-navy/10">
              <LayoutDashboard className="size-4" aria-hidden /> <span className="sm:hidden">Tools</span><span className="hidden sm:inline">Advanced Tools</span>
            </button>
          </div>
        </div>
        <p className="border-t border-line bg-gold-soft px-4 py-1 text-center text-[12px] font-medium text-gold-strong lg:hidden">Demonstration environment · Fictional government services</p>
      </header>

      <main className="mx-auto max-w-[1600px] px-4 pb-10 pt-4 sm:px-6">
        {/* A. headline + compact stage strip */}
        <div className="min-w-0">
          <h1 className="text-[24px] font-semibold leading-tight tracking-tight text-navy sm:text-[27px]">AI agents can act for government. WAKALA makes sure they only do what they are authorized to do.</h1>
          <p className="mt-1 text-[15px] text-fg-muted">Every protected action is checked against a signed, case-bound mandate before it runs, and a human officer stays accountable.</p>
        </div>
        <div className="mt-3">{stageNav}</div>

        {demo.error && <p role="alert" className="mt-4 rounded-xl border border-deny/40 bg-deny-soft p-3.5 text-[15px] text-deny">{demo.error}</p>}

        <div className="mt-4 grid gap-5 xl:grid-cols-[minmax(0,1fr)_400px]">
          {/* B. the live authority map */}
          <section className="card min-w-0 p-4 sm:p-5" aria-labelledby="map-title">
            <AuthorityMap model={model} selected={selected} onSelect={select} header={
              <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
                <div className="flex items-center gap-2.5">
                  <span className="relative flex size-2.5"><span className="absolute inline-flex size-full rounded-full bg-trust opacity-40" /><span className="relative inline-flex size-2.5 rounded-full bg-trust" /></span>
                  <h2 id="map-title" className="whitespace-nowrap text-[17px] font-semibold text-navy">Live Authority Map</h2>
                  <span className="hidden text-[13px] text-fg-muted sm:inline">{mapPortal ? `${mapPortal.citizen_name?.split(" ")[0]}'s residency renewal${mapKey === "test" ? " · security-test case" : mapKey === "other" ? " · unrelated case" : ""}` : mapKey === "test" ? "new security-test case · not started" : "waiting for the first request"}</span>
                </div>
                {visibleTabs.length > 1 && (
                  <div className="flex flex-wrap gap-1 rounded-lg bg-ink-800 p-1" role="tablist" aria-label="Case shown on the map">
                    {visibleTabs.map((t) => (
                      <button key={t.key} role="tab" aria-selected={mapKey === t.key} onClick={() => setMapCase(t.key)}
                        className={clsx("rounded-md px-2.5 py-1 text-[12.5px] font-medium", mapKey === t.key ? "bg-ink-850 text-navy shadow-sm" : "text-fg-muted hover:text-fg")}>{t.label}</button>
                    ))}
                  </div>
                )}
              </div>
            } />
            {/* E. compact status summary */}
            <dl className="mt-3 grid grid-cols-2 gap-2 border-t border-line pt-3 sm:grid-cols-4">
              <Stat label="Actions authorized" value={model.counts.allowed} tone="ok" />
              <Stat label="Attempts denied" value={model.counts.denied} tone="deny" />
              <Stat label="Held for an officer" value={model.counts.held} tone="hold" />
              <Stat label="Service status" value={!mapPortal ? "—" : caseState === "COMPLETED" ? (mapPortal.recovery_status === "recovered" ? "Recovered" : "Completed") : caseState === "PAUSED_FOR_REVIEW" ? "Paused" : caseState === "FAILED" ? "Failed" : "Active"}
                tone={caseState === "COMPLETED" ? "ok" : caseState === "PAUSED_FOR_REVIEW" ? "hold" : caseState === "FAILED" ? "deny" : "info"} />
            </dl>
          </section>

          {/* C + D. the current step and the one dominant action */}
          <section className="card order-first flex flex-col p-5 xl:order-none" aria-live="polite">
            <p className="eyebrow">Stage {current} of 4 · {STAGES[current - 1]}</p>
            {current === 1 && <StageNormal view={s1v} busy={busy} next={() => setStage(2)}
              start={() => run("Run Normal Service", () => apiPost("/api/portal/requests", { citizen_ref: "C-1001", message: REQUEST_TEXT, use_model: true }))} />}
            {current === 2 && <StageAttack view={v2} cv={mapKey === "test" ? cvData : null} busy={busy} next={() => setStage(3)} s1Done={s1Done}
              start={() => run("Test Unauthorized Request", () => apiPost("/api/portal/scenes/incident"))} />}
            {current === 3 && <StageOfficer insState={mapKey === "test" ? (cvData?.lanes?.find((l: Any) => l.agent_id === AGENT.ins)?.state ?? null) : null} view={v2} inv={inv} officer={off.officer} checked={off.checked} officerErr={officerErr} busy={busy}
              reviewed={reviewed} reassigned={reassigned} resumed={resumed} badAgent={badAgent} can={can} onSignedIn={off.setOfficer} signOut={signOut} next={() => setStage(4)}
              act={(label, fn) => void run(label, fn)} goBack={() => setStage(2)} />}
            {current === 4 && <StageRecovery view={v2} other={other.data} officer={off.officer} checked={off.checked} busy={busy} resumed={resumed}
              heldNow={heldNow} everHeld={everHeld} approvedOk={approvedOk} resolved={resolved} recovered={recovered} standbyDone={standbyDone} denied={!!denied}
              pendingApproval={pendingApproval} can={can} onSignedIn={off.setOfficer} signOut={signOut} restart={restart} openAdvanced={() => setAdvOpen(true)}
              showOther={() => setMapCase("other")}
              cont={(label) => void run(label, () => apiPost(`/api/portal/cases/${v2!.case_id}/continue`, { use_model: false }))}
              contOther={() => void run("Continue Omar's case", () => apiPost(`/api/portal/cases/${ids.scene2_unrelated.case_id}/continue`, { use_model: false }))}
              approve={() => void run("Approve held step", () => officerRequest(`/api/officer/approvals/${pendingApproval!.approval_id}/approve`, "POST", { note: "approved after review (judge demo)" }))}
              resolve={() => void run("Resolve incident", () => officerRequest(`/api/officer/incidents/${incidentId}/status`, "POST", { status: "resolved", note: "recovered via standby authority (judge demo)" }))}
              goBack={() => setStage(3)} />}
            <ErrorNote failure={failure} onDismiss={() => setFailure(null)} />
          </section>
        </div>

        {/* F. technical details, collapsed */}
        <details ref={techRef} className="group mt-5 rounded-xl border border-line bg-ink-850">
          <summary className="flex cursor-pointer list-none items-center gap-2 px-5 py-3 text-[14.5px] font-medium text-fg-muted hover:text-fg">
            <Wrench className="size-4" aria-hidden /> Technical details <span className="text-fg-subtle">— identities, signed mandates, gateway decisions and data sources</span>
            <ChevronDown className="ml-auto size-4 transition-transform group-open:rotate-180" aria-hidden />
          </summary>
          <TechPanel model={model} selected={selected} portal={mapPortal ?? null} ids={ids} />
        </details>
      </main>
      <AdvancedTools open={advOpen} onClose={() => setAdvOpen(false)} />
    </div>
  );
}

function Stat({ label, value, tone }: { label: string; value: ReactNode; tone: "ok" | "deny" | "hold" | "info" }) {
  return (
    <div className="flex items-baseline justify-between gap-2 rounded-lg bg-ink-800/70 px-3 py-1.5">
      <dt className="text-[11.5px] font-semibold uppercase tracking-wider text-fg-subtle">{label}</dt>
      <dd className={clsx("text-[20px] font-semibold leading-tight", tone === "ok" ? "text-trust" : tone === "deny" ? "text-deny" : tone === "hold" ? "text-warn" : "text-navy")}>{value}</dd>
    </div>
  );
}

function Headline({ title, text }: { title: string; text: string }) {
  return (
    <>
      <h2 className="mt-1.5 text-[22px] font-semibold leading-snug tracking-tight text-navy">{title}</h2>
      <p className="mt-1.5 text-[15px] leading-snug text-fg-muted">{text}</p>
    </>
  );
}

function Spacer() { return <div className="min-h-2 flex-1" />; }

// ------------------------------------------------------------------------------------------------ stage 1
function StageNormal({ view, busy, start, next }: { view: Any | null; busy: string | null; start: () => void; next: () => void }) {
  const done = view?.state === "COMPLETED";
  const allowed = view?.timeline?.filter((t: Any) => t.decision === "allowed").length ?? 0;
  const fee = view?.ledger?.[0];
  return (
    <>
      <Headline title="Mariam requests a residency renewal." text="The Residency Agent coordinates the service and delegates insurance verification. WAKALA verifies each protected action." />
      {!view && <p className="mt-4 rounded-lg bg-ink-800 px-3.5 py-2.5 text-[15px] text-fg">“{REQUEST_TEXT}”</p>}
      {view && !done && view.state !== "FAILED" && <p className="mt-4 flex items-center gap-2 text-[15px] text-fg-muted"><Loader2 className="size-4 animate-spin" /> Agents are working…</p>}
      {view?.state === "FAILED" && <Outcome tone="deny" title="The service could not be completed.">WAKALA recorded the case as failed. Open Technical details for the reason, then run it again.</Outcome>}
      {done && (
        <>
          <Outcome tone="ok" title="Authorized actions completed.">{allowed} agent actions verified and allowed{fee ? ` · AED ${Number(fee.amount).toFixed(0)} fee recorded` : ""}.</Outcome>
          <Bridge>But what if an agent requests information outside this citizen's case?</Bridge>
        </>
      )}
      <Spacer />
      <div className="mt-4">
        {done ? <MainButton onClick={next} tone="navy">Next: Unauthorized Request</MainButton>
          : <MainButton onClick={start} busy={busy === "Run Normal Service"} disabled={busy !== null || (!!view && view.state !== "FAILED")} icon={Play}>Run Normal Service</MainButton>}
      </div>
    </>
  );
}

// ------------------------------------------------------------------------------------------------ stage 2
function StageAttack({ view, cv, busy, start, next, s1Done }: { view: Any | null; cv: Any | null; busy: string | null; start: () => void; next: () => void; s1Done: boolean }) {
  const denied = view?.timeline?.find((t: Any) => t.decision === "denied") ?? null;
  const action = denied ? cv?.lanes?.flatMap((l: Any) => l.actions).find((a: Any) => a.technical?.event_id === denied.event_id) : null;
  const target: string | null = action?.technical?.target ?? null;
  const insuranceDone = view?.completed_prerequisites?.includes("insurance_verified");
  return (
    <>
      <Headline title="A legitimate agent requests the wrong citizen's record." text="The Insurance Agent is recognized, but this action exceeds Mariam's approved authority." />
      {!denied && (
        <p className="mt-3 rounded-lg bg-navy-soft px-3.5 py-2.5 text-[14px] text-navy">
          This test opens a <b>new case</b> for Mariam.{s1Done ? " The renewal from Stage 1 stays completed and untouched." : ""}
        </p>
      )}
      {view && !denied && <Outcome tone="hold" title="No denied request has been recorded on this case yet.">Check Technical details, or run the test again.</Outcome>}
      {denied && (
        <>
          <div className="mt-3 rounded-xl border-2 border-deny bg-deny-soft p-3.5">
            <p className="flex items-center gap-2.5 text-[15px] font-bold uppercase tracking-[0.14em] text-deny"><ShieldX className="size-6" aria-hidden /> Gateway decision: Deny</p>
            <p className="mt-1 text-[18px] font-semibold leading-snug text-deny">Unauthorized access blocked. No protected data returned.</p>
            <dl className="mt-2 grid grid-cols-[auto_1fr] gap-x-3 gap-y-1 text-[13.5px]">
              <dt className="text-fg-muted">Requested</dt><dd className="font-medium text-fg">Insurance record of {target ? `citizen ${target}` : "another citizen"} — not Mariam</dd>
              <dt className="text-fg-muted">Executed</dt><dd className="font-medium text-fg">No — stopped at the gateway{view?.state === "PAUSED_FOR_REVIEW" ? "; case paused for review" : ""}{insuranceDone ? "" : ", nothing charged"}</dd>
            </dl>
          </div>
          <Bridge>WAKALA blocked the operation. Now an authorized officer must review the affected workflow.</Bridge>
        </>
      )}
      <Spacer />
      <div className="mt-4">
        {denied ? <MainButton onClick={next} tone="navy">Next: Officer Review</MainButton>
          : <MainButton onClick={start} busy={busy === "Test Unauthorized Request"} disabled={busy !== null} tone="deny" icon={ShieldX}>Test Unauthorized Request</MainButton>}
      </div>
    </>
  );
}

// ------------------------------------------------------------------------------------------------ officer sign-in
function OfficerSignIn({ onSignedIn, compact }: { onSignedIn: (o: Any) => void; compact?: boolean }) {
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
      setErr(x instanceof ApiError && x.status === 401 ? "Officer ID or password is not correct." : plain(x));
    } finally { setBusy(false); }
  };
  return (
    <form onSubmit={submit} className="mt-4 rounded-xl border border-navy/25 bg-navy-soft p-4">
      <p className="flex items-center gap-2 text-[15px] font-semibold text-navy"><UserCog className="size-5" aria-hidden /> Officer sign-in required</p>
      {!compact && <p className="mt-1 text-[13.5px] text-fg-muted">Only an authenticated officer can intervene. The AI agents cannot.</p>}
      <div className="mt-3 grid grid-cols-[minmax(0,2fr)_minmax(0,3fr)] gap-2">
        <label className="text-[12.5px] text-fg-muted">Officer ID
          <input value={id} onChange={(e) => setId(e.target.value)} className="mt-1 w-full rounded-lg border border-line-strong bg-ink-850 px-2.5 py-2 font-mono text-[14px] text-fg" autoComplete="username" />
        </label>
        <label className="text-[12.5px] text-fg-muted">Password
          <input type="password" value={pw} onChange={(e) => setPw(e.target.value)} className="mt-1 w-full rounded-lg border border-line-strong bg-ink-850 px-2.5 py-2 text-[14px] text-fg" autoComplete="current-password" />
        </label>
      </div>
      {err && <p role="alert" className="mt-2 rounded-lg bg-deny-soft px-3 py-2 text-[13.5px] text-deny">{err}</p>}
      <div className="mt-3"><MainButton type="submit" busy={busy} disabled={!pw} tone="navy" icon={KeyRound}>Sign In as Officer</MainButton></div>
      <p className="mt-2 text-[12px] text-fg-subtle">The demo officer password is issued by the presenter. The browser never stores it.</p>
    </form>
  );
}

function OfficerBadge({ officer, signOut }: { officer: Any; signOut: () => void }) {
  return (
    <p className="mt-3 flex items-center gap-2 whitespace-nowrap text-[13px] text-fg-muted">
      <BadgeCheck className="size-4 shrink-0 text-navy" aria-hidden /><span className="truncate">Officer <b className="text-fg">{officer.name}</b> · <span className="font-mono">{officer.officer_id}</span></span>
      <button onClick={signOut} className="ml-auto inline-flex shrink-0 items-center gap-1 rounded-md px-2 py-1 hover:bg-ink-800"><LogOut className="size-3.5" /> Sign out</button>
    </p>
  );
}

// ------------------------------------------------------------------------------------------------ stage 3
function StageOfficer({ insState, view, inv, officer, checked, officerErr, busy, reviewed, reassigned, resumed, badAgent, can, onSignedIn, signOut, next, act, goBack }:
  { insState: string | null; view: Any | null; inv: Any | null; officer: Any | null; checked: boolean; officerErr: string | null; busy: string | null; reviewed: boolean; reassigned: boolean;
    resumed: boolean; badAgent: string | null; can: (p: string) => boolean; onSignedIn: (o: Any) => void; signOut: () => void; next: () => void;
    act: (label: string, fn: () => Promise<unknown>) => void; goBack: () => void }) {
  const head = <Headline title="Security is enforced. Now the service needs to recover." text="An authorized officer reviews the incident and assigns valid replacement authority." />;
  if (!view || !view.timeline?.some((t: Any) => t.decision === "denied")) {
    return <>{head}<Outcome tone="hold" title="There is no blocked request to review yet."><button onClick={goBack} className="font-semibold underline">Run Stage 2 first</button></Outcome></>;
  }
  const steps = [{ label: "Review incident", done: reviewed }, { label: "Assign replacement", done: reassigned }, { label: "Resume case", done: resumed }];
  const tasks: Record<string, string[]> = inv?.reassignable_tasks ?? {};
  const opt = Object.entries(tasks).flatMap(([task, rs]) => rs.filter((r) => r !== view.task_assignments?.[task] && r !== badAgent).map((r) => ({ task, r })))[0];
  const incidentId = inv?.incident?.incident_id;

  let action: ReactNode = null;
  let why = "";
  if (!checked) action = <p className="flex items-center gap-2 text-[14px] text-fg-muted"><Loader2 className="size-4 animate-spin" /> Checking officer session…</p>;
  else if (!officer) action = <OfficerSignIn onSignedIn={onSignedIn} />;
  else if (officerErr) action = <Outcome tone="deny" title="The officer console could not be read.">{officerErr}</Outcome>;
  else if (!inv) action = <p className="flex items-center gap-2 text-[14px] text-fg-muted"><Loader2 className="size-4 animate-spin" /> Loading the incident…</p>;
  else if (!reviewed) {
    why = "Take ownership of the incident, so the review is on the record.";
    action = <MainButton tone="navy" icon={ClipboardCheck} busy={busy === "Mark incident under review"} disabled={busy !== null || !can("incidents.update")}
      onClick={() => act("Mark incident under review", () => officerRequest(`/api/officer/incidents/${incidentId}/status`, "POST", { status: "under_review", note: "investigating (judge demo)" }))}>Mark Incident Under Review</MainButton>;
  } else if (!reassigned) {
    why = "Move only the insurance check to the standby Insurance Agent. The other agents keep their authority.";
    action = opt ? <MainButton tone="navy" icon={UserCog} busy={busy === "Assign standby agent"} disabled={busy !== null || !can("cases.reassign")}
      onClick={() => act("Assign standby agent", () => officerRequest(`/api/officer/cases/${view.case_id}/reassign`, "POST", { task: opt.task, receiving_agent_id: opt.r, note: `replace ${badAgent} (judge demo)` }))}>Assign Standby Insurance Agent</MainButton>
      : <Outcome tone="hold" title="No standby agent is available for this task." />;
  } else if (!resumed) {
    why = "Let Mariam's case continue. While the incident is open, sensitive steps still need officer approval.";
    action = <MainButton tone="navy" icon={Play} busy={busy === "Resume case"} disabled={busy !== null || !can("cases.resume")}
      onClick={() => act("Resume case", () => officerRequest(`/api/officer/cases/${view.case_id}/resume`, "POST", { note: "review complete; affected authority contained (judge demo)" }))}>Resume Mariam's Case</MainButton>;
  }
  const missingPerm = officer && inv && ((!reviewed && !can("incidents.update")) || (reviewed && !reassigned && !can("cases.reassign")) || (reassigned && !resumed && !can("cases.resume")));
  return (
    <>
      {head}
      <MiniSteps steps={steps} />
      {officer && <OfficerBadge officer={officer} signOut={signOut} />}
      {resumed ? (
        <>
          <Outcome tone="ok" title="Affected authority contained. Case resumed.">{insState === "suspended" || insState === "revoked" ? `The Insurance Agent's delegated authority is ${insState}. ` : ""}The insurance check is now assigned to the standby agent.</Outcome>
          <Bridge>Next, the citizen's service continues — under officer oversight.</Bridge>
        </>
      ) : why && <p className="mt-4 text-[15.5px] leading-snug text-fg">{why}</p>}
      {missingPerm && <p className="mt-2 text-[13.5px] text-deny">This officer's role does not permit this action. Sign in as a case officer.</p>}
      <Spacer />
      <div className="mt-4">{resumed ? <MainButton onClick={next} tone="navy">Next: Safe Recovery</MainButton> : action}</div>
    </>
  );
}

// ------------------------------------------------------------------------------------------------ stage 4
function StageRecovery(p: {
  view: Any | null; other: Any | null; officer: Any | null; checked: boolean; busy: string | null; resumed: boolean; heldNow: boolean; everHeld: boolean;
  approvedOk: boolean; resolved: boolean; recovered: boolean; standbyDone: boolean; denied: boolean; pendingApproval: Any | null; can: (p: string) => boolean;
  onSignedIn: (o: Any) => void; signOut: () => void; restart: () => void; openAdvanced: () => void; showOther: () => void; cont: (label: string) => void;
  contOther: () => void; approve: () => void; resolve: () => void; goBack: () => void;
}) {
  const { view, other, officer, busy } = p;
  const head = <Headline title="The legitimate government service continues." text="Mariam's agents resume. WAKALA holds the sensitive hand-off until the officer approves it." />;
  if (!view || !p.resumed) {
    return <>{head}<Outcome tone="hold" title="The officer has not resumed the case yet."><button onClick={p.goBack} className="font-semibold underline">Finish Stage 3 first</button></Outcome></>;
  }
  const completed = view.state === "COMPLETED";
  const steps = [{ label: "Continue service", done: p.everHeld || completed }, { label: "Officer approves", done: p.approvedOk }, { label: "Resolve incident", done: p.resolved || completed }, { label: "Service completes", done: completed }];

  if (p.recovered) {
    const otherOk = !!other && other.state !== "PAUSED_FOR_REVIEW" && other.state !== "FAILED" && !(other.incidents ?? []).length;
    const results: { ok: boolean; text: string; sub?: ReactNode }[] = [
      { ok: p.denied, text: "Unauthorized operation denied", sub: "Stopped at the gateway; never executed." },
      { ok: p.recovered, text: "Mariam's case recovered and completed" },
      { ok: p.standbyDone, text: "Replacement agent completed the insurance check", sub: p.standbyDone ? undefined : "Not recorded." },
      { ok: otherOk, text: `${other?.citizen_name?.split(" ")[0] ?? "Omar"}'s unrelated case unaffected`,
        sub: !other ? "Not available." : otherOk ? <>Never paused · {other.state === "COMPLETED" ? "completed" : other.state === "AWAITING_PAYMENT" ? "awaiting its fee" : "in progress"} · <button onClick={p.showOther} className="font-semibold text-navy underline-offset-2 hover:underline">Show on map</button></> : `Current state: ${other.state}` },
    ];
    return (
      <>
        <h2 className="mt-1.5 text-[22px] font-semibold leading-snug tracking-tight text-navy">The legitimate government service continues.</h2>
        <p className="mt-1 text-[14.5px] text-fg-muted">Confirmed by WAKALA's records:</p>
        <ul className="mt-3 space-y-1.5">
          {results.map((r) => (
            <li key={r.text} className={clsx("flex gap-2.5 rounded-lg border px-3 py-2", r.ok ? "border-trust/35 bg-trust-soft" : "border-line bg-ink-800")}>
              {r.ok ? <ShieldCheck className="mt-0.5 size-[18px] shrink-0 text-trust" aria-hidden /> : <Circle className="mt-0.5 size-[18px] shrink-0 text-fg-subtle" aria-hidden />}
              <span className="min-w-0"><span className="block text-[14.5px] font-semibold leading-snug text-fg">{r.text}</span>{r.sub && <span className="block text-[12.5px] leading-snug text-fg-muted">{r.sub}</span>}</span>
            </li>
          ))}
        </ul>
        {other && other.state !== "COMPLETED" && otherOk && (
          <button onClick={p.contOther} disabled={busy !== null} className="mt-2 inline-flex items-center gap-1.5 self-start text-[13.5px] font-medium text-trust hover:underline disabled:opacity-40">
            {busy === "Continue Omar's case" && <Loader2 className="size-4 animate-spin" />} Continue {other.citizen_name?.split(" ")[0]}'s case to completion
          </button>
        )}
        <Spacer />
        <div className="mt-3 grid gap-2">
          <Link to="/evidence" className="inline-flex w-full items-center justify-center gap-2.5 rounded-xl bg-trust px-5 py-3.5 text-[17px] font-semibold text-white shadow-[var(--shadow-card)] hover:bg-trust-strong"><BarChart3 className="size-5" aria-hidden /> View Technical Evidence</Link>
          <div className="grid grid-cols-2 gap-2">
            <button onClick={p.openAdvanced} className="inline-flex items-center justify-center gap-2 rounded-xl border border-navy/30 px-3 py-2.5 text-[14.5px] font-semibold text-navy hover:bg-navy-soft"><LayoutDashboard className="size-4" aria-hidden /> Explore Advanced Features</button>
            <button onClick={p.restart} disabled={busy !== null} className="inline-flex items-center justify-center gap-2 rounded-xl border border-line-strong px-3 py-2.5 text-[14.5px] font-semibold text-fg-muted hover:bg-ink-800 disabled:opacity-40"><RotateCcw className="size-4" aria-hidden /> Restart Guided Demo</button>
          </div>
        </div>
      </>
    );
  }

  let why = "";
  let action: ReactNode;
  const needOfficer = (label: string) => !p.checked ? <p className="flex items-center gap-2 text-[14px] text-fg-muted"><Loader2 className="size-4 animate-spin" /> Checking officer session…</p>
    : <><p className="text-[14px] text-fg-muted">{label}</p><OfficerSignIn onSignedIn={p.onSignedIn} compact /></>;
  if (!p.everHeld && !completed) {
    why = "Mariam's agents continue. While the incident is open, WAKALA requires officer approval before the hand-off to the standby agent.";
    action = <MainButton icon={ArrowRight} busy={busy === "Continue Mariam's service"} disabled={busy !== null} onClick={() => p.cont("Continue Mariam's service")}>Continue Mariam's Service</MainButton>;
  } else if (!p.approvedOk) {
    why = p.heldNow ? "On approval WAKALA re-checks the original signed request before it runs. Approval cannot widen authority." : "Waiting for WAKALA to record the held step.";
    action = !officer ? needOfficer("Approval needs an officer session.")
      : p.pendingApproval ? <MainButton tone="navy" icon={BadgeCheck} busy={busy === "Approve held step"} disabled={busy !== null || !p.can("approvals.decide")} onClick={p.approve}>Approve Held Step</MainButton>
      : <p className="flex items-center gap-2 text-[14px] text-fg-muted"><Loader2 className="size-4 animate-spin" /> Waiting for the held step to appear…</p>;
  } else if (!p.resolved) {
    why = "Approved and re-authorized. With the replacement authority in place, the officer closes the incident.";
    action = !officer ? needOfficer("Resolving needs an officer session.")
      : <MainButton tone="navy" icon={ShieldCheck} busy={busy === "Resolve incident"} disabled={busy !== null || !(p.can("incidents.update") || p.can("incidents.close"))} onClick={p.resolve}>Resolve Incident</MainButton>;
  } else {
    why = "The standby Insurance Agent checks insurance, the fee is paid and the renewal completes — each step verified by WAKALA.";
    action = <MainButton icon={ArrowRight} busy={busy === "Finish Mariam's renewal"} disabled={busy !== null} onClick={() => p.cont("Finish Mariam's renewal")}>Finish Mariam's Renewal</MainButton>;
  }
  return (
    <>
      {head}
      <MiniSteps steps={steps} />
      {officer && <OfficerBadge officer={officer} signOut={p.signOut} />}
      {completed && !p.recovered && <Outcome tone="hold" title="The case completed, but WAKALA has not recorded it as a recovery." />}
      {p.heldNow && !p.approvedOk ? <Outcome tone="hold" title="Held for officer approval.">{why}</Outcome> : <p className="mt-4 text-[15.5px] leading-snug text-fg">{why}</p>}
      <Spacer />
      <div className="mt-4">{action}</div>
    </>
  );
}

// ------------------------------------------------------------------------------------------------ technical details
function TechPanel({ model, selected, portal, ids }: { model: ReturnType<typeof buildAuthorityMap>; selected: string | null; portal: Any | null; ids: Any }) {
  const node = model.nodes.find((n) => n.id === selected) ?? null;
  return (
    <div className="grid gap-5 border-t border-line px-5 py-4 lg:grid-cols-[minmax(0,5fr)_minmax(0,7fr)]">
      <div>
        <p className="eyebrow mb-2">{node ? `${node.title}${node.conceptual ? " (conceptual role)" : ""}` : "Selected box"}</p>
        {node ? (
          <dl className="grid grid-cols-[150px_1fr] gap-x-3 gap-y-1 font-mono text-[12px]">
            {node.tech.map(([k, v]) => <div key={k} className="contents"><dt className="text-fg-subtle">{k}</dt><dd className="break-all text-fg">{v}</dd></div>)}
          </dl>
        ) : <p className="text-[13.5px] text-fg-subtle">Select any box on the map to see its identity, signed mandate and verification result.</p>}
        <p className="eyebrow mb-2 mt-5">Demo cases</p>
        <dl className="grid grid-cols-[150px_1fr] gap-x-3 gap-y-1 font-mono text-[12px]">
          {(["scene1", "scene2_mariam", "scene2_unrelated"] as const).map((k) => (
            <div key={k} className="contents"><dt className="text-fg-subtle">{{ scene1: "normal case", scene2_mariam: "security-test case", scene2_unrelated: "unrelated case" }[k]}</dt>
              <dd className="text-fg">{ids[k] ? `${ids[k].case_id} · ${ids[k].citizen_ref} · ${ids[k].state}` : "—"}</dd></div>
          ))}
        </dl>
        <p className="eyebrow mb-2 mt-5">Where each state comes from</p>
        <ul className="space-y-0.5 font-mono text-[11.5px] text-fg-muted">
          <li>case, decisions, delegations · GET /api/portal/cases/&#123;id&#125;</li>
          <li>signed mandate verification · GET /api/workflow/cases/&#123;id&#125;/case-view</li>
          <li>incident, approvals · GET /api/officer/incidents/&#123;id&#125;, /api/officer/approvals</li>
          <li>demo session · GET /api/portal/demo</li>
        </ul>
      </div>
      <div className="min-w-0">
        <p className="eyebrow mb-2">Gateway decisions on the case shown {portal ? `(${portal.case_id})` : ""}</p>
        {!portal?.timeline?.length ? <p className="text-[13.5px] text-fg-subtle">No decisions yet.</p> : (
          <div className="max-h-[300px] overflow-auto rounded-lg border border-line">
            <table className="w-full whitespace-nowrap text-left font-mono text-[11.5px]">
              <thead className="sticky top-0 bg-ink-800 text-fg-subtle"><tr><th className="px-2 py-1.5">#</th><th className="px-2">agent</th><th className="px-2">tool</th><th className="px-2">decision</th><th className="px-2">reason codes</th><th className="px-2">event</th></tr></thead>
              <tbody>
                {portal.timeline.map((t: Any) => (
                  <tr key={t.event_id} className="border-t border-line">
                    <td className="px-2 py-1 text-fg-subtle">{t.sequence}</td><td className="px-2 text-fg">{t.agent_id}</td><td className="px-2 text-fg">{t.tool_name}</td>
                    <td className={clsx("px-2 font-semibold", t.decision === "allowed" ? "text-trust" : t.decision === "denied" ? "text-deny" : "text-warn")}>{t.decision}</td>
                    <td className="px-2 text-fg-muted">{t.reason_codes.join(", ")}</td><td className="px-2 text-fg-subtle">{t.event_id}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        <p className="mt-2 text-[12px] text-fg-subtle">A denied request is never dispatched to the protected service; this is enforced and tested in the backend. Full chains: <Link to={portal ? `/delegation?case=${portal.case_id}` : "/delegation"} className="text-navy underline">Delegation Network</Link> · <Link to="/soc" className="text-navy underline">Security Operations</Link></p>
      </div>
    </div>
  );
}
