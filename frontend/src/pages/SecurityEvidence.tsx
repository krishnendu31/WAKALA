/* eslint-disable @typescript-eslint/no-explicit-any */
import clsx from "clsx";
import { AlertTriangle, BarChart3, Calculator, CheckCircle2, Clock, Database, FileText, Gauge, LifeBuoy, ShieldCheck, ShieldX, type LucideIcon } from "lucide-react";
import { Fragment, useEffect, useMemo, useState, type ReactNode } from "react";
import { Bar, BarChart, CartesianGrid, Legend, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { ApiView, Badge, Card, CardHeader, EmptyState, Notice, PageHeader } from "@/components/ui";
import { useApi } from "@/hooks/useApi";
import { API_BASE_URL, ApiError, apiPost } from "@/lib/api";
import { humanize } from "@/lib/format";

type Rate = { numerator: number; denominator: number; rate: number | null };
type Summary = Record<string, any>;
const LABEL = "Synthetic prototype benchmark — not production government statistics.";
const CONFIGS = ["A", "B", "C"] as const;
const CONFIG_NAME: Record<string, string> = { A: "A · role-only baseline", B: "B · case-bound WAKALA", C: "C · full WAKALA" };
const COLORS: Record<string, string> = { A: "#f59e0b", B: "#a5b4fc", C: "#2dd4bf" };

const pct = (r?: Rate | null) => (r && r.denominator ? `${(100 * (r.rate ?? 0)).toFixed(1)}%` : "n/a");
const frac = (r?: Rate | null) => (r && r.denominator ? `${r.numerator}/${r.denominator}` : "0 applicable");
const ms = (x?: number) => (x === undefined ? "—" : x < 1 ? x.toFixed(3) : x < 100 ? x.toFixed(2) : x.toFixed(0));

function RateCell({ r, good }: { r?: Rate | null; good?: "high" | "low" }) {
  const v = r?.denominator ? r.rate ?? 0 : null;
  const tone = v === null || !good ? "text-fg" : (good === "high" ? v >= 0.999 : v <= 0.001) ? "text-trust" : "text-deny";
  return (
    <span className="tabular-nums">
      <span className={clsx("font-medium", tone)}>{pct(r)}</span> <span className="text-[11.5px] text-fg-subtle">{frac(r)}</span>
    </span>
  );
}

function Tile({ icon: Icon, label, value, note, tone }: { icon: LucideIcon; label: string; value: ReactNode; note: ReactNode; tone?: "trust" | "deny" | "warn" }) {
  return (
    <div className="card p-4">
      <div className="flex items-center justify-between"><p className="text-[12.5px] text-fg-muted">{label}</p><Icon className="size-4 text-fg-subtle" aria-hidden /></div>
      <p className={clsx("mt-2 text-[26px] font-semibold leading-none tabular-nums", tone === "trust" ? "text-trust" : tone === "deny" ? "text-deny" : tone === "warn" ? "text-warn" : "text-fg")}>{value}</p>
      <p className="mt-2 text-[11.5px] leading-snug text-fg-subtle">{note}</p>
    </div>
  );
}

function Table({ head, rows }: { head: ReactNode[]; rows: ReactNode[][] }) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full min-w-[640px] text-left text-[12.5px]">
        <thead><tr className="border-b border-line text-[11px] uppercase tracking-wider text-fg-subtle">{head.map((h, i) => <th key={i} className="px-4 py-2.5 font-medium">{h}</th>)}</tr></thead>
        <tbody>{rows.map((r, i) => <tr key={i} className="border-b border-line/60">{r.map((c, j) => <td key={j} className="px-4 py-2 align-top">{c}</td>)}</tr>)}</tbody>
      </table>
    </div>
  );
}

function Lat({ s }: { s?: Record<string, number> }) {
  if (!s || !s.n) return <span className="text-fg-subtle">—</span>;
  return <span className="font-mono text-[11.5px] tabular-nums">{ms(s.median_ms)} / {ms(s.p95_ms)} / {ms(s.p99_ms)} <span className="text-fg-subtle">· mean {ms(s.mean_ms)} · n={s.n}</span></span>;
}

// --- business calculator -------------------------------------------------------------------------------
const FIELDS: [string, string, number][] = [
  ["annual_agent_operations", "Annual AI-agent operations", 1000], ["manual_review_pct", "Manual security-review %", 0.5],
  ["manual_review_minutes", "Average manual review (minutes)", 0.5], ["staff_cost_per_fte_year", "Fully loaded staff cost / FTE-year", 1000],
  ["productive_hours_per_fte_year", "Productive review hours / FTE-year", 10], ["wakala_exception_review_pct", "WAKALA exception-review %", 0.1],
  ["exception_review_minutes", "Average exception review (minutes)", 0.5], ["legally_required_review_pct", "Review required by law/policy %", 0.5],
  ["annual_platform_and_integration_cost", "Annual platform + integration cost", 1000],
];

function BusinessCalculator({ defaults }: { defaults: Summary }) {
  const [a, setA] = useState<Record<string, number | string>>(defaults.assumptions);
  const [res, setRes] = useState<Summary>(defaults);
  const [err, setErr] = useState<string | null>(null);
  useEffect(() => {
    const t = setTimeout(() => {
      apiPost<Summary>("/api/evidence/business-model", a).then((r) => { setRes(r); setErr(null); })
        .catch((e) => setErr(e instanceof ApiError ? `${e.code}: ${e.message}` : String(e)));
    }, 250);
    return () => clearTimeout(t);
  }, [a]);
  const cur = String(a.currency ?? "AED");
  const money = (x: number) => `${Math.round(x).toLocaleString("en-US")} ${cur}`;
  return (
    <Card>
      <CardHeader icon={Calculator} title="Business-value scenario calculator" subtitle="Every input is an ASSUMPTION you control — not an observed government statistic"
        right={<Badge tone="warn">Hypothetical model</Badge>} />
      <div className="grid gap-6 p-5 xl:grid-cols-[minmax(0,420px)_1fr]">
        <div className="space-y-3">
          {FIELDS.map(([k, label, step]) => (
            <label key={k} className="block">
              <span className="flex items-center justify-between text-[12px] text-fg-muted">{label}<Badge tone="neutral">assumption</Badge></span>
              <input type="number" step={step} min={0} value={Number(a[k])} onChange={(e) => setA({ ...a, [k]: Number(e.target.value) })}
                className="mt-1 block w-full rounded-lg border border-line bg-ink-900 px-3 py-1.5 font-mono text-[13px] text-fg focus:border-trust" />
            </label>
          ))}
          {err && <p className="text-[12px] text-deny">{err}</p>}
        </div>
        <div className="space-y-4">
          <div className="grid gap-3 sm:grid-cols-2">
            <Tile icon={ShieldCheck} label="Routine manual reviews avoided" value={Math.round(res.routine_manual_reviews_avoided).toLocaleString("en-US")} note="per year, under these assumptions" />
            <Tile icon={Clock} label="Review hours: manual → WAKALA" value={`${Math.round(res.manual_review_scenario.review_hours).toLocaleString("en-US")} → ${Math.round(res.wakala_exception_scenario.review_hours).toLocaleString("en-US")}`}
              note={`workload reduction ${res.operational_workload_reduction.rate === null ? "n/a" : (100 * res.operational_workload_reduction.rate).toFixed(1) + "%"} (${res.operational_workload_reduction.numerator_hours} / ${res.operational_workload_reduction.denominator_hours} h)`} />
            <Tile icon={Calculator} label="Hypothetical annual cost difference" value={money(res.hypothetical_annual_cost_difference)}
              tone={res.hypothetical_annual_cost_difference >= 0 ? "trust" : "deny"} note="manual review cost − (exception review cost + platform cost)" />
            <Tile icon={Gauge} label="Break-even" value={res.break_even.annual_operations ? `${Math.round(res.break_even.annual_operations).toLocaleString("en-US")} ops/yr` : "never"}
              note={`or manual-review share ${res.break_even.manual_review_pct ?? "n/a"}% at current volume`} />
          </div>
          <div>
            <p className="eyebrow mb-2">Sensitivity — annual cost difference ({cur})</p>
            <Table head={["Manual review % ↓ / exception % →", ...[0.5, 2, 5, 10].map((e) => `${e}%`)]}
              rows={[5, 10, 20, 40].map((m) => [`${m}%`, ...[0.5, 2, 5, 10].map((e) => {
                const v = res.sensitivity.find((x: Summary) => x.manual_review_pct === m && x.wakala_exception_review_pct === e)?.annual_cost_difference ?? 0;
                return <span key={e} className={clsx("font-mono tabular-nums", v >= 0 ? "text-trust" : "text-deny")}>{Math.round(v).toLocaleString("en-US")}</span>;
              })])} />
          </div>
          <div className="rounded-lg border border-line bg-ink-900/60 p-3 text-[12px] text-fg-muted">
            <p className="eyebrow mb-1">Observed in the synthetic benchmark (reference only, not a default)</p>
            {Object.entries(res.observed_in_synthetic_benchmark ?? {}).map(([k, v]) => (
              <p key={k}><span className="text-fg-subtle">{humanize(k)}:</span> {typeof v === "object" && v !== null && "denominator" in (v as object) ? `${pct(v as Rate)} (${frac(v as Rate)})` : String(v)}</p>
            ))}
            <ul className="mt-2 list-disc space-y-0.5 pl-4">{res.limits.map((l: string) => <li key={l}>{l}</li>)}</ul>
          </div>
        </div>
      </div>
    </Card>
  );
}

// --- page -----------------------------------------------------------------------------------------------
export function SecurityEvidence() {
  const state = useApi<Summary>("/api/evidence/summary", { live: true });
  return (
    <>
      <PageHeader eyebrow="Phase 5 · Adversarial benchmark" title="Security Evidence" titleAr="الأدلة الأمنية"
        description="Labeled synthetic requests run through an intentionally weak role-only baseline, case-bound WAKALA and full WAKALA — each in isolated state. Every figure on this page is loaded from the generated result files through the backend."
        actions={<Badge tone="warn" className="uppercase tracking-wider">Synthetic benchmark</Badge>} />
      <Notice tone="warn" icon={AlertTriangle} title={LABEL}>
        Simulated agents, synthetic citizens and a single-process prototype on one developer machine. Rates are per designed attack category;
        latency must not be extrapolated to national capacity. The baseline is deliberately weak and does not represent all real IAM systems.
      </Notice>
      {state.status === "error" && state.error instanceof ApiError && state.error.code === "EVIDENCE_NOT_GENERATED" ? (
        <EmptyState icon={FileText} title="No benchmark evidence has been generated yet">
          Run <span className="font-mono">.venv\Scripts\python -m app.evaluation.run</span> in <span className="font-mono">backend/</span>, then reload.
        </EmptyState>
      ) : (
        <ApiView state={state} reload={state.reload}>{(s) => <Evidence s={s} />}</ApiView>
      )}
    </>
  );
}

function Evidence({ s }: { s: Summary }) {
  const cfg = s.configurations;
  const C = cfg.C;
  const rec = s.recovery;
  const [report, setReport] = useState<string | null>(null);
  const chart = useMemo(() => C.by_category.filter((r: Summary) => r.label === "unauthorized").map((r: Summary, i: number) => {
    const idx = C.by_category.indexOf(r);
    void i;
    const row: Record<string, string | number | null> = { category: humanize(r.category) };
    for (const k of CONFIGS) {
      const o = cfg[k].by_category[idx].outcome as Rate;
      row[k] = o.denominator ? Math.round(1000 * (o.rate ?? 0)) / 10 : null;
    }
    return row;
  }), [C, cfg]);
  const problems: string[] = [];
  for (const k of CONFIGS) {
    const x = cfg[k];
    if (x.harness_errors.length) problems.push(`${k}: ${x.harness_errors.length} harness error(s)`);
    if (x.unauthorized_operations_executed.numerator) problems.push(`${k}: ${x.unauthorized_operations_executed.numerator} unauthorized operation(s) executed`);
    if (x.legitimate_incorrectly_denied.numerator) problems.push(`${k}: ${x.legitimate_incorrectly_denied.numerator} legitimate operation(s) denied — ${Object.keys(x.false_denial_reasons).join("; ")}`);
  }
  for (const k of ["independent_incidents", "back_to_back_shared"]) {
    const r = rec[k];
    if (r.recovery_success.numerator < r.recovery_success.denominator) problems.push(`Recovery (${humanize(k)}): ${r.recovery_success.denominator - r.recovery_success.numerator} of ${r.recovery_success.denominator} incident(s) not fully recovered`);
  }
  if (s.integrity.mismatched?.length) problems.push(`Evidence files changed since generation: ${s.integrity.mismatched.join(", ")}`);
  const mem = s.latency.integration_in_memory_sqlite, fil = s.latency.integration_persisted_sqlite_file, mic = s.latency.microbenchmarks_in_memory;
  const run = s.run;

  return (
    <div className="space-y-6">
      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-6">
        <Tile icon={Database} label="Requests evaluated" value={s.dataset.total_requests} note={`${s.dataset.legitimate} legitimate · ${s.dataset.unauthorized} unauthorized — individual requests, not applications`} />
        <Tile icon={ShieldX} label="Unauthorized executed · A" value={pct(cfg.A.unauthorized_operations_executed)} note={frac(cfg.A.unauthorized_operations_executed)} tone="deny" />
        <Tile icon={ShieldCheck} label="Unauthorized executed · C" value={pct(C.unauthorized_operations_executed)} note={frac(C.unauthorized_operations_executed)} tone={C.unauthorized_operations_executed.numerator ? "deny" : "trust"} />
        <Tile icon={CheckCircle2} label="Legitimate allowed · C" value={pct(C.legitimate_operations_allowed)} note={frac(C.legitimate_operations_allowed)} tone={C.legitimate_incorrectly_denied.numerator ? "warn" : "trust"} />
        <Tile icon={AlertTriangle} label="False denial rate · C" value={pct(C.legitimate_incorrectly_denied)} note={`B: ${pct(cfg.B.legitimate_incorrectly_denied)} (${frac(cfg.B.legitimate_incorrectly_denied)})`} tone={C.legitimate_incorrectly_denied.numerator ? "warn" : "trust"} />
        <Tile icon={LifeBuoy} label="Recovery success" value={pct(rec.independent_incidents.recovery_success)}
          note={`independent ${frac(rec.independent_incidents.recovery_success)} · back-to-back ${pct(rec.back_to_back_shared.recovery_success)} (${frac(rec.back_to_back_shared.recovery_success)})`}
          tone={rec.back_to_back_shared.recovery_success.rate < 1 ? "warn" : "trust"} />
      </div>

      <Card>
        <CardHeader icon={AlertTriangle} title="Failures and unexpected results" subtitle="Listed from the result files — never hidden" right={<Badge tone={problems.length ? "warn" : "trust"}>{problems.length} item(s)</Badge>} />
        <ul className="space-y-1.5 px-5 py-4 text-[12.5px]">
          {problems.length === 0 ? <li className="text-trust">None reported.</li> : problems.map((p) => <li key={p} className="flex gap-2 text-fg-muted"><AlertTriangle className="mt-0.5 size-3.5 shrink-0 text-warn" aria-hidden />{p}</li>)}
        </ul>
      </Card>

      <Card>
        <CardHeader icon={BarChart3} title="Baseline versus WAKALA" subtitle="Ground truth × outcome. Each cell: rate and numerator/denominator" />
        <Table head={["Measure", ...CONFIGS.map((k) => CONFIG_NAME[k])]} rows={([
          ["Requests evaluated (applicable)", "requests_evaluated", undefined], ["Unauthorized operations executed", "unauthorized_operations_executed", "low"],
          ["Unauthorized operations prevented", "unauthorized_operations_prevented", "high"], ["Unauthorized incorrectly permitted", "unauthorized_incorrectly_permitted", "low"],
          ["Legitimate operations allowed", "legitimate_operations_allowed", "high"], ["Legitimate incorrectly denied", "legitimate_incorrectly_denied", "low"],
          ["Delegation escalation prevented", "delegation_escalation_prevention", "high"], ["Revocation effectiveness", "revocation_effectiveness", "high"],
          ["Unauthorized state mutations", "unauthorized_state_mutations", "low"], ["Audit evidence complete", "audit_evidence_complete", "high"],
        ] as [string, string, "high" | "low" | undefined][]).map(([label, key, good]) => [
          <span className="text-fg-muted">{label}</span>,
          ...CONFIGS.map((k) => typeof cfg[k][key] === "number" ? <span className="tabular-nums">{cfg[k][key]}{k === "B" && key === "requests_evaluated" ? <span className="text-fg-subtle"> ({cfg.B.not_applicable} n/a)</span> : null}</span> : <RateCell r={cfg[k][key]} good={good} />),
        ])} />
        <div className="space-y-1 px-5 py-3 text-[11.5px] text-fg-subtle">{CONFIGS.map((k) => <p key={k}><b className="text-fg-muted">{k}</b> — {cfg[k].run.description}</p>)}</div>
      </Card>

      <div className="grid gap-6 2xl:grid-cols-2">
        <Card className="min-w-0">
          <CardHeader icon={ShieldCheck} title="Prevention by attack type" subtitle="% of unauthorized requests not executed (gaps = not applicable)" />
          <div className="h-[380px] px-2 py-4">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={chart} layout="vertical" margin={{ left: 40, right: 16 }}>
                <CartesianGrid horizontal={false} stroke="#1b2a46" />
                <XAxis type="number" domain={[0, 100]} tick={{ fill: "#64748f", fontSize: 11 }} unit="%" />
                <YAxis type="category" dataKey="category" width={170} tick={{ fill: "#94a3b8", fontSize: 10.5 }} />
                <Tooltip contentStyle={{ background: "#0d172b", border: "1px solid #263a5e", borderRadius: 10, fontSize: 12 }} labelStyle={{ color: "#e7edf7" }} />
                <Legend wrapperStyle={{ fontSize: 12 }} />
                {CONFIGS.map((k) => <Bar key={k} dataKey={k} name={CONFIG_NAME[k]} fill={COLORS[k]} barSize={5} />)}
              </BarChart>
            </ResponsiveContainer>
          </div>
        </Card>
        <Card className="min-w-0">
          <CardHeader icon={Gauge} title="Prevention vs monitoring detection · C" subtitle="Detection = a deterministic rule fired; it is separate from prevention" />
          <Table head={["Category", "Prevented / completed", "Specific-rule detection", "Escalated"]} rows={C.by_category.map((r: Summary) => [
            <span>{humanize(r.category)} {r.label === "legitimate" && <Badge tone="trust">legit</Badge>}</span>,
            <RateCell r={r.outcome} good="high" />, <RateCell r={r.detection_specific} />, <RateCell r={r.escalated_to_officer_queue} />,
          ])} />
          <p className="px-5 py-3 text-[11.5px] text-fg-subtle">{C.monitoring.note} False alarms on legitimate requests (specific rules): {pct(C.monitoring.legitimate_with_specific_rule_alert)} ({frac(C.monitoring.legitimate_with_specific_rule_alert)}).</p>
        </Card>
      </div>

      <Card>
        <CardHeader icon={Clock} title="Authorization latency (ms) — median / p95 / p99" subtitle={s.latency.method} />
        <Table head={["Measurement", "SQLite :memory:", "SQLite file (persisted)"]} rows={[
          ["Direct mandate · decision only", <Lat s={mem.direct_mandate_authorization.decision_only} />, <Lat s={fil.direct_mandate_authorization.decision_only} />],
          ["Direct mandate · full gateway (audit + monitoring)", <Lat s={mem.direct_mandate_authorization.gateway_wall} />, <Lat s={fil.direct_mandate_authorization.gateway_wall} />],
          ["Delegated mandate · decision only", <Lat s={mem.delegated_mandate_authorization.decision_only} />, <Lat s={fil.delegated_mandate_authorization.decision_only} />],
          ["Delegated mandate · full gateway", <Lat s={mem.delegated_mandate_authorization.gateway_wall} />, <Lat s={fil.delegated_mandate_authorization.gateway_wall} />],
          ["Protected tool execution", <Lat s={mem.protected_tool_execution.gateway_execute_wall} />, <Lat s={fil.protected_tool_execution.gateway_execute_wall} />],
          ["End-to-end case (machine time)", <Lat s={mem.end_to_end_case.wall} />, <Lat s={fil.end_to_end_case.wall} />],
          ["Microbenchmark · signature verification", <Lat s={mic.authentication_and_signature_verification} />, <span className="text-fg-subtle">in-memory only</span>],
          ["Microbenchmark · chain verification (2 links)", <Lat s={mic.delegation_chain_verification} />, <span className="text-fg-subtle">in-memory only</span>],
        ].map((r) => [<span className="text-fg-muted">{r[0]}</span>, r[1], r[2]])} />
      </Card>

      <Card>
        <CardHeader icon={Gauge} title="Scalability stress" subtitle={s.stress.probe} />
        <Table head={["Dimension", "Points (value → median / p95 ms, errors)"]} rows={([
          ["Active cases", "active_cases", "active_cases"], ["Registered agents", "registered_agents", "registered_agents"],
          ["Audit records", "audit_records", "audit_records"], ["Prior decisions by same agent", "agent_history", "prior_decisions_by_same_agent"],
        ] as [string, string, string][]).map(([label, key, dim]) => [
          <span className="text-fg-muted">{label}</span>,
          <span className="font-mono text-[11.5px]">{s.stress[key].map((p: Summary) => `${p[dim]} → ${ms(p.latency.median_ms)} / ${ms(p.latency.p95_ms)}${p.full_chain_verification_ms !== undefined ? ` (chain verify ${ms(p.full_chain_verification_ms)})` : ""}, ${p.errors_or_unexpected_denials} err`).join("   ·   ")}</span>,
        ]).concat([[
          <span className="text-fg-muted">Concurrency (threads)</span>,
          <span className="font-mono text-[11.5px]">{s.stress.concurrency.map((p: Summary) => `${p.threads}t → ${p.throughput_rps} req/s, median ${ms(p.latency.median_ms)} ms, ${p.errors} err, ${p.monitoring_observer_failures} observer failures`).join("   ·   ")}</span>,
        ], [
          <span className="text-fg-muted">Delegation depth</span>,
          <span className="font-mono text-[11.5px]">depth 1 median {ms(s.stress.delegation_depth.depth_1_delegated_authorization.median_ms)} ms · grant permits {s.stress.delegation_depth.depth_permitted_by_current_grant} (global max {s.stress.delegation_depth.global_max_depth}) · depth-2 attempt {s.stress.delegation_depth.depth_2_attempt.allowed ? "ALLOWED" : "denied"}: {s.stress.delegation_depth.depth_2_attempt.reason_codes.join(", ")}</span>,
        ]])} />
      </Card>

      <Card>
        <CardHeader icon={LifeBuoy} title="Revocation, intervention and service continuity" subtitle={rec.note} />
        <div className="grid gap-4 p-5 lg:grid-cols-2">
          {(["independent_incidents", "back_to_back_shared"] as const).map((k) => {
            const r = rec[k];
            return (
              <div key={k} className="rounded-xl border border-line bg-ink-800/60 p-4">
                <div className="flex items-center justify-between"><p className="text-[13.5px] font-medium text-fg">{humanize(k)}</p>
                  <Badge tone={r.recovery_success.rate === 1 ? "trust" : "warn"}>{pct(r.recovery_success)} · {frac(r.recovery_success)}</Badge></div>
                <p className="mt-1 text-[11.5px] text-fg-subtle">{r.condition}</p>
                <ul className="mt-3 space-y-1 text-[12px]">{Object.entries(r.per_step_success).map(([step, v]) => (
                  <li key={step} className="flex justify-between gap-3"><span className="text-fg-muted">{humanize(step.replace(/^\d_/, ""))}</span><RateCell r={v as Rate} good="high" /></li>
                ))}</ul>
                <p className="mt-3 text-[11.5px] text-fg-subtle">Containment {JSON.stringify(r.containment_actions)} · denial → completion median {ms(r.denial_to_completion.median_ms)} ms · REQUEST_RATE incidents {r.request_rate_incidents_during_run} · audit chain {r.audit_chain_valid ? "valid" : "INVALID"}</p>
                {r.failures.length > 0 && <p className="mt-2 text-[11.5px] text-warn">Failures: {Object.entries(r.failures.reduce((acc: Record<string, number>, f: Summary) => { const key = `${f.failed_at}: ${f.cause ?? "—"}`; acc[key] = (acc[key] ?? 0) + 1; return acc; }, {})).map(([c, n]) => `${n} × ${c}`).join("; ")}</p>}
              </div>
            );
          })}
        </div>
        <p className="px-5 pb-4 text-[12px] text-fg-muted">Revocation effectiveness (C): {pct(C.revocation_effectiveness)} ({frac(C.revocation_effectiveness)}) · delegation escalation prevented: {pct(C.delegation_escalation_prevention)} ({frac(C.delegation_escalation_prevention)}).</p>
      </Card>

      <BusinessCalculator defaults={s.business_model_defaults} />

      <div className="grid gap-6 xl:grid-cols-2">
        <Card>
          <CardHeader icon={Database} title="Dataset breakdown" subtitle={`seed ${run.dataset.seed} · SHA-256 ${s.dataset_sha256.slice(0, 16)}…`} />
          <Table head={["Category", "Label", "Count"]} rows={s.dataset.by_category.map((c: Summary) => [
            <span>{humanize(c.category)}{c.delegation_only && <span className="text-fg-subtle"> · delegation only</span>}</span>,
            <Badge tone={c.label === "legitimate" ? "trust" : "deny"}>{c.label}</Badge>, <span className="tabular-nums">{c.count}</span>,
          ])} />
        </Card>
        <Card>
          <CardHeader icon={FileText} title="Reproducible run metadata" subtitle="From config.json and environment.json"
            right={<Badge tone={s.integrity.mismatched?.length ? "deny" : "trust"}>{s.integrity.manifest_present ? `${s.integrity.files_verified} files hash-verified` : "no manifest"}</Badge>} />
          <dl className="grid grid-cols-[170px_1fr] gap-x-4 gap-y-1.5 px-5 py-4 text-[12px]">
            {[["Commit", `${run.git.commit?.slice(0, 12) ?? "unknown"}${run.git.working_tree_dirty ? " (uncommitted changes)" : ""}`], ["Branch", run.git.branch],
              ["Started / finished", `${run.started_at} → ${run.finished_at}`], ["Phase timings (s)", JSON.stringify(run.phase_timings)],
              ["Quick mode", run.quick_mode ? "YES — development sample sizes" : "no"],
              ...Object.entries(s.environment).map(([k, v]) => [humanize(k), String(v)]), ["Isolation", run.isolation]].map(([k, v]) => (
              <Fragment key={k}><dt className="text-fg-subtle">{k}</dt><dd className="break-words font-mono text-[11.5px] text-fg-muted">{v}</dd></Fragment>
            ))}
          </dl>
          <div className="border-t border-line px-5 py-3">
            <p className="eyebrow mb-1">Reproduce</p>
            <pre className="overflow-x-auto rounded-lg bg-ink-900 p-3 font-mono text-[11.5px] text-fg-muted">{run.reproduce.join("\n")}</pre>
            <button className="mt-3 text-[12.5px] text-trust hover:underline" onClick={() => (report ? setReport(null) : fetch(`${API_BASE_URL}/api/evidence/report`).then((r) => (r.ok ? r.text() : Promise.reject(r.status))).then(setReport).catch(() => setReport("Report unavailable.")))}>
              {report ? "Hide" : "Show"} REPORT.md
            </button>
          </div>
        </Card>
      </div>
      {report && <Card><pre className="max-h-[600px] overflow-auto whitespace-pre-wrap p-5 font-mono text-[11.5px] text-fg-muted">{report}</pre></Card>}
    </div>
  );
}
