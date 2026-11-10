/* eslint-disable @typescript-eslint/no-explicit-any */
import clsx from "clsx";
import { CheckCircle2, FilePen, Loader2, ShieldAlert, ShieldCheck, XCircle } from "lucide-react";
import { Fragment, useEffect, useState } from "react";
import { Badge, Card, CardHeader, Notice, PageHeader, SyntheticBadge } from "@/components/ui";
import { ApiError, apiGet, apiPost, hasOfficerToken, officerRequest } from "@/lib/api";

const EXAMPLE = "The insurance agent may verify coverage only for the citizen in the current case, and no more than five times.";
const FIELDS: [string, string][] = [["agent_role", "Agent role"], ["permitted_action", "Permitted action"], ["citizen_scope", "Citizen scope"],
  ["case_scope", "Case scope"], ["action_limit", "Action limit"], ["expiration_minutes", "Expiration (min)"], ["receiving_service", "Receiving service"],
  ["required_approval_level", "Required approval"]];

export function PolicyDrafting() {
  const [text, setText] = useState(EXAMPLE);
  const [list, setList] = useState<any[]>([]);
  const [sel, setSel] = useState<any | null>(null);
  const [ver, setVer] = useState<any | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const load = () => apiGet<any[]>("/api/policies").then(setList).catch(() => undefined);
  useEffect(() => { load(); }, []);
  const act = async (label: string, fn: () => Promise<any>) => {
    setBusy(label); setErr(null);
    try { const r = await fn(); if (r?.policy_id) { setSel(r); setVer(null); } await load(); }
    catch (e) { setErr(e instanceof ApiError ? `${e.code}: ${e.message}` : String(e)); } finally { setBusy(null); }
  };
  return (
    <>
      <PageHeader eyebrow="Service owners" title="Policy Drafting" titleAr="صياغة السياسات"
        description="Describe a rule in plain language. WAKALA turns it into a structured draft, validates it, checks it against existing authority, and only an authenticated officer of the owning entity can approve it — signed with that entity's issuer key."
        actions={<SyntheticBadge />} />
      <Notice tone="warn" icon={ShieldAlert} title="Draft-only demonstration — approved policies are signed but NOT enforced">
        A restricted, deterministic template parser (no AI model) produces the draft; unrecognised wording is rejected, never guessed. Approval never replaces existing authorization policy. Wiring approved drafts into enforcement is not implemented.
      </Notice>
      {err && <p className="rounded-xl border border-deny/30 bg-deny-soft px-4 py-2.5 text-[13px] text-deny">{err}</p>}
      <div className="grid gap-6 xl:grid-cols-[1fr_360px]">
        <div className="space-y-6">
          <Card>
            <CardHeader icon={FilePen} title="Plain-language rule" />
            <div className="space-y-3 p-5">
              <textarea value={text} onChange={(e) => setText(e.target.value)} rows={3} maxLength={400} className="w-full rounded-xl border border-line bg-ink-900 p-3 text-[14px] text-fg" />
              <button onClick={() => act("draft", () => apiPost("/api/policies/drafts", { text }))} disabled={busy !== null} className="inline-flex items-center gap-1.5 rounded-lg bg-trust px-4 py-2 text-[13px] font-medium text-ink-950 disabled:opacity-40">{busy === "draft" && <Loader2 className="size-4 animate-spin" />}Create structured draft</button>
              <p className="text-[11.5px] text-fg-subtle">Supported: “The (insurance|residency|payment) agent may (verify coverage | check eligibility | complete the renewal | collect the fee) only for the citizen in the current case, no more than N times[, within N minutes|hours][, with officer|supervisor approval].”</p>
            </div>
          </Card>
          {sel && (
            <Card>
              <CardHeader icon={sel.valid ? ShieldCheck : XCircle} title={`${sel.policy_id} · ${sel.status.replace(/_/g, " ")}`} subtitle={sel.drafted_by} />
              <div className="space-y-4 p-5">
                <p className="rounded-xl border border-line bg-ink-850 p-3 text-[14px] text-fg">{sel.human_summary}</p>
                <dl className="grid gap-x-4 gap-y-1.5 text-[12.5px] sm:grid-cols-[170px_1fr]">{FIELDS.map(([k, l]) => <Fragment key={k}><dt className="text-fg-subtle">{l}</dt><dd className="font-mono text-fg">{sel.draft[k] ?? "—"}</dd></Fragment>)}</dl>
                {[["Errors", sel.validation.errors, "text-deny"], ["Conflicts", sel.validation.conflicts, "text-deny"], ["Warnings", sel.validation.warnings, "text-warn"]].map(([l, items, cls]) => (items as string[]).length > 0 && (
                  <div key={l as string}><p className="text-[12px] uppercase tracking-wider text-fg-subtle">{l as string}</p><ul className={clsx("list-disc pl-5 text-[12.5px]", cls as string)}>{(items as string[]).map((x) => <li key={x}>{x}</li>)}</ul></div>
                ))}
                {sel.status === "draft" && (
                  <div className="flex flex-wrap items-center gap-2 border-t border-line pt-3">
                    <button disabled={!hasOfficerToken() || busy !== null} onClick={() => act("approve", () => officerRequest(`/api/policies/${sel.policy_id}/decision`, "POST", { approve: true, note: "approved in Policy Drafting" }))} className="rounded-lg border border-trust/50 px-3 py-1.5 text-[12.5px] text-trust disabled:opacity-40">Approve & sign</button>
                    <button disabled={!hasOfficerToken() || busy !== null} onClick={() => act("reject", () => officerRequest(`/api/policies/${sel.policy_id}/decision`, "POST", { approve: false, note: "rejected" }))} className="rounded-lg border border-deny/50 px-3 py-1.5 text-[12.5px] text-deny disabled:opacity-40">Reject</button>
                    <span className="text-[11.5px] text-fg-subtle">{hasOfficerToken() ? "Signed in — the backend checks your role and entity." : "Sign in on Security Operations as the owning entity's officer (insurance: OFF-0202)."}</span>
                  </div>
                )}
                {sel.signature && (
                  <div className="rounded-lg border border-trust/30 bg-trust-soft/40 p-3 text-[12px]">
                    <p className="text-fg">Approved by {sel.approval.officer_id} · signed {sel.signature.algorithm} by {sel.signature.issuer_id} ({sel.signature.key_id})</p>
                    <p className="mt-1 break-all font-mono text-[10.5px] text-fg-subtle">{sel.signature.value}</p>
                    <button onClick={async () => setVer(await apiGet(`/api/policies/${sel.policy_id}/verify`))} className="mt-2 text-trust hover:underline">Verify signature now</button>
                    {ver && <p className={clsx("mt-1 flex items-center gap-1", ver.valid ? "text-trust" : "text-deny")}>{ver.valid ? <CheckCircle2 className="size-4" /> : <XCircle className="size-4" />}signature {String(ver.signature_valid)} · matches stored draft {String(ver.body_matches_stored_draft)}</p>}
                  </div>
                )}
              </div>
            </Card>
          )}
        </div>
        <Card>
          <CardHeader icon={FilePen} title="Drafts" />
          <ul className="divide-y divide-line">{list.length === 0 ? <li className="px-4 py-3 text-[12.5px] text-fg-subtle">None yet.</li> : list.map((p) => (
            <li key={p.policy_id}><button onClick={() => { setSel(p); setVer(null); }} className={clsx("w-full px-4 py-2.5 text-left hover:bg-ink-800", sel?.policy_id === p.policy_id && "bg-ink-750")}>
              <span className="flex items-center gap-2"><Badge tone={p.status.startsWith("approved") ? "trust" : p.status === "draft" ? "warn" : "deny"}>{p.status.replace(/_/g, " ")}</Badge><span className="font-mono text-[11px] text-fg-subtle">{p.policy_id}</span></span>
              <span className="mt-1 block truncate text-[12px] text-fg-muted">{p.source_text}</span>
            </button></li>
          ))}</ul>
        </Card>
      </div>
    </>
  );
}
