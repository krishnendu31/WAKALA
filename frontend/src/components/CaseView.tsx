/* eslint-disable @typescript-eslint/no-explicit-any */
import clsx from "clsx";
import { ArrowDown, Bot, Building2, CheckCircle2, CircleSlash, Clock, PauseCircle, RotateCcw, ShieldX, UserRound, type LucideIcon } from "lucide-react";
import { useEffect, useState } from "react";
import { apiGet } from "@/lib/api";

const STATE: Record<string, { label: string; cls: string; icon: LucideIcon }> = {
  authorized: { label: "Authorized", cls: "border-trust/40 bg-trust-soft text-trust", icon: CheckCircle2 },
  denied: { label: "Denied", cls: "border-deny/40 bg-deny-soft text-deny", icon: ShieldX },
  suspended: { label: "Suspended", cls: "border-warn/40 bg-warn-soft text-warn", icon: PauseCircle },
  revoked: { label: "Revoked", cls: "border-deny/50 bg-deny-soft text-deny", icon: CircleSlash },
  pending_approval: { label: "Pending approval", cls: "border-cyan/40 bg-ink-800 text-cyan", icon: Clock },
  recovered: { label: "Recovered", cls: "border-trust/50 bg-trust-soft text-trust", icon: RotateCcw },
};

function Pill({ state }: { state: string }) {
  const s = STATE[state] ?? STATE.denied!;
  return <span className={clsx("inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-[11.5px] font-medium", s.cls)}><s.icon className="size-3.5" />{s.label}</span>;
}

/** Projector-friendly linear view of one case: request → Residency Agent → delegated agent → protected services. */
export function CaseView({ caseId }: { caseId: string }) {
  const [v, setV] = useState<any | null>(null);
  const [sel, setSel] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);
  useEffect(() => {
    let live = true;
    const tick = () => apiGet<any>(`/api/workflow/cases/${caseId}/case-view`).then((d) => live && setV(d)).catch((e) => live && setErr(String(e)));
    tick();
    const id = setInterval(tick, 3000);
    return () => { live = false; clearInterval(id); };
  }, [caseId]);
  if (err && !v) return <p className="text-[13px] text-deny">{err}</p>;
  if (!v) return <p className="text-[13px] text-fg-subtle">Loading case…</p>;
  const selected = sel ? [...v.lanes.flatMap((l: any) => [{ id: l.mandate_id, title: `${l.agent_name} · ${l.mandate_id}`, explanation: l.explanation, technical: l.technical }, ...l.actions.map((a: any) => ({ id: a.technical.event_id, title: `${a.service} · ${a.tool_name}`, explanation: a.explanation, technical: a.technical }))])].find((x) => x.id === sel) : null;
  return (
    <div className="card p-6">
      <div className="flex flex-wrap items-center gap-2">
        <p className="text-[12px] uppercase tracking-wider text-fg-subtle">Case View</p>
        <span className="font-mono text-[13px] text-fg">{v.case_id}</span>
        <span className="text-[13px] text-fg-muted">· {v.state}{v.recovery_status === "recovered" ? " · recovered" : ""}</span>
        {v.incident && <span className="ml-auto rounded-full border border-deny/40 bg-deny-soft px-2.5 py-0.5 text-[12px] text-deny">Incident: {v.incident.title}</span>}
      </div>
      <div className="mt-5 flex flex-col items-stretch gap-2">
        <div className="flex items-center gap-3 rounded-xl border border-line bg-ink-850 px-4 py-3">
          <UserRound className="size-5 text-fg-muted" /><div><p className="text-[15px] text-fg">{v.citizen.first_name} asked: “{v.request.text}”</p><p className="text-[12px] text-fg-subtle">{v.request.service} · {v.citizen.ref}</p></div>
        </div>
        {v.lanes.map((l: any) => (
          <div key={l.mandate_id} className="flex flex-col items-stretch gap-2">
            <ArrowDown className="mx-auto size-4 text-fg-subtle" />
            <button onClick={() => setSel(l.mandate_id)} className={clsx("flex flex-wrap items-center gap-3 rounded-xl border px-4 py-3 text-left transition-colors", sel === l.mandate_id ? "border-trust/60 bg-ink-750" : "border-line bg-ink-850 hover:border-line-strong", l.delegated_from && "ml-6")}>
              <Bot className="size-5 text-trust" />
              <div className="min-w-0 flex-1"><p className="text-[15px] font-medium text-fg">{l.agent_name}{l.delegated_from ? " — delegated" : ""}</p><p className="text-[12.5px] text-fg-muted">{l.explanation}</p></div>
              <Pill state={l.state} />
            </button>
            {l.actions.length > 0 && (
              <div className={clsx("flex flex-wrap gap-2", l.delegated_from ? "ml-12" : "ml-6")}>
                {l.actions.map((a: any) => (
                  <button key={a.technical.event_id} onClick={() => setSel(a.technical.event_id)} className={clsx("flex items-center gap-2 rounded-lg border px-3 py-2 text-left", sel === a.technical.event_id ? "border-trust/60 bg-ink-750" : "border-line bg-ink-900/60 hover:border-line-strong")}>
                    <Building2 className="size-4 text-fg-subtle" /><span className="text-[12.5px] text-fg">{a.service}</span><Pill state={a.state} />
                  </button>
                ))}
              </div>
            )}
          </div>
        ))}
        {v.denied_delegations.map((d: any) => (
          <button key={d.technical.event_id} onClick={() => setSel(null)} className="ml-6 rounded-lg border border-deny/30 bg-deny-soft px-3 py-2 text-left text-[12.5px] text-deny">{d.explanation} <span className="font-mono text-[11px]">({d.technical.reason_codes.join(", ")})</span></button>
        ))}
      </div>
      <div className="mt-4 flex flex-wrap gap-2">{v.legend.map((s: string) => <Pill key={s} state={s} />)}</div>
      {selected && (
        <div className="mt-5 rounded-xl border border-line bg-ink-900/70 p-4">
          <p className="text-[14px] font-medium text-fg">{selected.title}</p>
          <p className="mt-1 text-[13.5px] text-fg">{selected.explanation}</p>
          <details className="mt-2"><summary className="cursor-pointer text-[12px] text-fg-muted">Technical details</summary>
            <pre className="mt-2 overflow-x-auto font-mono text-[11px] text-fg-muted">{JSON.stringify(selected.technical, null, 1)}</pre></details>
        </div>
      )}
      <p className="mt-3 text-[11px] text-fg-subtle">Source: {v.source}. Live, refreshed every 3 s.</p>
    </div>
  );
}
