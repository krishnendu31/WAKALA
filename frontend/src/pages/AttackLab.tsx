/* eslint-disable @typescript-eslint/no-explicit-any */
import clsx from "clsx";
import { CheckCircle2, ChevronDown, FlaskConical, Loader2, Play, PlayCircle, RotateCcw, ShieldCheck, ShieldX, Swords, XCircle } from "lucide-react";
import { useEffect, useState } from "react";
import { Badge, Card, CardHeader, Notice, PageHeader, SyntheticBadge } from "@/components/ui";
import { ApiError, apiGet, apiPost } from "@/lib/api";

type Any = Record<string, any>;

function Flag({ ok, label }: { ok: boolean; label: string }) {
  return <span className={clsx("inline-flex items-center gap-1 text-[12px]", ok ? "text-deny" : "text-trust")}>{ok ? <XCircle className="size-3.5" /> : <CheckCircle2 className="size-3.5" />}{label}: {ok ? "yes" : "no"}</span>;
}

function Side({ title, attempts, wakala }: { title: string; attempts: Any[]; wakala?: boolean }) {
  return (
    <div className={clsx("rounded-xl border p-4", wakala ? "border-trust/30 bg-trust-soft/30" : "border-line bg-ink-900/50")}>
      <p className="flex items-center gap-2 text-[12px] uppercase tracking-wider text-fg-subtle">{wakala ? <ShieldCheck className="size-4 text-trust" /> : <FlaskConical className="size-4" />}{title}</p>
      {attempts.map((a, i) => (
        <div key={i} className="mt-3">
          <p className={clsx("text-[15px] font-semibold", a.executed ? "text-deny" : "text-trust")}>
            {a.executed ? "Request executed." : wakala ? "Blocked before execution." : "Refused."}
          </p>
          <p className="mt-0.5 text-[13px] text-fg">{wakala ? a.plain_english : a.reason}</p>
          <p className="mt-1 font-mono text-[11px] text-fg-subtle">{a.agent_id} · {a.operation}</p>
          <div className="mt-2 flex flex-wrap gap-3">
            <Flag ok={a.executed} label="Operation executed" /><Flag ok={a.data_returned} label="Protected data returned" /><Flag ok={a.state_modified} label="State modified" />
          </div>
          {wakala && a.monitoring?.length > 0 && <p className="mt-1 text-[11.5px] text-warn">Behaviour Watch: {a.monitoring.join(", ")}</p>}
        </div>
      ))}
    </div>
  );
}

function Result({ r }: { r: Any }) {
  const [open, setOpen] = useState(false);
  const both = r.verdict.startsWith("Denied in both");
  return (
    <Card>
      <div className="border-b border-line px-5 py-4">
        <div className="flex flex-wrap items-center gap-2">
          <span className="flex size-7 items-center justify-center rounded-lg bg-ink-700 font-semibold text-fg">{r.letter}</span>
          <p className="text-[16px] font-semibold text-fg">{r.title}</p>
          <Badge tone={r.outcome.wakala_executed ? "deny" : both ? "neutral" : "trust"}>{r.verdict}</Badge>
          <span className="ml-auto font-mono text-[11px] text-fg-subtle">{r.duration_ms} ms · fp {r.outcome_fingerprint}</span>
        </div>
        <p className="mt-1.5 text-[14px] text-fg">{r.story}</p>
        <p className="mt-1 text-[12.5px] text-fg-muted"><b className="text-fg-subtle">Target:</b> {r.target} · <b className="text-fg-subtle">Original authority:</b> {r.original_authority}</p>
      </div>
      <div className="grid gap-4 p-5 lg:grid-cols-2">
        <Side title="Without WAKALA · weak role-only baseline" attempts={r.baseline.attempts} />
        <Side title="With WAKALA · full enforcement" attempts={r.wakala.attempts} wakala />
      </div>
      {r.baseline_note && <p className="px-5 pb-3 text-[12px] text-fg-subtle">Note: {r.baseline_note}</p>}
      {r.wakala.document_shield && (
        <p className="px-5 pb-3 text-[12.5px] text-fg-muted">Document Shield: <b className="text-deny">{r.wakala.document_shield.document_disposition}</b> · {r.wakala.document_shield.high_findings} high findings · {r.wakala.document_shield.hidden_runs} hidden text runs · agent received content: {String(r.wakala.document_shield.agent_received_content)} · ledger {r.wakala.document_shield.ledger_rows_before} → {r.wakala.document_shield.ledger_rows_after}</p>
      )}
      <button onClick={() => setOpen(!open)} className="flex w-full items-center gap-1 border-t border-line px-5 py-2.5 text-[12px] text-fg-muted hover:text-fg">
        <ChevronDown className={clsx("size-3.5 transition-transform", open && "rotate-180")} /> Technical evidence ({r.evidence.events.length} audit events · chain {r.evidence.audit_chain_valid ? "valid" : "INVALID"})
      </button>
      {open && (
        <div className="space-y-2 border-t border-line bg-ink-900/40 px-5 py-3 font-mono text-[11px]">
          {r.wakala.attempts.map((a: Any, i: number) => <p key={i} className="text-deny">{a.agent_id} · {a.operation} · {a.reason_codes.join(", ")} · {a.audit_reference}</p>)}
          {r.evidence.events.map((e: Any) => (
            <p key={e.event_id} className="text-fg-muted">#{e.sequence} {e.timestamp} · {e.decision} · {e.actor ?? e.claimed_agent_id} · {e.action} · hash {String(e.event_hash ?? "").slice(0, 16)}</p>
          ))}
          <p className="text-fg-subtle">Isolated environment destroyed after the run; events copied here with the chain verification result. Started {r.started_at} · seed {r.seed}.</p>
        </div>
      )}
    </Card>
  );
}

export function AttackLab() {
  const [scenarios, setScenarios] = useState<Any[]>([]);
  const [sel, setSel] = useState<string>("cross_citizen");
  const [run, setRun] = useState<Any | null>(null);
  const [history, setHistory] = useState<Any | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [seed, setSeed] = useState(2026);
  const loadHistory = () => apiGet<Any>("/api/attack-lab/runs").then(setHistory).catch(() => undefined);
  useEffect(() => { apiGet<Any[]>("/api/attack-lab/scenarios").then(setScenarios).catch((e) => setErr(e instanceof ApiError ? `${e.code}: ${e.message}` : String(e))); loadHistory(); }, []);
  const go = async (label: string, body: Any) => {
    setBusy(label); setErr(null);
    try { setRun(await apiPost<Any>("/api/attack-lab/run", { ...body, seed })); loadHistory(); }
    catch (e) { setErr(e instanceof ApiError ? `${e.code}: ${e.message}` : String(e)); }
    finally { setBusy(null); }
  };
  const reset = async () => { setBusy("reset"); try { await apiPost("/api/attack-lab/reset"); setRun(null); loadHistory(); } finally { setBusy(null); } };
  const open = async (id: string) => { setBusy(id); try { setRun(await apiGet<Any>(`/api/attack-lab/runs/${id}`)); } finally { setBusy(null); } };
  return (
    <>
      <PageHeader eyebrow="Live demonstration" title="WAKALA Attack Lab" titleAr="مختبر الهجمات"
        description="Real synthetic attacks, executed now. Each one runs twice in fresh isolated environments: once against an intentionally weak role-only baseline, once through full WAKALA enforcement."
        actions={<SyntheticBadge />} />
      <Notice tone="warn" icon={Swords} title="Developer/demo mode only · synthetic environments">
        Results come from actual execution, not a scoreboard. The baseline is deliberately weak (role check only) and does not represent every real IAM system; where it also refuses an attack, that is shown.
      </Notice>
      {err && <p className="rounded-xl border border-deny/30 bg-deny-soft px-4 py-2.5 text-[13px] text-deny">{err}</p>}
      <div className="grid gap-6 xl:grid-cols-[320px_1fr]">
        <div className="space-y-4">
          <Card>
            <CardHeader icon={Swords} title="Attacks" />
            <ul className="divide-y divide-line">{scenarios.map((s) => (
              <li key={s.key}><button onClick={() => setSel(s.key)} className={clsx("flex w-full items-start gap-2.5 px-4 py-2.5 text-left hover:bg-ink-800", sel === s.key && "bg-ink-750")}>
                <span className="mt-0.5 flex size-6 shrink-0 items-center justify-center rounded-md bg-ink-700 text-[12px] font-semibold text-fg">{s.letter}</span>
                <span><span className="block text-[13px] text-fg">{s.title}</span><span className="block text-[11.5px] text-fg-subtle">{s.story}</span></span>
              </button></li>
            ))}</ul>
            <div className="flex flex-wrap gap-2 border-t border-line p-3">
              <button onClick={() => go("one", { scenarios: [sel] })} disabled={busy !== null} className="inline-flex items-center gap-1.5 rounded-lg bg-trust px-3 py-1.5 text-[13px] font-medium text-ink-950 disabled:opacity-40">{busy === "one" ? <Loader2 className="size-4 animate-spin" /> : <Play className="size-4" />} Run selected</button>
              <button onClick={() => go("all", { scenarios: "all" })} disabled={busy !== null} className="inline-flex items-center gap-1.5 rounded-lg border border-trust/50 px-3 py-1.5 text-[13px] text-trust disabled:opacity-40">{busy === "all" ? <Loader2 className="size-4 animate-spin" /> : <PlayCircle className="size-4" />} Run all 8</button>
              <button onClick={reset} disabled={busy !== null} className="inline-flex items-center gap-1.5 rounded-lg border border-line px-3 py-1.5 text-[13px] text-fg-muted disabled:opacity-40"><RotateCcw className="size-4" /> Reset</button>
            </div>
            <label className="flex items-center gap-2 border-t border-line px-4 py-2 text-[12px] text-fg-muted">Seed <input type="number" value={seed} onChange={(e) => setSeed(Number(e.target.value) || 0)} className="w-24 rounded border border-line bg-ink-900 px-2 py-0.5 text-fg" /></label>
          </Card>
          <Card>
            <CardHeader icon={FlaskConical} title="Run history" subtitle={history?.session_id} />
            <ul className="max-h-72 divide-y divide-line overflow-y-auto">{(history?.runs ?? []).map((h: Any) => (
              <li key={h.run_id}><button onClick={() => open(h.run_id)} className="w-full px-4 py-2 text-left text-[12px] hover:bg-ink-800">
                <span className="font-mono text-fg">{h.run_id}</span> <span className="text-fg-subtle">{new Date(h.created_at).toLocaleTimeString()}</span><br />
                <span className="text-fg-muted">{h.summary.scenarios} attacks · baseline executed {h.summary.baseline_executed} · WAKALA executed {h.summary.wakala_executed}</span>
              </button></li>
            ))}</ul>
          </Card>
        </div>
        <div className="min-w-0 space-y-4">
          {run && (
            <div className="grid gap-3 sm:grid-cols-4">
              {[["Attacks run", run.summary.scenarios, "neutral"], ["Executed without WAKALA", run.summary.baseline_executed, "deny"], ["Executed with WAKALA", run.summary.wakala_executed, run.summary.wakala_executed ? "deny" : "trust"], ["Denied in both", run.summary.denied_in_both, "neutral"]].map(([l, v, t]) => (
                <div key={l as string} className="card p-4"><p className="text-[11.5px] uppercase tracking-wider text-fg-subtle">{l}</p><p className={clsx("mt-1 text-[28px] font-semibold", t === "deny" ? "text-deny" : t === "trust" ? "text-trust" : "text-fg")}>{v}</p></div>
              ))}
            </div>
          )}
          {run && <p className="font-mono text-[11.5px] text-fg-subtle">Run {run.run_id} · {run.created_at} · seed {run.seed}</p>}
          {!run && <div className="card flex items-center gap-3 p-8 text-[14px] text-fg-muted"><ShieldX className="size-5" /> Select an attack and press Run, or run all eight.</div>}
          {run?.results.map((r: Any) => <Result key={r.scenario + run.run_id} r={r} />)}
        </div>
      </div>
    </>
  );
}
