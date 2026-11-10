/* eslint-disable @typescript-eslint/no-explicit-any */
import clsx from "clsx";
import { Ban, Loader2, Search } from "lucide-react";
import { useEffect, useState } from "react";
import { Card, CardHeader } from "@/components/ui";
import { ApiError, officerRequest } from "@/lib/api";

type Scope = "mandate" | "mandate_tree" | "case" | "agent";
const SCOPES: [Scope, string, string][] = [
  ["mandate", "Single mandate", "Only this mandate. Its children stay on record but fail chain verification on use."],
  ["mandate_tree", "Mandate + dependent delegations", "This mandate and every child mandate issued from it."],
  ["case", "One citizen case", "Every mandate bound to this case. Other citizens' cases are untouched."],
  ["agent", "Agent identity", "Suspends the registered identity across all cases (reversible). Supervisor only."],
];
const AGENTS = ["AGT-RES-001", "AGT-INS-001", "AGT-INS-002", "AGT-PAY-001"];

/** Precise incident-response controls with a blast-radius preview from stored records (officer session required). */
export function PreciseRevocation() {
  const [scope, setScope] = useState<Scope>("case");
  const [cases, setCases] = useState<any[]>([]);
  const [target, setTarget] = useState("");
  const [preview, setPreview] = useState<any | null>(null);
  const [result, setResult] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);
  useEffect(() => { officerRequest<any[]>("/api/officer/cases").then(setCases).catch(() => undefined); }, [result]);
  const api = scope === "mandate_tree" || scope === "mandate" ? "mandate" : scope;
  const cascade = scope !== "mandate";
  const run = async (label: string, fn: () => Promise<any>) => {
    setBusy(label); setErr(null);
    try { return await fn(); } catch (e) { setErr(e instanceof ApiError ? `${e.code}: ${e.message}` : String(e)); return null; } finally { setBusy(null); }
  };
  const doPreview = () => run("preview", async () => { setResult(null); setPreview(await officerRequest(`/api/officer/revocation/preview?scope=${api}&target=${encodeURIComponent(target)}&cascade=${cascade}`)); });
  const doRevoke = () => run("revoke", async () => {
    const reason = "precise revocation from Security Operations";
    const r: any = api === "case" ? await officerRequest(`/api/officer/cases/${target}/revoke-authority`, "POST", { reason })
      : api === "agent" ? await officerRequest(`/api/officer/agents/${target}/suspend`, "POST", { reason })
        : await officerRequest(`/api/officer/mandates/${target}/revoke`, "POST", { reason, cascade });
    setResult(api === "agent" ? `Agent ${target} suspended.` : `Revoked ${r.revoked.length} mandate(s): ${r.revoked.join(", ") || "none (already revoked)"}`);
  });
  const caseOptions = cases.filter((c) => !c.authority_revoked);
  return (
    <Card>
      <CardHeader icon={Ban} title="Precise revocation" subtitle="Preview the exact blast radius from stored records, then act. Every action is checked by the backend and audited." />
      <div className="space-y-4 p-5">
        <div className="grid gap-2 sm:grid-cols-2 xl:grid-cols-4">{SCOPES.map(([k, l, d]) => (
          <button key={k} onClick={() => { setScope(k); setTarget(""); setPreview(null); setResult(null); }} className={clsx("rounded-xl border p-3 text-left", scope === k ? "border-trust/60 bg-ink-750" : "border-line bg-ink-850 hover:border-line-strong")}>
            <p className="text-[13px] font-medium text-fg">{l}</p><p className="mt-1 text-[11.5px] text-fg-subtle">{d}</p>
          </button>
        ))}</div>
        <div className="flex flex-wrap items-center gap-2">
          {scope === "case" ? (
            <select value={target} onChange={(e) => setTarget(e.target.value)} className="rounded-lg border border-line bg-ink-900 px-3 py-1.5 text-[13px] text-fg">
              <option value="">Select a case…</option>{caseOptions.map((c) => <option key={c.case_id} value={c.case_id}>{c.case_id} · {c.citizen_ref} · {c.state}</option>)}
            </select>
          ) : scope === "agent" ? (
            <select value={target} onChange={(e) => setTarget(e.target.value)} className="rounded-lg border border-line bg-ink-900 px-3 py-1.5 text-[13px] text-fg">
              <option value="">Select an agent…</option>{AGENTS.map((a) => <option key={a}>{a}</option>)}
            </select>
          ) : (
            <input value={target} onChange={(e) => setTarget(e.target.value.trim())} placeholder="Mandate ID, e.g. MND-DLG-… (see Delegation Network)" className="w-[380px] max-w-full rounded-lg border border-line bg-ink-900 px-3 py-1.5 font-mono text-[12.5px] text-fg" />
          )}
          <button onClick={doPreview} disabled={!target || busy !== null} className="inline-flex items-center gap-1.5 rounded-lg border border-line px-3 py-1.5 text-[12.5px] text-fg-muted disabled:opacity-40">{busy === "preview" ? <Loader2 className="size-3.5 animate-spin" /> : <Search className="size-3.5" />} Preview impact</button>
          <button onClick={doRevoke} disabled={!preview || busy !== null} className="inline-flex items-center gap-1.5 rounded-lg border border-deny/50 px-3 py-1.5 text-[12.5px] text-deny disabled:opacity-40">{busy === "revoke" && <Loader2 className="size-3.5 animate-spin" />}{scope === "agent" ? "Suspend agent identity" : "Revoke"}</button>
        </div>
        {err && <p className="text-[12.5px] text-deny">{err}</p>}
        {preview && (
          <div className="grid gap-4 rounded-xl border border-line bg-ink-900/60 p-4 text-[12.5px] md:grid-cols-3">
            <div><p className="text-[11px] uppercase tracking-wider text-fg-subtle">Mandates affected</p>
              <ul className="mt-1 space-y-0.5 font-mono text-[11.5px]">{preview.mandates.length ? preview.mandates.map((m: any) => <li key={m.mandate_id} className={m.already_revoked ? "text-fg-subtle line-through" : "text-fg"}>{m.mandate_id} · {m.agent_id}{m.delegated ? " · delegated" : ""}</li>) : <li className="text-fg-muted">Identity-level (no mandate is revoked)</li>}</ul></div>
            <div><p className="text-[11px] uppercase tracking-wider text-fg-subtle">Cases affected</p>
              <ul className="mt-1 space-y-0.5 font-mono text-[11.5px] text-fg">{preview.affected_cases.map((c: any) => <li key={c.case_id}>{c.case_id} · {c.citizen_ref}</li>)}</ul></div>
            <div><p className="text-[11px] uppercase tracking-wider text-fg-subtle">Not affected</p><p className="mt-1 text-[20px] font-semibold text-trust">{preview.unaffected_active_cases}</p><p className="text-fg-muted">other active cases keep their authority</p></div>
            <p className="text-[11px] text-fg-subtle md:col-span-3">Version-scoped revocation: {preview.version_scope}.</p>
          </div>
        )}
        {result && <p className="rounded-lg border border-trust/30 bg-trust-soft px-3 py-2 text-[13px] text-trust">{result}</p>}
      </div>
    </Card>
  );
}
