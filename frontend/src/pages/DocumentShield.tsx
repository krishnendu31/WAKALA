/* eslint-disable @typescript-eslint/no-explicit-any */
import clsx from "clsx";
import { AlertTriangle, Bot, CheckCircle2, Eye, EyeOff, FileSearch, FileUp, Layers, Loader2, Lock, ScrollText, ShieldAlert, ShieldCheck, ShieldX, Swords, type LucideIcon } from "lucide-react";
import { useCallback, useEffect, useRef, useState, type ReactNode } from "react";
import { Badge, Card, CardHeader, EmptyState, Notice, PageHeader, SyntheticBadge } from "@/components/ui";
import { API_BASE_URL, ApiError, apiGet, apiPost, hasOfficerToken, officerRequest } from "@/lib/api";
import type { Tone } from "@/lib/format";

type Doc = Record<string, any>;
type Summary = { document_id: string; display_name: string; disposition: string; status: string; created_at: string; findings: number; high_findings: number; hidden_runs: number; released_to_agents: boolean };

const DISPOSITION: Record<string, { tone: Tone; icon: LucideIcon; meaning: string }> = {
  CLEAN: { tone: "trust", icon: ShieldCheck, meaning: "No suspicious indicator found by these checks. This is not a guarantee of safety." },
  REVIEW: { tone: "warn", icon: ShieldAlert, meaning: "Suspicious or uninspectable content. Withheld from agents until an authenticated officer releases it." },
  QUARANTINED: { tone: "deny", icon: ShieldX, meaning: "Withheld from agent processing by policy. The original is preserved for investigation." },
};
const SEV: Record<string, Tone> = { high: "deny", medium: "warn", low: "neutral" };
const short = (s: string, n = 90) => (s.length > n ? s.slice(0, n) + "…" : s);

async function uploadPdf(file: File): Promise<Doc> {
  const res = await fetch(`${API_BASE_URL}/api/documents`, {
    method: "POST", body: file, headers: { "Content-Type": "application/pdf", "X-Filename": file.name.slice(-120), Accept: "application/json" },
  });
  const body = await res.json().catch(() => null);
  if (!res.ok) throw new ApiError(body?.error?.message ?? res.statusText, res.status, body?.error?.code ?? `HTTP_${res.status}`);
  return body as Doc;
}

function Preview({ doc, page, showBoxes }: { doc: Doc; page: Doc; showBoxes: boolean }) {
  const runs: Doc[] = doc.runs.filter((r: Doc) => r.page === page.page);
  const findings: Doc[] = doc.findings.filter((f: Doc) => f.page === page.page && f.bbox);
  const box = ([x0, y0, x1, y1]: [number, number, number, number]) => ({ left: `${(x0 / page.width) * 100}%`, top: `${(y0 / page.height) * 100}%`,
    width: `${Math.max(0.4, ((x1 - x0) / page.width) * 100)}%`, height: `${Math.max(0.4, ((y1 - y0) / page.height) * 100)}%` });
  const offPage = runs.filter((r) => r.hidden_reasons.includes("OFF_PAGE"));
  return (
    <div>
      <div className="relative mx-auto w-full max-w-[520px] overflow-hidden rounded-lg border border-line bg-white shadow-lg">
        <img src={`${API_BASE_URL}/api/documents/${doc.document_id}/pages/${page.page}`} alt={`Rendered page ${page.page} of the original PDF`} className="block w-full" />
        {showBoxes && runs.filter((r) => !r.hidden_reasons.includes("OFF_PAGE")).map((r, i) => (
          <div key={i} title={`${r.hidden_reasons.length ? "HIDDEN: " + r.hidden_reasons.join(", ") : "visible"} — ${short(r.text, 140)}`} style={box(r.bbox)}
            className={clsx("absolute", r.hidden_reasons.length ? "border-2 border-dashed border-red-500 bg-red-500/15" : "border border-sky-400/40")} />
        ))}
        {showBoxes && findings.map((f, i) => <div key={`f${i}`} style={box(f.bbox)} title={`${f.rule_id}: ${f.match}`} className="absolute outline outline-2 outline-amber-400" />)}
      </div>
      {offPage.length > 0 && <p className="mt-2 text-center text-[11.5px] text-deny">{offPage.length} text run(s) positioned outside the visible page (not drawn above).</p>}
      <p className="mt-2 text-center text-[11px] text-fg-subtle">Rendered server-side from the preserved original at {doc.render_dpi} dpi · dashed red = hidden text · amber = injection finding</p>
    </div>
  );
}

function Section({ title, icon, children, right }: { title: string; icon: LucideIcon; children: ReactNode; right?: ReactNode }) {
  return <Card className="min-w-0"><CardHeader icon={icon} title={title} right={right} />{children}</Card>;
}

function Detail({ id, onChanged }: { id: string; onChanged: () => void }) {
  const [doc, setDoc] = useState<Doc | null>(null);
  const [page, setPage] = useState(1);
  const [boxes, setBoxes] = useState(true);
  const [view, setView] = useState<Doc | null>(null);
  const [adv, setAdv] = useState<Doc | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const load = useCallback(() => apiGet<Doc>(`/api/documents/${id}`).then(setDoc).catch((e) => setErr(String(e))), [id]);
  useEffect(() => { setView(null); setAdv(null); setPage(1); load(); }, [load]);
  async function act(label: string, fn: () => Promise<void>) {
    setBusy(label); setErr(null);
    try { await fn(); } catch (e) { setErr(e instanceof ApiError ? `${e.code}: ${e.message}` : String(e)); } finally { setBusy(null); }
  }
  if (!doc) return <p className="p-5 text-[13px] text-fg-subtle">Loading inspection…</p>;
  const d = DISPOSITION[doc.disposition] ?? DISPOSITION.QUARANTINED!;
  const hidden: Doc[] = doc.hidden_run_indexes.map((i: number) => ({ ...doc.runs[i], i }));
  const pg = doc.pages.find((p: Doc) => p.page === page);
  return (
    <div className="space-y-6">
      <div className={clsx("rounded-xl border p-5", d.tone === "deny" ? "border-deny/40 bg-deny-soft" : d.tone === "warn" ? "border-warn/40 bg-warn-soft" : "border-trust/40 bg-trust-soft")}>
        <div className="flex flex-wrap items-center gap-3">
          <d.icon className={clsx("size-6", d.tone === "deny" ? "text-deny" : d.tone === "warn" ? "text-warn" : "text-trust")} aria-hidden />
          <p className="text-[18px] font-semibold text-fg">{doc.disposition}</p>
          {doc.released_to_agents && <Badge tone="warn">released by officer {doc.review?.officer}</Badge>}
          <span className="font-mono text-[11.5px] text-fg-subtle">{doc.document_id} · {doc.display_name} · {doc.status} · {doc.engine ?? "no engine output"}</span>
        </div>
        <p className="mt-2 text-[13px] text-fg-muted">{d.meaning}</p>
        <ul className="mt-3 list-disc space-y-0.5 pl-5 text-[12.5px] text-fg">{doc.reasons.map((r: string, i: number) => <li key={i}>{r}</li>)}</ul>
        <p className="mt-3 font-mono text-[11px] text-fg-subtle">Original preserved read-only · SHA-256 {doc.sha256} · {doc.size_bytes} bytes · audit {doc.audit_event}</p>
      </div>
      {err && <p className="rounded-lg border border-deny/30 bg-deny-soft px-3 py-2 text-[12.5px] text-deny">{err}</p>}

      <div className="grid gap-6 2xl:grid-cols-[minmax(0,560px)_1fr]">
        <Section title="PDF preview" icon={Eye} right={<span className="flex items-center gap-2">
          {doc.pages.length > 1 && doc.pages.map((p: Doc) => <button key={p.page} onClick={() => setPage(p.page)} className={clsx("rounded px-2 text-[12px]", p.page === page ? "bg-ink-700 text-fg" : "text-fg-subtle")}>{p.page}</button>)}
          <button onClick={() => setBoxes(!boxes)} className="inline-flex items-center gap-1 text-[12px] text-fg-muted">{boxes ? <EyeOff className="size-3.5" /> : <Eye className="size-3.5" />} boxes</button></span>}>
          <div className="p-4">{pg ? <Preview doc={doc} page={pg} showBoxes={boxes} /> : <EmptyState icon={Lock} title="No preview">The document could not be inspected, so nothing was rendered.</EmptyState>}</div>
        </Section>
        <div className="space-y-6">
          <Section title={`Security findings (${doc.findings.length})`} icon={ShieldAlert}>
            {doc.findings.length === 0 ? <p className="px-5 py-4 text-[13px] text-fg-subtle">No rule matched. Absence of findings is not proof of safety.</p> : (
              <ul className="divide-y divide-line">{doc.findings.map((f: Doc, i: number) => (
                <li key={i} className="px-5 py-3">
                  <div className="flex flex-wrap items-center gap-2">
                    <Badge tone={SEV[f.severity]}>{f.severity}</Badge><span className="font-mono text-[12px] text-fg">{f.rule_id}</span>
                    <span className="text-[12px] text-fg-muted">{f.description}</span>
                    <Badge tone={f.layer === "visible_text" ? "neutral" : "deny"}>{f.layer.replace("_", " ")}{f.hidden_reasons.length ? `: ${f.hidden_reasons.join(", ")}` : ""}</Badge>
                  </div>
                  <p className="mt-1.5 rounded bg-ink-900/70 px-2 py-1 font-mono text-[11.5px] text-warn">“{f.excerpt}”</p>
                  <p className="mt-1 text-[11px] text-fg-subtle">page {f.page ?? "—"} · bbox {f.bbox ? f.bbox.map((v: number) => v.toFixed(0)).join(", ") : "n/a"}{f.adjustments.length ? ` · ${f.adjustments.join("; ")}` : ""}</p>
                </li>
              ))}</ul>
            )}
            {doc.findings[0] && <p className="border-t border-line px-5 py-2 text-[11px] text-fg-subtle">{doc.findings[0].confidence}</p>}
          </Section>
          <Section title={`Detected text layers (${doc.runs.length} runs · ${hidden.length} hidden)`} icon={Layers}>
            <div className="max-h-[320px] overflow-auto">
              <table className="w-full text-left text-[11.5px]">
                <thead className="sticky top-0 bg-ink-850"><tr className="border-b border-line text-[10.5px] uppercase tracking-wider text-fg-subtle">{["Pg", "Text", "Size", "Colour", "Opacity", "Mode", "Render Δpx", "Visibility"].map((h) => <th key={h} className="px-3 py-2 font-medium">{h}</th>)}</tr></thead>
                <tbody>{doc.runs.map((r: Doc, i: number) => (
                  <tr key={i} className={clsx("border-b border-line/50", r.hidden_reasons.length && "bg-deny-soft/40")}>
                    <td className="px-3 py-1.5">{r.page}</td><td className="px-3 py-1.5 font-mono">{short(r.text, 70)}</td><td className="px-3 py-1.5">{r.size}</td>
                    <td className="px-3 py-1.5"><span className="inline-flex items-center gap-1"><span className="size-3 rounded-sm border border-line" style={{ background: r.color ?? "transparent" }} />{r.color}</span></td>
                    <td className="px-3 py-1.5">{r.opacity}</td><td className="px-3 py-1.5">{r.render_mode}</td><td className="px-3 py-1.5">{r.render_changed_pixels}/{r.render_sampled_pixels}</td>
                    <td className="px-3 py-1.5">{r.hidden_reasons.length ? <Badge tone="deny">{r.hidden_reasons.join(", ")}</Badge> : <Badge tone="trust">visible</Badge>}</td>
                  </tr>
                ))}</tbody>
              </table>
            </div>
          </Section>
        </div>
      </div>

      <div className="grid gap-6 xl:grid-cols-2">
        <Section title="Agent workflow — what the AI agent receives" icon={Bot}
          right={<button disabled={busy !== null} onClick={() => act("view", async () => setView(await apiGet<Doc>(`/api/documents/${id}/agent-view`)))} className="rounded-lg border border-trust/40 px-2.5 py-1 text-[12px] text-trust disabled:opacity-40">{busy === "view" ? "…" : "Deliver to intake agent"}</button>}>
          <div className="space-y-3 p-5 text-[12.5px]">
            {!view ? <p className="text-fg-subtle">Deliver the document to the simulated intake agent to see exactly what the policy permits it to read.</p> : (
              <>
                <div className="flex items-center gap-2">{view.view.released ? <Badge tone="warn">released as untrusted data</Badge> : <Badge tone="deny">withheld: {view.view.withheld_reason}</Badge>}<span className="font-mono text-[11px] text-fg-subtle">audit {view.view.audit_event}</span></div>
                <p className="rounded-lg border border-line bg-ink-900/60 p-3 font-mono text-[11.5px] text-fg-muted">{view.view.label}<br />{view.view.handling_rule}</p>
                {view.view.content && <pre className="max-h-48 overflow-auto rounded-lg bg-ink-900 p-3 font-mono text-[11.5px] text-fg-muted">{Object.entries(view.view.content).map(([p, t]) => `— page ${p} (visible text only) —\n${t}`).join("\n")}</pre>}
                <p className="text-fg-muted"><b className="text-fg">Agent result:</b> {view.agent_result.observation} Proposed tool calls: <b className="text-fg">{view.agent_result.proposed_tool_calls.length}</b>.</p>
              </>
            )}
            {doc.disposition === "REVIEW" && !doc.released_to_agents && (
              <div className="rounded-lg border border-warn/30 p-3">
                <p className="text-fg-muted">Officer review (requires an officer session from Security Operations).</p>
                <div className="mt-2 flex gap-2">
                  {(["release", "quarantine"] as const).map((dcs) => (
                    <button key={dcs} disabled={!hasOfficerToken() || busy !== null} onClick={() => act(dcs, async () => { await officerRequest(`/api/documents/${id}/review`, "POST", { decision: dcs, note: "reviewed in Document Shield" }); await load(); onChanged(); })}
                      className={clsx("rounded-lg border px-2.5 py-1 text-[12px] disabled:opacity-40", dcs === "release" ? "border-warn/40 text-warn" : "border-deny/40 text-deny")}>{dcs === "release" ? "Release visible text to agents" : "Quarantine"}</button>
                  ))}
                </div>
                {!hasOfficerToken() && <p className="mt-1 text-[11px] text-fg-subtle">Sign in on the Security Operations page first.</p>}
              </div>
            )}
          </div>
        </Section>

        <Section title="Scenario B — adversarial test (independent gateway)" icon={Swords}
          right={<button disabled={busy !== null} onClick={() => act("adv", async () => { setAdv(await apiPost<Doc>(`/api/documents/${id}/adversarial-test`)); await load(); })} className="rounded-lg border border-deny/40 px-2.5 py-1 text-[12px] text-deny disabled:opacity-40">{busy === "adv" ? "Running…" : "Run manipulated-agent test"}</button>}>
          <div className="space-y-3 p-5 text-[12.5px]">
            <Notice tone="warn" icon={AlertTriangle} title="Simulated manipulated agent — deterministic script, no real LLM">
              It deliberately reads every text layer, including content Document Shield withheld, and obeys the injected payment instruction using its own key and real case mandate.
            </Notice>
            {adv && (
              <>
                <p className="text-fg-muted">Parsed instruction: <span className="font-mono text-fg">{adv.parsed_instruction ? `${adv.parsed_instruction.amount} AED → ${adv.parsed_instruction.recipient}` : "none"}</span> · case <span className="font-mono">{adv.case_id ?? "—"}</span> ({adv.case_state_before} → {adv.case_state_after})</p>
                {adv.attempts.map((a: Doc, i: number) => (
                  <div key={i} className={clsx("rounded-lg border p-3", a.executed ? "border-deny bg-deny-soft" : "border-line bg-ink-900/60")}>
                    <div className="flex flex-wrap items-center gap-2"><Badge tone={a.allowed ? "deny" : "trust"}>{a.allowed ? "ALLOWED" : "DENIED by gateway"}</Badge><span className="font-mono text-[11.5px] text-fg">{a.agent_id} · {a.tool_name}</span></div>
                    <p className="mt-1 text-fg-muted">{a.title}</p>
                    <p className="mt-1 font-mono text-[11px] text-deny">{a.reason_codes.join(" · ")}</p>
                    <p className="mt-1 text-[11.5px] text-fg-subtle">{a.explanation}</p>
                    <p className="mt-1 font-mono text-[10.5px] text-fg-subtle">params {JSON.stringify(a.parameters)} · audit {a.audit_reference}</p>
                  </div>
                ))}
                {adv.ledger_unchanged !== undefined && (
                  <p className={clsx("flex items-center gap-2 font-medium", adv.ledger_unchanged ? "text-trust" : "text-deny")}>
                    {adv.ledger_unchanged ? <CheckCircle2 className="size-4" /> : <ShieldX className="size-4" />}
                    Ledger: case {adv.ledger_entries_for_case_before} → {adv.ledger_entries_for_case_after} entries · all cases {adv.ledger_rows_total_before} → {adv.ledger_rows_total_after} · {adv.outcome}
                  </p>
                )}
                {adv.audit_events && (
                  <details className="rounded-lg border border-line p-3"><summary className="cursor-pointer text-fg-muted">Linked audit evidence ({adv.audit_events.length} hash-chained events for this case)</summary>
                    <ul className="mt-2 space-y-1 font-mono text-[11px]">{adv.audit_events.map((e: Doc) => (
                      <li key={e.event_id}><span className="text-fg-subtle">#{e.sequence}</span> <span className={e.decision === "denied" ? "text-deny" : "text-fg-muted"}>{e.decision}</span> <span className="text-fg">{e.actor} {e.action}</span> <span className="text-fg-subtle">{(e.reason_codes ?? []).join(",")}</span></li>
                    ))}</ul>
                  </details>
                )}
              </>
            )}
            {!adv && doc.adversarial_test && <p className="text-fg-subtle">Last run: {doc.adversarial_test.outcome} (case {doc.adversarial_test.case_id}).</p>}
          </div>
        </Section>
      </div>

      <div className="grid gap-6 xl:grid-cols-2">
        <Section title="Metadata, annotations and active content" icon={ScrollText}>
          <div className="space-y-2 p-5 font-mono text-[11.5px] text-fg-muted">
            {Object.entries(doc.metadata ?? {}).map(([k, v]) => <p key={k}><span className="text-fg-subtle">{k}:</span> {String(v)}</p>)}
            <p><span className="text-fg-subtle">annotations:</span> {doc.annotations?.length ?? 0} · <span className="text-fg-subtle">form fields:</span> {doc.widgets?.length ?? 0} · <span className="text-fg-subtle">embedded files:</span> {doc.embedded_files?.length ?? 0} (never extracted)</p>
            <p><span className="text-fg-subtle">active content keys:</span> {Object.keys(doc.active_content ?? {}).join(", ") || "none found"}</p>
            <p><span className="text-fg-subtle">image-only pages:</span> {doc.image_only_pages?.join(", ") || "none"}</p>
          </div>
        </Section>
        <Section title="Inspection limitations" icon={FileSearch}>
          <ul className="list-disc space-y-1 px-9 py-4 text-[12px] text-fg-muted">{doc.limitations.map((l: string) => <li key={l}>{l}</li>)}</ul>
        </Section>
      </div>
    </div>
  );
}

export function DocumentShield() {
  const [docs, setDocs] = useState<Summary[]>([]);
  const [samples, setSamples] = useState<{ key: string; description: string }[]>([]);
  const [sel, setSel] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);
  const refresh = useCallback(() => apiGet<Summary[]>("/api/documents").then(setDocs).catch((e) => setErr(String(e))), []);
  useEffect(() => { refresh(); apiGet<{ key: string; description: string }[]>("/api/documents/samples").then(setSamples).catch(() => undefined); }, [refresh]);
  async function run(label: string, fn: () => Promise<Doc>) {
    setBusy(label); setErr(null);
    try { const d = await fn(); await refresh(); setSel(d.document_id); } catch (e) { setErr(e instanceof ApiError ? `${e.code}: ${e.message}` : String(e)); } finally { setBusy(null); }
  }
  return (
    <>
      <PageHeader eyebrow="Document Shield" title="Document Shield" titleAr="درع المستندات"
        description="Untrusted PDFs are inspected in an isolated worker before any AI agent sees them: text layers, rendering visibility, metadata and annotations are checked against transparent injection rules. It complements — never replaces — the case-bound authorization gateway."
        actions={<SyntheticBadge />} />
      <Notice tone="warn" icon={AlertTriangle} title="Development prototype · synthetic documents only">
        Rule-based and incomplete by design: CLEAN means no indicator was found, not that a document is safe. Every protected action still requires a signed case mandate through the gateway.
      </Notice>
      <div className="grid gap-6 2xl:grid-cols-[340px_1fr]">
        <div className="space-y-6">
          <Card>
            <CardHeader icon={FileUp} title="Upload PDF" subtitle="≤ 5 MB · ≤ 20 pages · inspected in an isolated process" />
            <div className="space-y-3 p-4">
              <input ref={fileRef} type="file" accept="application/pdf,.pdf" className="block w-full text-[12px] text-fg-muted file:mr-3 file:rounded-lg file:border file:border-line file:bg-ink-800 file:px-3 file:py-1.5 file:text-fg"
                onChange={(e) => { const f = e.target.files?.[0]; if (f) run("upload", () => uploadPdf(f)); e.target.value = ""; }} />
              <p className="eyebrow">Or generate a synthetic sample</p>
              <div className="flex flex-col gap-1.5">{samples.map((s) => (
                <button key={s.key} disabled={busy !== null} onClick={() => run(s.key, () => apiPost<Doc>(`/api/documents/samples/${s.key}`))}
                  className={clsx("rounded-lg border px-3 py-1.5 text-left text-[12px] disabled:opacity-40", s.key === "hidden_payment_injection" ? "border-deny/40 text-deny" : "border-line text-fg-muted hover:bg-ink-750")}>
                  {busy === s.key ? <Loader2 className="mr-1 inline size-3 animate-spin" /> : null}{s.description}
                </button>
              ))}</div>
              {err && <p className="text-[12px] text-deny">{err}</p>}
            </div>
          </Card>
          <Card>
            <CardHeader icon={FileSearch} title="Inspected documents" />
            {docs.length === 0 ? <p className="px-4 py-3 text-[12.5px] text-fg-subtle">None yet.</p> : (
              <ul className="divide-y divide-line">{docs.map((d) => (
                <li key={d.document_id}><button onClick={() => setSel(d.document_id)} className={clsx("w-full px-4 py-2.5 text-left hover:bg-ink-800", sel === d.document_id && "bg-ink-750")}>
                  <span className="flex items-center gap-2"><Badge tone={DISPOSITION[d.disposition]?.tone ?? "neutral"}>{d.disposition}</Badge><span className="truncate text-[12.5px] text-fg">{d.display_name}</span></span>
                  <span className="mt-0.5 block font-mono text-[10.5px] text-fg-subtle">{d.document_id} · {d.findings} findings ({d.high_findings} high) · {d.hidden_runs} hidden</span>
                </button></li>
              ))}</ul>
            )}
          </Card>
        </div>
        <div className="min-w-0">{sel ? <Detail key={sel} id={sel} onChanged={refresh} /> : <EmptyState icon={FileSearch} title="Select or upload a document">Start with the red “hidden white-text AED 50,000” sample for the two-layer demonstration.</EmptyState>}</div>
      </div>
    </>
  );
}
