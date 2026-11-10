/* eslint-disable @typescript-eslint/no-explicit-any */
import clsx from "clsx";
import { Eye, Loader2, Play, ShieldCheck } from "lucide-react";
import { useState } from "react";
import { Badge, Card, CardHeader, Notice, PageHeader, SyntheticBadge } from "@/components/ui";
import { ApiError, apiPost } from "@/lib/api";
import type { Tone } from "@/lib/format";

const CLS: Record<string, [string, Tone]> = {
  agreement: ["Agrees with source", "neutral"], would_block: ["Would block (source allowed)", "deny"],
  false_denial_candidate: ["False-denial candidate", "warn"], would_allow_where_source_denied: ["Would allow (source denied)", "warn"],
};

export function ShadowMode() {
  const [d, setD] = useState<any | null>(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [step, setStep] = useState<1 | 2>(1);
  const run = async () => { setBusy(true); setErr(null); try { setD(await apiPost<any>("/api/shadow/demo")); setStep(1); } catch (e) { setErr(e instanceof ApiError ? `${e.code}: ${e.message}` : String(e)); } finally { setBusy(false); } };
  const rep = d?.shadow.report;
  return (
    <>
      <PageHeader eyebrow="Adoption path" title="Shadow Mode" titleAr="وضع المراقبة"
        description="A government entity can evaluate WAKALA's policies on copies of its existing agent traffic before enforcing anything. Watch-only: WAKALA records what it would decide; the source system's decisions are never changed and nothing is executed."
        actions={<SyntheticBadge />} />
      <Notice tone="trust" icon={Eye} title="Counterfactual, not prevention">
        “Would block” means WAKALA's policy would have denied a copied event that the source system executed. Nothing was prevented in shadow mode. Enforcement is then demonstrated in a separate, fresh synthetic environment — never by weakening a live gateway.
      </Notice>
      {err && <p className="rounded-xl border border-deny/30 bg-deny-soft px-4 py-2.5 text-[13px] text-deny">{err}</p>}
      <div className="flex flex-wrap items-center gap-3">
        <button onClick={run} disabled={busy} className="inline-flex items-center gap-1.5 rounded-lg bg-trust px-4 py-2 text-[13.5px] font-medium text-ink-950 disabled:opacity-40">{busy ? <Loader2 className="size-4 animate-spin" /> : <Play className="size-4" />} Run shadow evaluation, then enforcement</button>
        {d && (["1 · Observe (shadow)", "2 · Enforce (separate environment)"] as const).map((l, i) => (
          <button key={l} onClick={() => setStep((i + 1) as 1 | 2)} className={clsx("rounded-lg border px-3 py-1.5 text-[12.5px]", step === i + 1 ? "border-trust/50 bg-ink-750 text-fg" : "border-line text-fg-subtle")}>{l}</button>
        ))}
      </div>
      {d && step === 1 && (
        <>
          <div className="grid gap-3 sm:grid-cols-3 xl:grid-cols-6">
            {[["Events observed", rep.events_observed], ["Would allow", rep.would_allow], ["Would deny", rep.would_deny], ["Agree with source", rep.agreements],
              ["Would block (source allowed)", rep.would_block_source_allowed], ["False-denial candidates", rep.false_denial_candidates.length]].map(([l, v]) => (
              <div key={l as string} className="card p-4"><p className="text-[11px] uppercase tracking-wider text-fg-subtle">{l}</p><p className="mt-1 text-[26px] font-semibold text-fg">{v}</p></div>
            ))}
          </div>
          <Card>
            <CardHeader icon={Eye} title="Copied events — source decision vs. what WAKALA would decide" subtitle={`${d.shadow.shadow_run_id} · source state unchanged during observation: ${d.shadow.isolation_check.source_state_unchanged_during_observation}`} />
            <div className="overflow-x-auto"><table className="w-full text-left text-[12.5px]">
              <thead><tr className="border-b border-line text-[11px] uppercase tracking-wider text-fg-subtle">{["#", "Event", "Source system", "WAKALA would", "Finding", "Why"].map((h) => <th key={h} className="px-4 py-2 font-medium">{h}</th>)}</tr></thead>
              <tbody>{d.shadow.events.map((r: any) => (
                <tr key={r.n} className="border-b border-line/60 align-top">
                  <td className="px-4 py-2 text-fg-subtle">{r.n}</td>
                  <td className="px-4 py-2 text-fg">{r.description}<br /><span className="font-mono text-[11px] text-fg-subtle">{r.agent_id} · {r.tool_name}</span></td>
                  <td className="px-4 py-2">{r.source_decision}</td>
                  <td className={clsx("px-4 py-2 font-medium", r.wakala_would === "allow" ? "text-trust" : "text-deny")}>{r.wakala_would}</td>
                  <td className="px-4 py-2"><Badge tone={CLS[r.classification]?.[1] ?? "neutral"}>{CLS[r.classification]?.[0] ?? r.classification}</Badge></td>
                  <td className="px-4 py-2 text-fg-muted">{r.plain_english}<br /><span className="font-mono text-[10.5px] text-fg-subtle">{r.reason_codes.join(", ")}</span></td>
                </tr>
              ))}</tbody>
            </table></div>
          </Card>
          <div className="grid gap-6 lg:grid-cols-2">
            <Card><CardHeader title="Potential policy conflicts" icon={Eye} />
              <ul className="space-y-2 px-5 py-4 text-[13px]">{rep.policy_conflicts.length ? rep.policy_conflicts.map((c: any) => <li key={c.event} className="text-fg">{c.conflict} <span className="font-mono text-[11px] text-fg-subtle">({c.event}: {c.codes.join(", ")})</span></li>) : <li className="text-fg-subtle">None found.</li>}</ul></Card>
            <Card><CardHeader title="Next steps for policy tuning" icon={ShieldCheck} />
              <ol className="list-decimal space-y-1.5 px-9 py-4 text-[13px] text-fg">{rep.next_steps.map((s: string) => <li key={s}>{s}</li>)}</ol></Card>
          </div>
        </>
      )}
      {d && step === 2 && (
        <Card>
          <CardHeader icon={ShieldCheck} title="Active enforcement" subtitle={d.enforcement.environment} />
          <p className="px-5 pt-3 text-[13.5px] text-fg">Shadow prediction matched enforcement on <b>{d.prediction_agreement.matched}/{d.prediction_agreement.total}</b> events · audit chain {d.enforcement.audit_chain_valid ? "valid" : "INVALID"} · ledger rows {d.enforcement.ledger_rows}</p>
          <ul className="divide-y divide-line px-5 py-3 text-[12.5px]">{d.enforcement.events.map((e: any, i: number) => (
            <li key={i} className="flex flex-wrap gap-3 py-1.5"><span className="w-36 font-mono text-fg-muted">{e.event}</span><span className={e.executed ? "text-trust" : "text-deny"}>{e.status}</span><span className="font-mono text-[11px] text-fg-subtle">{e.reason_codes.join(", ")}</span></li>
          ))}</ul>
        </Card>
      )}
    </>
  );
}
