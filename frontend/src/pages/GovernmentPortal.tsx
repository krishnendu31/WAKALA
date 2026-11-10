/* eslint-disable @typescript-eslint/no-explicit-any */
import clsx from "clsx";
import { AlertTriangle, ArrowRight, BadgeCheck, Bot, Building2, CheckCircle2, ChevronDown, Circle, CircleDot, ExternalLink, FileUp, Loader2, Lock, MonitorPlay, PauseCircle, RotateCcw, Send, ShieldCheck, ShieldX, Sparkles, UserRound, type LucideIcon } from "lucide-react";
import { Component, useCallback, useEffect, useRef, useState, type ReactNode } from "react";
import { Link } from "react-router-dom";
import { AiActivityReceipt } from "@/components/AiActivityReceipt";
import { Badge } from "@/components/ui";
import { API_BASE_URL, ApiError, apiGet, apiPost } from "@/lib/api";

type Any = Record<string, any>;
const DEFAULT_MSG = "I want to renew my residency permit.";
const DISP: Record<string, { label: string; cls: string; icon: LucideIcon }> = {
  CLEAN: { label: "CLEAN", cls: "border-trust/40 bg-trust-soft text-trust", icon: ShieldCheck },
  REVIEW: { label: "REVIEW REQUIRED", cls: "border-warn/40 bg-warn-soft text-warn", icon: AlertTriangle },
  QUARANTINED: { label: "QUARANTINED", cls: "border-deny/40 bg-deny-soft text-deny", icon: ShieldX },
};

function usePoll<T>(path: string | null, ms: number): [T | null, () => void, string | null] {
  const [data, setData] = useState<T | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [n, setN] = useState(0);
  useEffect(() => {
    if (!path) { setData(null); return; }
    let live = true;
    const tick = () => apiGet<T>(path).then((d) => { if (live) { setData(d); setErr(null); } })
      .catch((e) => live && setErr(e instanceof ApiError ? `${e.code}: ${e.message}` : String(e)));
    tick();
    const id = setInterval(tick, ms);
    return () => { live = false; clearInterval(id); };
  }, [path, ms, n]);
  return [data, () => setN((x) => x + 1), err];
}

function Step({ s, last }: { s: Any; last: boolean }) {
  const Icon = s.status === "done" ? CheckCircle2 : s.status === "active" ? CircleDot : s.status === "blocked" ? PauseCircle : Circle;
  return (
    <li className="relative flex gap-3 pb-5">
      {!last && <span className={clsx("absolute left-[11px] top-7 h-[calc(100%-22px)] w-px", s.status === "done" ? "bg-trust/60" : "bg-line")} />}
      <Icon className={clsx("mt-0.5 size-6 shrink-0 transition-colors", s.status === "done" ? "text-trust" : s.status === "active" ? "animate-pulse text-cyan" : s.status === "blocked" ? "text-warn" : "text-fg-subtle")} aria-hidden />
      <div>
        <p className={clsx("text-[15px]", s.status === "pending" ? "text-fg-subtle" : "text-fg")}>{s.label}</p>
        {s.status === "blocked" && <p className="text-[12.5px] text-warn">Paused for security review</p>}
      </div>
    </li>
  );
}

function ChatBubble({ who, children, tone }: { who: "citizen" | "assistant" | "system"; children: ReactNode; tone?: "ok" | "deny" | "hold" }) {
  return (
    <div className={clsx("flex gap-2.5", who === "citizen" && "flex-row-reverse")}>
      <span className={clsx("mt-1 flex size-8 shrink-0 items-center justify-center rounded-full", who === "citizen" ? "bg-ink-700" : "bg-trust-soft")}>
        {who === "citizen" ? <UserRound className="size-4 text-fg-muted" /> : <Bot className="size-4 text-trust" />}
      </span>
      <div className={clsx("max-w-[85%] rounded-2xl px-4 py-2.5 text-[14px] leading-relaxed",
        who === "citizen" ? "rounded-tr-sm bg-ink-700 text-fg" : tone === "deny" ? "rounded-tl-sm border border-deny/30 bg-deny-soft text-fg" :
          tone === "hold" ? "rounded-tl-sm border border-warn/30 bg-warn-soft text-fg" : "rounded-tl-sm border border-line bg-ink-850 text-fg")}>{children}</div>
    </div>
  );
}

function Conversation({ runs }: { runs: Any[] }) {
  const end = useRef<HTMLDivElement>(null);
  useEffect(() => { end.current?.scrollIntoView({ behavior: "smooth", block: "nearest" }); }, [runs.length, runs.at(-1)?.transcript?.length]);
  if (!runs.length) return <p className="py-10 text-center text-[13.5px] text-fg-subtle">Ask the assistant to start your service.</p>;
  return (
    <div className="space-y-3">
      {runs.map((run) => (
        <div key={run.run_id} className="space-y-3">
          <p className="text-center text-[11px] uppercase tracking-wider text-fg-subtle">
            {run.mode.startsWith("model") ? `AI model · ${run.mode.split(":").slice(2).join(":")}` : "Deterministic offline assistant (no AI model)"} · {run.purpose}
          </p>
          {run.transcript.map((t: Any, i: number) => {
            if (t.role === "citizen") return <ChatBubble key={i} who="citizen">{t.text}</ChatBubble>;
            if (t.role === "assistant") return <ChatBubble key={i} who="assistant">{t.text}</ChatBubble>;
            if (t.role === "model") {
              const text = t.blocks.filter((b: Any) => b.type === "text").map((b: Any) => b.text).join(" ");
              return text ? <ChatBubble key={i} who="assistant">{text}</ChatBubble> : null;
            }
            if (t.role === "tool") {
              const o = t.output ?? {};
              const inner = o.insurance_check ?? o;
              const blocked = t.is_error;
              const held = (inner.reason_codes ?? []).includes("ESCALATE_HUMAN_REVIEW");
              const text = inner.plain_english ?? o.error ?? (t.name === "read_case_document" ? (o.released ? "Read the document as untrusted data." : `Document withheld: ${o.withheld_reason ?? o.error}`) : "Done.");
              return (
                <ChatBubble key={i} who="assistant" tone={held ? "hold" : blocked ? "deny" : "ok"}>
                  <span className="text-[12px] text-fg-subtle">{t.name.replace(/_/g, " ")}</span><br />{text}
                </ChatBubble>
              );
            }
            return null;
          })}
          {run.error && <ChatBubble who="system" tone="deny">The assistant stopped: {run.status} ({run.error}). Nothing further was attempted.</ChatBubble>}
        </div>
      ))}
      <div ref={end} />
    </div>
  );
}

function Scene({ n, title, active, done, children }: { n: number; title: string; active: boolean; done: boolean; children: ReactNode }) {
  return (
    <div className={clsx("rounded-xl border p-3 transition-colors", active ? "border-trust/50 bg-trust-soft/40" : "border-line bg-ink-850/60")}>
      <p className="flex items-center gap-2 text-[13px] font-medium text-fg">
        <span className={clsx("flex size-5 items-center justify-center rounded-full text-[11px]", done ? "bg-trust text-ink-950" : "bg-ink-700 text-fg-muted")}>{n}</span>{title}
      </p>
      <div className="mt-2 space-y-2 text-[12.5px] text-fg-muted">{children}</div>
    </div>
  );
}

function Btn({ onClick, children, busy, tone = "trust", disabled }: { onClick: () => void; children: ReactNode; busy?: boolean; tone?: "trust" | "deny" | "neutral"; disabled?: boolean }) {
  return (
    <button onClick={onClick} disabled={busy || disabled} className={clsx("inline-flex items-center gap-1.5 rounded-lg border px-3 py-1.5 text-[12.5px] font-medium transition-colors disabled:opacity-40",
      tone === "trust" ? "border-trust/50 text-trust hover:bg-trust-soft" : tone === "deny" ? "border-deny/50 text-deny hover:bg-deny-soft" : "border-line text-fg-muted hover:bg-ink-750")}>
      {busy && <Loader2 className="size-3.5 animate-spin" />}{children}
    </button>
  );
}

class PortalErrorBoundary extends Component<{ children: ReactNode }, { error: string | null }> {
  state = { error: null as string | null };
  static getDerivedStateFromError(e: Error) { return { error: e.message }; }
  render() {
    return this.state.error
      ? <div className="rounded-xl border border-deny/40 bg-deny-soft p-5 text-[13.5px] text-deny">The portal view failed to render ({this.state.error}). The backend state is unaffected — reload the page.</div>
      : this.props.children;
  }
}

export function GovernmentPortal() {
  return <PortalErrorBoundary><PortalView /></PortalErrorBoundary>;
}

function PortalView() {
  const [demo, reloadDemo] = usePoll<Any>("/api/portal/demo", 4000);
  const [cfg] = usePoll<Any>("/api/portal/config", 60000);
  const [caseId, setCaseId] = useState<string | null>(null);
  const [view, reloadView, viewErr] = usePoll<Any>(caseId ? `/api/portal/cases/${caseId}` : null, 2000);
  const [citizens] = usePoll<Any>("/api/citizens", 60000);
  const [evidence] = usePoll<Any>("/api/evidence/summary", 120000);
  const [msg, setMsg] = useState(DEFAULT_MSG);
  const [busy, setBusy] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [adv, setAdv] = useState<Any | null>(null);
  const [inj, setInj] = useState<Any | null>(null);
  const [details, setDetails] = useState(false);
  const [presenter, setPresenter] = useState(true);
  const [receipt, setReceipt] = useState(false);
  const fileRef = useRef<HTMLInputElement>(null);

  useEffect(() => {  // follow the demo session's most recent case when none is selected
    if (!caseId && demo?.cases) {
      const order = ["scene2_mariam", "scene1"];
      const pick = order.map((k) => demo.cases[k]?.case_id).find(Boolean);
      if (pick) setCaseId(pick);
    }
  }, [demo, caseId]);

  const act = useCallback(async (label: string, fn: () => Promise<any>) => {
    setBusy(label); setErr(null);
    try { const r = await fn(); reloadDemo(); reloadView(); return r; }
    catch (e) { setErr(e instanceof ApiError ? `${e.code}: ${e.message}` : String(e)); return null; }
    finally { setBusy(null); }
  }, [reloadDemo, reloadView]);

  const startService = () => act("start", async () => { setAdv(null); setInj(null); const r = await apiPost<Any>("/api/portal/requests", { citizen_ref: "C-1001", message: msg, use_model: true }); setCaseId(r.case_id); });
  const incident = () => act("incident", async () => { setAdv(null); setInj(null); const r = await apiPost<Any>("/api/portal/scenes/incident"); setCaseId(r.case_id); });
  const cont = () => act("continue", () => apiPost(`/api/portal/cases/${caseId}/continue`, { use_model: false }));
  const sample = (key: string) => act(key, () => apiPost(`/api/portal/cases/${caseId}/documents/samples/${key}`));
  const upload = (f: File) => act("upload", async () => {
    const res = await fetch(`${API_BASE_URL}/api/portal/cases/${caseId}/documents`, { method: "POST", body: f, headers: { "Content-Type": "application/pdf", "X-Filename": f.name.slice(-120) } });
    const body = await res.json().catch(() => null);
    if (!res.ok) throw new ApiError(body?.error?.message ?? res.statusText, res.status, body?.error?.code ?? `HTTP_${res.status}`);
    return body;
  });
  const quarantined = view?.documents?.find((d: Any) => d.disposition === "QUARANTINED");
  const bypass = () => act("bypass", async () => setAdv(await apiPost<Any>(`/api/documents/${quarantined.document_id}/adversarial-test`)));
  const injection = () => act("inj", async () => setInj(await apiPost<Any>(`/api/portal/cases/${caseId}/documents/${quarantined.document_id}/injection-test`)));
  const reset = () => act("reset", async () => { await apiPost("/api/portal/demo/reset"); setCaseId(null); setAdv(null); setInj(null); });
  const openSoc = () => window.open("/soc", "wakala-soc", "width=1280,height=900");

  const citizen = citizens?.items?.find?.((c: Any) => c.citizen_ref === (view?.citizen_ref ?? "C-1001")) ?? (Array.isArray(citizens) ? citizens.find((c: Any) => c.citizen_ref === "C-1001") : null);
  const scene = demo?.scene ?? 0;
  const C = evidence?.configurations?.C;
  const banner = view?.banner;

  return (
    <div className="-mx-2 space-y-5 sm:mx-0">
      {/* fictional service header */}
      <div className="overflow-hidden rounded-2xl border border-line bg-gradient-to-r from-[#0a1a33] via-[#0c2240] to-[#0b2b3a]">
        <div className="flex flex-wrap items-center gap-4 px-6 py-5">
          <span className="flex size-12 items-center justify-center rounded-xl border border-trust/30 bg-trust-soft"><Building2 className="size-6 text-trust" /></span>
          <div className="min-w-0 flex-1">
            <p className="text-[12px] uppercase tracking-[0.18em] text-trust/80">Fictional Residency Services Authority · Digital Services</p>
            <h1 className="text-[26px] font-semibold tracking-tight text-fg">Government AI Services Portal</h1>
            <p className="text-[13px] text-fg-muted">AI assistants handle your request · every sensitive action is independently verified by <b className="text-fg">WAKALA</b></p>
          </div>
          <div className="flex flex-col items-end gap-1.5">
            <Badge tone="warn" className="uppercase tracking-wider">Fictional prototype · synthetic data</Badge>
            <span className="text-[11px] text-fg-subtle">Not an official government website</span>
          </div>
        </div>
        <div className="flex flex-wrap items-center gap-3 border-t border-white/5 bg-black/20 px-6 py-2 text-[12px] text-fg-muted">
          <Sparkles className="size-3.5 text-trust" />
          Assistant: <b className="text-fg">{cfg?.agent_mode ?? "…"}</b>
          {view && <><span className="text-line-strong">|</span>Case <span className="font-mono text-fg">{view.case_id}</span> · {view.state}</>}
          <span className="ml-auto flex gap-2">
            <button onClick={openSoc} className="inline-flex items-center gap-1 text-trust hover:underline"><ExternalLink className="size-3.5" /> Open Security Operations side by side</button>
            <button onClick={() => setPresenter(!presenter)} className="inline-flex items-center gap-1 hover:text-fg"><MonitorPlay className="size-3.5" /> Presenter</button>
          </span>
        </div>
      </div>

      {err && <p className="rounded-xl border border-deny/30 bg-deny-soft px-4 py-2.5 text-[13px] text-deny">{err}</p>}
      {viewErr && caseId && <p className="text-[12px] text-warn">Live update failed: {viewErr}</p>}

      <div className={clsx("grid gap-5", presenter ? "2xl:grid-cols-[300px_minmax(0,1fr)_minmax(0,1fr)_320px] xl:grid-cols-[300px_minmax(0,1fr)_minmax(0,1fr)]" : "xl:grid-cols-[300px_minmax(0,1fr)_minmax(0,1fr)]")}>
        {/* citizen + progress */}
        <div className="space-y-5">
          <div className="card p-5">
            <div className="flex items-center gap-3">
              <span className="flex size-11 items-center justify-center rounded-full bg-ink-700 text-[16px] font-semibold text-fg">{(view?.citizen_name ?? citizen?.full_name ?? "M")[0]}</span>
              <div>
                <p className="text-[15px] font-medium text-fg">{view?.citizen_name ?? citizen?.full_name ?? "Mariam Al Hashimi"}</p>
                <p className="font-mono text-[11.5px] text-fg-subtle">{view?.citizen_ref ?? "C-1001"} · synthetic citizen</p>
              </div>
            </div>
            <p className="mt-4 text-[12px] uppercase tracking-wider text-fg-subtle">Service</p>
            <p className="text-[14px] text-fg">Residency permit renewal · AED 500</p>
          </div>
          <div className="card p-5">
            <p className="mb-4 text-[12px] uppercase tracking-wider text-fg-subtle">Application progress</p>
            {view ? <ol>{view.steps.map((s: Any, i: number) => <Step key={s.key} s={s} last={i === view.steps.length - 1} />)}</ol>
              : <p className="text-[13px] text-fg-subtle">No application yet.</p>}
            {view && <div className="mt-3 flex flex-col gap-1.5">
              <button onClick={() => setReceipt(true)} className="inline-flex items-center justify-center gap-1.5 rounded-lg border border-trust/50 px-3 py-1.5 text-[12.5px] font-medium text-trust hover:bg-trust-soft">My AI Activity</button>
              <Link to={`/delegation?case=${view.case_id}`} className="text-center text-[11.5px] text-fg-muted hover:text-fg">See who was authorized (Case View) →</Link>
            </div>}
            {view && view.ledger?.length > 0 && <p className="mt-1 font-mono text-[11.5px] text-fg-subtle">Receipt {view.ledger[0].transaction_id ?? ""} · AED {view.ledger[0].amount} → {view.ledger[0].recipient}</p>}
          </div>
        </div>

        {/* assistant */}
        <div className="card flex min-h-[520px] flex-col">
          <div className="flex items-center gap-2 border-b border-line px-5 py-3"><Bot className="size-4 text-trust" /><p className="text-[14px] font-medium text-fg">AI assistant</p></div>
          {banner && (
            <div className={clsx("mx-4 mt-4 flex items-start gap-2 rounded-xl border px-3 py-2.5 text-[13.5px]",
              banner.kind === "success" ? "border-trust/40 bg-trust-soft text-trust" : banner.kind === "review" ? "border-warn/40 bg-warn-soft text-warn" : "border-line bg-ink-850 text-fg-muted")}>
              {banner.kind === "success" ? <BadgeCheck className="mt-0.5 size-4" /> : banner.kind === "review" ? <Lock className="mt-0.5 size-4" /> : <Loader2 className="mt-0.5 size-4 animate-spin" />}{banner.text}
            </div>
          )}
          <div className="flex-1 overflow-y-auto px-4 py-4"><Conversation runs={view?.agent_runs ?? []} /></div>
          <form onSubmit={(e) => { e.preventDefault(); startService(); }} className="flex gap-2 border-t border-line p-3">
            <input value={msg} onChange={(e) => setMsg(e.target.value)} maxLength={500} className="flex-1 rounded-xl border border-line bg-ink-900 px-4 py-2.5 text-[14px] text-fg focus:border-trust" aria-label="Message to the assistant" />
            <button disabled={busy !== null || !msg.trim()} className="inline-flex items-center gap-1.5 rounded-xl bg-trust px-4 text-[13.5px] font-medium text-ink-950 disabled:opacity-40">
              {busy === "start" ? <Loader2 className="size-4 animate-spin" /> : <Send className="size-4" />} Send
            </button>
          </form>
        </div>

        {/* what WAKALA checked */}
        <div className="space-y-5">
          <div className="card">
            <div className="flex items-center justify-between border-b border-line px-5 py-3">
              <p className="flex items-center gap-2 text-[14px] font-medium text-fg"><ShieldCheck className="size-4 text-trust" /> What WAKALA verified</p>
              <button onClick={() => setDetails(!details)} className="inline-flex items-center gap-1 text-[12px] text-fg-muted">Technical details <ChevronDown className={clsx("size-3.5 transition-transform", details && "rotate-180")} /></button>
            </div>
            <ul className="max-h-[420px] divide-y divide-line overflow-y-auto">
              {(view?.timeline ?? []).length === 0 && <li className="px-5 py-6 text-[13px] text-fg-subtle">Every agent action will appear here with WAKALA's independent decision.</li>}
              {(view?.timeline ?? []).map((t: Any) => (
                <li key={t.event_id} className="px-5 py-3">
                  <div className="flex items-start gap-2">
                    {t.decision === "allowed" ? <CheckCircle2 className="mt-0.5 size-4 shrink-0 text-trust" /> : t.decision === "escalated" ? <PauseCircle className="mt-0.5 size-4 shrink-0 text-warn" /> : <ShieldX className="mt-0.5 size-4 shrink-0 text-deny" />}
                    <div className="min-w-0">
                      <p className="text-[13.5px] text-fg">{t.plain_english}</p>
                      {details && <p className="mt-1 break-all font-mono text-[11px] text-fg-subtle">#{t.sequence} {t.agent_id} · {t.tool_name} · {t.reason_codes.join(", ")} · mandate {t.mandate_id} · {t.event_id}</p>}
                    </div>
                  </div>
                </li>
              ))}
            </ul>
          </div>
          <div className="card p-5">
            <p className="mb-3 flex items-center gap-2 text-[14px] font-medium text-fg"><FileUp className="size-4 text-trust" /> Supporting documents</p>
            <input ref={fileRef} type="file" accept="application/pdf,.pdf" disabled={!caseId} className="block w-full text-[12px] text-fg-muted file:mr-3 file:rounded-lg file:border file:border-line file:bg-ink-800 file:px-3 file:py-1.5 file:text-fg disabled:opacity-40"
              onChange={(e) => { const f = e.target.files?.[0]; if (f) upload(f); e.target.value = ""; }} />
            {!caseId && <p className="mt-2 text-[12px] text-fg-subtle">Start a request first.</p>}
            <ul className="mt-3 space-y-2">{(view?.documents ?? []).map((d: Any) => {
              const s = DISP[d.disposition] ?? DISP.QUARANTINED!;
              return (
                <li key={d.document_id} className={clsx("rounded-xl border p-3", s.cls)}>
                  <p className="flex items-center gap-2 text-[13px] font-semibold"><s.icon className="size-4" />{s.label}<span className="ml-auto font-mono text-[11px] font-normal opacity-80">{d.document_id}</span></p>
                  <p className="mt-1 truncate text-[12px] text-fg-muted">{d.display_name}</p>
                  {d.findings.slice(0, 2).map((f: Any, i: number) => <p key={i} className="mt-1 text-[11.5px] text-fg-muted">{f.rule_id} · {f.layer.replace("_", " ")} · page {f.page} — “{f.excerpt.slice(0, 80)}…”</p>)}
                  <Link to="/documents" className="mt-1 inline-flex items-center gap-1 text-[11.5px] text-trust hover:underline">Inspect in Document Shield <ArrowRight className="size-3" /></Link>
                </li>
              );
            })}</ul>
          </div>
        </div>

        {receipt && caseId && <AiActivityReceipt caseId={caseId} onClose={() => setReceipt(false)} />}
        {/* presenter */}
        {presenter && (
          <div className="space-y-3 xl:col-span-3 2xl:col-span-1">
            <div className="flex items-center justify-between">
              <p className="text-[12px] uppercase tracking-wider text-fg-subtle">Guided demonstration · {demo?.session_id ?? "no session"}</p>
              <button onClick={reset} disabled={busy !== null} className="inline-flex items-center gap-1 text-[12px] text-fg-muted hover:text-fg"><RotateCcw className="size-3.5" /> New demo session</button>
            </div>
            <div className="grid gap-3 xl:grid-cols-5 2xl:grid-cols-1">
              <Scene n={1} title="Normal service" active={!view || view.state !== "COMPLETED"} done={!!demo?.cases?.scene1 && demo.cases.scene1.state === "COMPLETED"}>
                <p>Mariam asks the assistant. The Residency Agent registers, checks eligibility, delegates insurance; the Payment Agent collects AED 500.</p>
                <Btn onClick={startService} busy={busy === "start"}>Send “{DEFAULT_MSG.slice(0, 22)}…”</Btn>
              </Scene>
              <Scene n={2} title="Cross-citizen incident" active={scene >= 1} done={!!demo?.cases?.scene2_mariam}>
                <p>Fresh case: the Insurance Agent requests another citizen's record. WAKALA blocks it before execution and opens an incident.</p>
                <Btn onClick={incident} busy={busy === "incident"} tone="deny">Run the unauthorized request</Btn>
              </Scene>
              <Scene n={3} title="Accountable recovery" active={view?.state === "PAUSED_FOR_REVIEW" || (view?.pending_approvals?.length ?? 0) > 0} done={demo?.cases?.scene2_mariam?.recovery_status === "recovered"}>
                <p>In Security Operations: sign in → open the incident → Mark under review → Reassign to the standby agent → Resume.
                  Then <b className="text-fg">Continue my case</b>: the delegation is held. Approve it in Approvals (it is re-authorized), Resolve the incident, and Continue again.</p>
                <div className="flex flex-wrap gap-2"><Btn onClick={openSoc} tone="neutral">Open Security Operations</Btn><Btn onClick={cont} busy={busy === "continue"} disabled={!caseId}>Continue my case</Btn></div>
                {demo?.cases?.scene2_unrelated && <p className="font-mono text-[11px]">Unrelated case {demo.cases.scene2_unrelated.case_id} ({demo.cases.scene2_unrelated.citizen_ref}): {demo.cases.scene2_unrelated.state}</p>}
              </Scene>
              <Scene n={4} title="Malicious PDF" active={!!view} done={!!quarantined}>
                <div className="flex flex-wrap gap-2">
                  <Btn onClick={() => sample("normal")} busy={busy === "normal"} disabled={!caseId} tone="neutral">Attach normal PDF</Btn>
                  <Btn onClick={() => sample("hidden_payment_injection")} busy={busy === "hidden_payment_injection"} disabled={!caseId} tone="deny">Attach hidden-text PDF</Btn>
                </div>
                {quarantined && (
                  <div className="flex flex-wrap gap-2">
                    <Btn onClick={bypass} busy={busy === "bypass"} tone="neutral">Gateway-bypass test (simulated agent)</Btn>
                    <Btn onClick={injection} busy={busy === "inj"} tone="neutral">Real-model injection test</Btn>
                  </div>
                )}
                {adv && <p className={adv.ledger_unchanged ? "text-trust" : "text-deny"}>Simulated manipulated agent (no LLM): {adv.attempts.map((a: Any) => `${a.agent_id} ${a.allowed ? "ALLOWED" : "denied"}`).join(", ")} · ledger {adv.ledger_rows_total_before} → {adv.ledger_rows_total_after}</p>}
                {inj && (inj.status === "not_run" ? <p className="text-warn">Real-model test not run: {inj.reason}</p> :
                  <p>Model proposed: {inj.summary.model_proposed_tool_calls.map((c: Any) => c.name).join(", ") || "no tool call"} · unauthorized payment proposed: {String(inj.summary.unauthorized_payment_proposed)} · gateway denials {inj.summary.gateway_denials.length} · status {inj.status}</p>)}
              </Scene>
              <Scene n={5} title="Real evidence" active={false} done={false}>
                {C ? <p>{evidence.dataset.total_requests} requests · unauthorized executed {C.unauthorized_operations_executed.numerator}/{C.unauthorized_operations_executed.denominator} · false denials {C.legitimate_incorrectly_denied.numerator}/{C.legitimate_incorrectly_denied.denominator} · back-to-back recovery {evidence.recovery.back_to_back_shared.recovery_success.numerator}/{evidence.recovery.back_to_back_shared.recovery_success.denominator}</p> : <p>Evidence not generated.</p>}
                <Link to="/evidence" className="inline-flex items-center gap-1 text-trust hover:underline">Open Security Evidence <ArrowRight className="size-3.5" /></Link>
              </Scene>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
