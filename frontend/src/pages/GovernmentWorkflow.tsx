import clsx from "clsx";
import {
  ArrowRight, Bot, CheckCircle2, CircleSlash, Clock, CreditCard, FileCheck2, History, Landmark, Loader2, Lock, Play,
  ScrollText, ShieldAlert, ShieldCheck, Stethoscope, User, XCircle, type LucideIcon,
} from "lucide-react";
import { useState } from "react";
import { ApiView, Badge, Card, CardHeader, EmptyState, Notice, PageHeader, SyntheticBadge } from "@/components/ui";
import { invalidate, useApi } from "@/hooks/useApi";
import { apiGet, apiPost } from "@/lib/api";
import { humanize, type Tone } from "@/lib/format";
import type {
  AuditEvent, BaselineComparison, CaseDetail, CaseState, CaseSummary, Citizen, ListResponse, RenewalCase, SystemCapabilities,
  WorkflowRun, WorkflowScenarioInfo, WorkflowStep,
} from "@/types/api";

const MAIN_PATH: CaseState[] = ["CREATED", "VERIFYING", "AWAITING_PAYMENT", "READY_TO_COMPLETE", "COMPLETED"];
const STATE_TONE: Record<CaseState, Tone> = {
  CREATED: "neutral", VERIFYING: "plan", AWAITING_PAYMENT: "plan", READY_TO_COMPLETE: "plan",
  COMPLETED: "trust", PAUSED_FOR_REVIEW: "warn", FAILED: "deny",
};
const AGENT_ICON: Record<string, LucideIcon> = { "AGT-RES-001": FileCheck2, "AGT-INS-001": Stethoscope, "AGT-PAY-001": CreditCard };
const AGENT_NAME: Record<string, string> = { "AGT-RES-001": "Residency Agent", "AGT-INS-001": "Insurance Agent", "AGT-PAY-001": "Payment Agent" };
const PREREQS = [
  ["residency_eligibility", "Residency eligibility"],
  ["insurance_verified", "Insurance verified"],
  ["fee_paid", "Fee paid (synthetic)"],
] as const;
const CHECK_LABEL: Record<string, string> = {
  identity: "1 Identity", agent_status: "2 Agent status", mandate_integrity: "3 Mandate integrity",
  mandate_validity: "4 Mandate validity", tool_permission: "5 Tool permission", resource_scope: "6 Case & resource scope",
  action_constraints: "7 Action constraints", request_context: "8 Request context",
};
const SCENARIO_ICON: Record<string, LucideIcon> = {
  legitimate_renewal: ShieldCheck, wrong_citizen: User, unauthorized_payment: CreditCard, baseline_comparison: ScrollText,
};

const time = (iso: string) => new Date(iso).toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit", second: "2-digit" });
const fmt = (o: Record<string, unknown>) => Object.entries(o).map(([k, v]) => `${k}=${String(v)}`).join(" · ");

function StateStepper({ c }: { c: RenewalCase }) {
  const reachedIdx = MAIN_PATH.indexOf(c.state === "PAUSED_FOR_REVIEW" ? (c.paused_from ?? "CREATED") : c.state);
  const off = c.state === "FAILED" || c.state === "PAUSED_FOR_REVIEW";
  return (
    <div>
      <ol className="flex flex-wrap items-center gap-1.5">
        {MAIN_PATH.map((s, i) => {
          const done = !off ? i < reachedIdx || c.state === "COMPLETED" : i < reachedIdx;
          const current = !off && i === reachedIdx && c.state !== "COMPLETED";
          return (
            <li key={s} className="flex items-center gap-1.5">
              <span className={clsx(
                "rounded-md border px-2 py-1 font-mono text-[11px] transition-colors",
                done && "border-trust/30 bg-trust-soft text-trust",
                current && "border-cyan/40 bg-ink-750 text-cyan",
                c.state === "COMPLETED" && s === "COMPLETED" && "border-trust/50 bg-trust-soft text-trust",
                !done && !current && !(c.state === "COMPLETED" && s === "COMPLETED") && "border-line text-fg-subtle",
              )}>
                {s.replace(/_/g, " ")}
              </span>
              {i < MAIN_PATH.length - 1 && <ArrowRight className="size-3 text-fg-subtle" aria-hidden />}
            </li>
          );
        })}
      </ol>
      {off && (
        <p className={clsx("mt-2 inline-flex items-center gap-1.5 rounded-md border px-2 py-1 font-mono text-[11px]",
          c.state === "FAILED" ? "border-deny/30 bg-deny-soft text-deny" : "border-warn/30 bg-warn-soft text-warn")}>
          {c.state === "FAILED" ? <XCircle className="size-3.5" aria-hidden /> : <ShieldAlert className="size-3.5" aria-hidden />}
          {c.state.replace(/_/g, " ")}{c.paused_from ? ` (from ${c.paused_from.replace(/_/g, " ")})` : ""} · recovery: {humanize(c.recovery_status)}
        </p>
      )}
    </div>
  );
}

function CaseCard({ c }: { c: RenewalCase }) {
  return (
    <Card>
      <div className="flex flex-wrap items-start justify-between gap-4 border-b border-line p-5">
        <div>
          <p className="eyebrow">Renewal case · synthetic</p>
          <p className="mt-1 font-mono text-[18px] font-semibold text-fg">{c.case_id}</p>
          <p className="mt-1 text-[13px] text-fg-muted">
            Citizen <span className="font-mono text-fg">{c.citizen_ref}</span> · request <span className="font-mono">{c.request_id}</span>
          </p>
        </div>
        <Badge tone={STATE_TONE[c.state]} dot>{c.state.replace(/_/g, " ")}</Badge>
      </div>
      <div className="space-y-5 p-5">
        <StateStepper c={c} />
        <div className="grid gap-5 lg:grid-cols-3">
          <div>
            <p className="eyebrow mb-2">Prerequisites</p>
            <ul className="space-y-1.5">
              {PREREQS.map(([k, label]) => {
                const ok = c.completed_prerequisites.includes(k);
                return (
                  <li key={k} className={clsx("flex items-center gap-2 text-[13px]", ok ? "text-fg" : "text-fg-subtle")}>
                    {ok ? <CheckCircle2 className="size-4 text-trust" aria-hidden /> : <CircleSlash className="size-4" aria-hidden />} {label}
                  </li>
                );
              })}
            </ul>
          </div>
          <div>
            <p className="eyebrow mb-2">Case-specific authority</p>
            <dl className="space-y-1 text-[12.5px]">
              <div><dt className="inline text-fg-subtle">Owner </dt><dd className="inline text-fg">{c.service_owner}</dd></div>
              <div><dt className="inline text-fg-subtle">Purpose </dt><dd className="inline text-fg">{c.authorized_purpose}</dd></div>
              <div><dt className="inline text-fg-subtle">Expires </dt><dd className="inline font-mono text-fg">{time(c.expires_at)}</dd></div>
              <div><dt className="inline text-fg-subtle">Operations </dt><dd className="inline font-mono text-[11.5px] text-fg-muted">{c.authorized_operations.length} authorized</dd></div>
            </dl>
          </div>
          <div>
            <p className="eyebrow mb-2">Assigned agents · case mandates</p>
            <ul className="space-y-1.5">
              {c.assigned_agents.map((a) => {
                const Icon = AGENT_ICON[a] ?? Bot;
                return (
                  <li key={a} className="flex items-center gap-2 text-[12.5px]">
                    <Icon className="size-3.5 text-cyan" aria-hidden />
                    <span className="text-fg">{AGENT_NAME[a] ?? a}</span>
                    <span className="ml-auto font-mono text-[11px] text-fg-subtle">{c.mandate_refs[a]}</span>
                  </li>
                );
              })}
            </ul>
          </div>
        </div>
      </div>
    </Card>
  );
}

function StepRow({ s }: { s: WorkflowStep }) {
  const d = s.decision;
  const failed = s.checks.filter((c) => c.status === "failed");
  const safety = s.intent === "safety_control";
  const allowed = safety ? true : !!d?.allowed;
  const Icon = safety ? ShieldAlert : AGENT_ICON[s.agent_id] ?? Bot;
  return (
    <li className="relative pl-10">
      <span className={clsx(
        "absolute left-0 top-0.5 grid size-7 place-items-center rounded-full border text-[12px] font-semibold",
        safety ? "border-warn/40 bg-warn-soft text-warn" : allowed ? "border-trust/40 bg-trust-soft text-trust" : "border-deny/40 bg-deny-soft text-deny",
      )}>{s.index}</span>
      <div className={clsx("rounded-xl border p-4", allowed ? "border-line bg-ink-800/60" : "border-deny/25 bg-deny-soft/40")}>
        <div className="flex flex-wrap items-center gap-2">
          <Icon className="size-4 text-fg-subtle" aria-hidden />
          <span className="text-[14px] font-semibold text-fg">{s.title}</span>
          <span className="text-[12px] text-fg-subtle">· {safety ? "server-side control" : AGENT_NAME[s.agent_id] ?? s.agent_id}</span>
          <span className="ml-auto flex items-center gap-1.5">
            {d && <Badge tone={d.allowed ? "trust" : "deny"}>{d.allowed ? "ALLOW" : "DENY"}</Badge>}
            <Badge tone={s.executed ? "trust" : "neutral"}>{s.executed ? "executed" : humanize(s.execution_status)}</Badge>
          </span>
        </div>
        <p className="mt-2 font-mono text-[12px] text-cyan">{s.tool_name}</p>
        <p className="mt-0.5 break-all font-mono text-[11.5px] text-fg-muted">{fmt(s.parameters)}</p>
        {d && !d.allowed && (
          <div className="mt-3 rounded-lg border border-deny/30 bg-ink-900/60 px-3 py-2">
            <p className="text-[12.5px] text-fg">{d.human_readable_explanation}</p>
            <p className="mt-1 font-mono text-[11.5px] text-deny">{d.reason_codes.join(" · ")}</p>
            {failed.length > 0 && (
              <p className="mt-1 text-[12px] text-fg-muted">
                Failed check: {failed.map((c) => <b key={c.name} className="text-fg">{CHECK_LABEL[c.name] ?? c.name}</b>)} ·
                mandate <span className="font-mono">{s.mandate_id}</span> · case <span className="font-mono">{s.case_id}</span>
              </p>
            )}
            <p className="mt-1 text-[12px] text-fg-subtle">No data returned · no state changed · nothing executed.</p>
          </div>
        )}
        {s.result && s.executed && (
          <p className="mt-2 break-all rounded-lg border border-line bg-ink-900/60 px-3 py-2 font-mono text-[11.5px] text-fg-muted">
            <span className="text-trust">service result </span>{fmt(s.result)}
          </p>
        )}
        {s.result && !s.executed && <p className="mt-2 font-mono text-[11.5px] text-warn">service refusal: {fmt(s.result)}</p>}
        {s.note && <p className="mt-2 text-[12px] italic text-fg-subtle">{s.note}</p>}
        <div className="mt-3 flex flex-wrap items-center gap-x-4 gap-y-1 border-t border-line pt-2 font-mono text-[11px] text-fg-subtle">
          <span>case {s.case_state_before.replace(/_/g, " ")} → <span className={s.case_state_after !== s.case_state_before ? "text-fg" : ""}>{s.case_state_after.replace(/_/g, " ")}</span></span>
          {d && <span>decision {d.decision_id}</span>}
          {d && <span>audit {d.audit_reference}</span>}
          {s.execution_audit_reference && <span>execution audit {s.execution_audit_reference}</span>}
          {d && <span>{d.decision_latency_ms.toFixed(2)} ms</span>}
        </div>
      </div>
    </li>
  );
}

function Baseline({ b }: { b: BaselineComparison }) {
  return (
    <Card>
      <CardHeader icon={ScrollText} title="Same request · two systems" subtitle={b.description} right={<Badge tone="warn">{b.label}</Badge>} />
      <p className="border-b border-line px-5 py-3 font-mono text-[12px] text-fg-muted">{fmt(b.request)}</p>
      <div className="grid divide-y divide-line md:grid-cols-2 md:divide-x md:divide-y-0">
        <div className="p-5">
          <p className="flex items-center gap-2 text-[13px] font-semibold text-warn"><Lock className="size-4" aria-hidden /> Weak role-based baseline</p>
          <p className="mt-2 text-[12.5px] text-fg-muted">Checks performed: {b.baseline_checks_performed.join(", ")}</p>
          <p className={clsx("mt-3 text-[22px] font-semibold", b.baseline_allowed ? "text-deny" : "text-trust")}>
            {b.baseline_allowed ? "Returned another citizen's record" : "Refused"}
          </p>
          {b.baseline_returned_data && (
            <pre className="mt-3 overflow-x-auto rounded-lg border border-deny/30 bg-deny-soft/40 p-3 font-mono text-[11.5px] text-fg-muted">
              {JSON.stringify(b.baseline_returned_data, null, 2)}
            </pre>
          )}
          <p className="mt-2 text-[11.5px] text-fg-subtle">Synthetic data · isolated in-memory copy · not WAKALA's services.</p>
        </div>
        <div className="p-5">
          <p className="flex items-center gap-2 text-[13px] font-semibold text-trust"><ShieldCheck className="size-4" aria-hidden /> WAKALA gateway</p>
          <p className="mt-2 text-[12.5px] text-fg-muted">Signature · mandate · case · scope · constraints · context</p>
          <p className={clsx("mt-3 text-[22px] font-semibold", b.wakala_allowed ? "text-deny" : "text-trust")}>
            {b.wakala_allowed ? "Allowed" : "Denied before any data was read"}
          </p>
          <p className="mt-2 font-mono text-[11.5px] text-deny">{b.wakala_reason_codes.join(" · ")}</p>
          <p className="mt-1 font-mono text-[11px] text-fg-subtle">audit {b.wakala_audit_reference} · returned data: {b.wakala_returned_data ? "yes" : "none"}</p>
        </div>
      </div>
      <p className="border-t border-line px-5 py-3 text-[12px] text-fg-subtle">
        The baseline is intentionally weak and test-only. It does not represent all real government access-management systems.
      </p>
    </Card>
  );
}

function AuditList({ events }: { events: AuditEvent[] }) {
  if (!events.length) return <EmptyState icon={History} title="No audit events for this case yet." />;
  return (
    <div className="overflow-x-auto">
      <table className="w-full min-w-[720px] text-left text-[12.5px]">
        <thead>
          <tr className="border-b border-line text-[11px] uppercase tracking-wider text-fg-subtle">
            {["#", "Time", "Actor", "Action", "Decision", "Reason codes", "Event"].map((h) => <th key={h} className="px-4 py-2.5 font-medium">{h}</th>)}
          </tr>
        </thead>
        <tbody>
          {events.map((e) => (
            <tr key={e.event_id} className="border-b border-line/60">
              <td className="px-4 py-2 font-mono text-fg-subtle">{e.sequence}</td>
              <td className="px-4 py-2 font-mono">{time(e.timestamp)}</td>
              <td className="px-4 py-2 font-mono">{e.actor}</td>
              <td className="px-4 py-2 font-mono">{e.action}</td>
              <td className="px-4 py-2">
                <Badge tone={e.decision === "allowed" ? "trust" : e.decision === "denied" ? "deny" : "neutral"}>{e.decision}</Badge>
              </td>
              <td className="px-4 py-2 font-mono text-[11px] text-fg-muted">
                {e.reason_codes.join(" · ") || String(e.evidence_metadata.execution_status ?? e.evidence_metadata.reason ?? "—")}
              </td>
              <td className="px-4 py-2 font-mono text-[11px] text-fg-subtle">{e.event_id}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function CaseExtras({ c, ledger, events }: { c: RenewalCase; ledger: Record<string, string>[]; events: AuditEvent[] }) {
  return (
    <div className="grid gap-6 2xl:grid-cols-[1.4fr_1fr]">
      <Card className="min-w-0">
        <CardHeader icon={ShieldCheck} title="Linked audit records" subtitle="Every gateway decision and service execution for this case (hash-chained)" />
        <AuditList events={events} />
      </Card>
      <div className="flex min-w-0 flex-col gap-6">
        <Card>
          <CardHeader icon={CreditCard} title="Synthetic ledger" subtitle="Payment service · no real funds" />
          {ledger.length === 0 ? (
            <p className="px-5 py-4 text-[13px] text-fg-subtle">No transaction recorded for this case.</p>
          ) : ledger.map((t) => (
            <dl key={t.transaction_id} className="grid grid-cols-[110px_1fr] gap-y-1 px-5 py-4 font-mono text-[12px]">
              {["transaction_id", "amount", "currency", "recipient", "idempotency_key", "decision_id"].map((k) => (
                <div key={k} className="contents"><dt className="text-fg-subtle">{k.replace("_id", "")}</dt><dd className="break-all text-fg">{t[k]}</dd></div>
              ))}
            </dl>
          ))}
        </Card>
        <Card>
          <CardHeader icon={History} title="Case history" subtitle="Recorded by protected services and controls" />
          <ul className="max-h-[320px] space-y-2 overflow-y-auto px-5 py-4">
            {c.history.map((h, i) => (
              <li key={i} className="flex gap-3 text-[12.5px]">
                <span className="w-16 shrink-0 font-mono text-[11px] text-fg-subtle">{time(h.at)}</span>
                <span className="min-w-0">
                  <span className="text-fg">{h.detail}</span>
                  <span className="block font-mono text-[11px] text-fg-subtle">
                    {h.actor} · {h.kind}{h.to_state ? ` → ${h.to_state}` : ""}{h.audit_reference ? ` · ${h.audit_reference}` : ""}
                  </span>
                </span>
              </li>
            ))}
          </ul>
        </Card>
      </div>
    </div>
  );
}

export function GovernmentWorkflow() {
  const caps = useApi<SystemCapabilities>("/api/system/capabilities", { live: true });
  const citizens = useApi<ListResponse<Citizen>>("/api/citizens");
  const scenarios = useApi<WorkflowScenarioInfo[]>("/api/workflow/scenarios");
  const cases = useApi<CaseSummary[]>("/api/workflow/cases", { live: true });
  const [citizen, setCitizen] = useState("C-1001");
  const [running, setRunning] = useState<string | null>(null);
  const [run, setRun] = useState<WorkflowRun | null>(null);
  const [detail, setDetail] = useState<CaseDetail | null>(null);
  const [error, setError] = useState<string | null>(null);
  const enabled = caps.status === "success" && caps.data.developer_demo_enabled;

  async function start(key: string, selectable: boolean) {
    setRunning(key);
    setError(null);
    setDetail(null);
    try {
      const r = await apiPost<WorkflowRun>(`/api/workflow/scenarios/${key}/run`, { citizen_ref: selectable ? citizen : "C-1001" });
      setRun(r);
      invalidate("/api/audit", "/api/mandates", "/api/workflow/cases");
      cases.reload();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setRunning(null);
    }
  }

  async function open(caseId: string) {
    setError(null);
    try {
      setDetail(await apiGet<CaseDetail>(`/api/workflow/cases/${caseId}`));
      setRun(null);
    } catch (e) {
      setError((e as Error).message);
    }
  }

  const shownCase = run?.case ?? detail?.case ?? null;

  return (
    <>
      <PageHeader
        eyebrow="Phase 2 · Protected workflows"
        title="Government Workflow"
        titleAr="سير العمل الحكومي"
        description="A synthetic residency renewal run by three simulated agents. Every operation is a signed request through the WAKALA gateway, bound to one case — an agent authorized for a service in general still cannot act outside the case it is handling."
        actions={<SyntheticBadge />}
      />
      <Notice tone="plan" icon={Bot} title="Simulated agents, real enforcement">
        The agents are deterministic Python scripts, not model-driven AI. The gateway, mandates, case checks, protected
        services, ledger and audit trail are real. Outcomes below are returned by the backend for each run; nothing is pre-recorded.
      </Notice>

      <div className="grid gap-6 xl:grid-cols-[320px_1fr]">
        <div className="flex flex-col gap-6">
          <Card>
            <CardHeader icon={User} title="Citizen" subtitle="Applies to scenario A" />
            <ApiView state={citizens} reload={citizens.reload}>
              {(data) => (
                <ul className="p-2">
                  {data.items.map((c) => (
                    <li key={c.citizen_ref}>
                      <button
                        onClick={() => setCitizen(c.citizen_ref)}
                        aria-pressed={citizen === c.citizen_ref}
                        className={clsx("flex w-full items-center justify-between rounded-lg px-3 py-2 text-left transition-colors",
                          citizen === c.citizen_ref ? "bg-ink-750" : "hover:bg-ink-800")}
                      >
                        <span>
                          <span className="block text-[13.5px] text-fg">{c.full_name}</span>
                          <span className="font-mono text-[11px] text-fg-subtle">{c.citizen_ref}</span>
                        </span>
                        <Badge tone={c.service_attributes.renewal_eligible ? "trust" : "neutral"}>
                          {c.service_attributes.renewal_eligible ? "eligible" : "not eligible"}
                        </Badge>
                      </button>
                    </li>
                  ))}
                </ul>
              )}
            </ApiView>
          </Card>

          <Card>
            <CardHeader icon={Play} title="Scenarios" subtitle="Each run opens a new case" />
            {caps.status === "success" && !enabled ? (
              <p className="px-5 py-4 text-[13px] text-fg-muted">
                Disabled. Start the backend with <span className="font-mono">python run_dev.py</span> (dev mode, local only).
              </p>
            ) : (
              <ApiView state={scenarios} reload={scenarios.reload}>
                {(list) => (
                  <div className="space-y-2 p-3">
                    {list.map((s) => {
                      const Icon = SCENARIO_ICON[s.key] ?? Play;
                      return (
                        <button
                          key={s.key}
                          onClick={() => start(s.key, s.citizen_selectable)}
                          disabled={running !== null}
                          className={clsx("w-full rounded-xl border px-3.5 py-3 text-left transition-colors disabled:cursor-wait",
                            run?.scenario === s.key ? "border-trust/50 bg-ink-750" : "border-line bg-ink-800 hover:border-line-strong")}
                        >
                          <span className="flex items-center gap-2 text-[13.5px] font-medium text-fg">
                            {running === s.key ? <Loader2 className="size-4 animate-spin" aria-hidden /> : <Icon className="size-4 text-trust" aria-hidden />}
                            {s.title}
                          </span>
                          <span className="mt-1 block text-[12px] leading-snug text-fg-subtle">{s.description}</span>
                          {s.citizen_selectable && <span className="mt-1 block font-mono text-[11px] text-cyan">citizen {citizen}</span>}
                        </button>
                      );
                    })}
                  </div>
                )}
              </ApiView>
            )}
          </Card>

          <Card>
            <CardHeader icon={Clock} title="Recent cases" subtitle="GET /api/workflow/cases" />
            <ApiView state={cases} reload={cases.reload}>
              {(list) => list.length === 0 ? (
                <p className="px-5 py-4 text-[13px] text-fg-subtle">No cases yet.</p>
              ) : (
                <ul className="max-h-[320px] overflow-y-auto p-2">
                  {list.map((c) => (
                    <li key={c.case_id}>
                      <button onClick={() => open(c.case_id)}
                        className={clsx("flex w-full items-center justify-between rounded-lg px-3 py-2 text-left hover:bg-ink-800",
                          shownCase?.case_id === c.case_id && "bg-ink-750")}>
                        <span>
                          <span className="block font-mono text-[12.5px] text-fg">{c.case_id}</span>
                          <span className="font-mono text-[11px] text-fg-subtle">{c.citizen_ref} · {time(c.created_at)}</span>
                        </span>
                        <Badge tone={STATE_TONE[c.state]}>{c.state.replace(/_/g, " ").toLowerCase()}</Badge>
                      </button>
                    </li>
                  ))}
                </ul>
              )}
            </ApiView>
          </Card>
        </div>

        <div className="flex min-w-0 flex-col gap-6">
          {error && <p className="rounded-xl border border-deny/30 bg-deny-soft px-4 py-3 text-[13px] text-deny">{error}</p>}
          {!shownCase && !error && (
            <Card>
              <EmptyState icon={Landmark} title="Run a scenario or open a case">
                Scenario A completes a renewal end to end. B and C show case-bound denials. D compares an isolated weak
                baseline with WAKALA on the same request.
              </EmptyState>
            </Card>
          )}
          {shownCase && <CaseCard c={shownCase} />}
          {run?.baseline && <Baseline b={run.baseline} />}
          {run && (
            <Card>
              <CardHeader icon={History} title={`Execution timeline · ${run.title}`}
                subtitle={`${run.steps.length} operations · ${run.steps.filter((s) => s.decision?.allowed).length} allowed · ${run.steps.filter((s) => s.decision && !s.decision.allowed).length} denied`} />
              <ol className="relative space-y-4 p-5 before:absolute before:bottom-6 before:left-[34px] before:top-6 before:w-px before:bg-line">
                {run.steps.map((s) => <StepRow key={s.index} s={s} />)}
              </ol>
            </Card>
          )}
          {shownCase && (
            <CaseExtras c={shownCase} ledger={run?.ledger ?? detail?.ledger ?? []} events={run?.audit_events ?? detail?.audit_events ?? []} />
          )}
        </div>
      </div>
    </>
  );
}
