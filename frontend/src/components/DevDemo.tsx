import clsx from "clsx";
import { CheckCircle2, CircleSlash, Loader2, Play, Terminal, XCircle } from "lucide-react";
import { useState } from "react";
import { ApiView, Badge, Card, CardHeader, EmptyState } from "@/components/ui";
import { invalidate, useApi } from "@/hooks/useApi";
import { apiPost } from "@/lib/api";
import { humanize } from "@/lib/format";
import type { DevScenarioInfo, DevScenarioResult, SystemCapabilities } from "@/types/api";

const CHECK_LABEL: Record<string, string> = {
  identity: "1 Identity",
  agent_status: "2 Agent status",
  mandate_integrity: "3 Mandate integrity",
  mandate_validity: "4 Mandate validity",
  tool_permission: "5 Tool permission",
  resource_scope: "6 Resource scope",
  action_constraints: "7 Action constraints",
  request_context: "8 Request context",
};

function Result({ r }: { r: DevScenarioResult }) {
  const d = r.decision;
  return (
    <div className="animate-fade-in">
      <div className={clsx("flex flex-wrap items-center gap-3 border-b px-5 py-4", d.allowed ? "border-trust/25 bg-trust-soft" : "border-deny/25 bg-deny-soft")}>
        <span className={clsx("text-[22px] font-semibold tracking-wide", d.allowed ? "text-trust" : "text-deny")}>{d.allowed ? "ALLOW" : "DENY"}</span>
        <div className="flex flex-wrap gap-1.5">
          {d.reason_codes.map((c) => <Badge key={c} tone={d.allowed ? "trust" : "deny"}>{c}</Badge>)}
        </div>
        <span className="ml-auto font-mono text-[12px] text-fg-muted">measured {d.decision_latency_ms.toFixed(2)} ms</span>
      </div>
      <div className="grid gap-6 p-5 lg:grid-cols-2">
        <div>
          <p className="text-[13.5px] text-fg">{d.human_readable_explanation}</p>
          {r.note && <p className="mt-2 text-[12.5px] text-fg-muted">{r.note}</p>}
          <dl className="mt-4 grid gap-x-4 gap-y-1.5 font-mono text-[11.5px] sm:grid-cols-[120px_1fr]">
            {[
              ["agent", r.request.agent_id], ["tool", r.request.tool_name], ["mandate", r.request.mandate_id],
              ["target", r.request.target_resource],
              ["parameters", Object.entries(r.request.parameters).map(([k, v]) => `${k}=${String(v)}`).join(", ")],
              ["nonce", r.request.nonce], ["request digest", r.request.request_digest.slice(0, 24) + "…"],
              ["decision", d.decision_id], ["audit event", d.audit_reference], ["policy", d.policy_version],
            ].map(([k, v]) => (
              <div key={k} className="contents">
                <dt className="text-fg-subtle">{k}</dt>
                <dd className="break-all text-fg-muted">{v}</dd>
              </div>
            ))}
          </dl>
        </div>
        <div>
          <p className="mb-2 text-[11.5px] font-medium uppercase tracking-wider text-fg-subtle">Check trace</p>
          <ul className="space-y-1">
            {r.checks.map((c) => (
              <li key={c.name} className="flex items-center gap-2 text-[13px]">
                {c.status === "passed" ? <CheckCircle2 className="size-4 text-trust" aria-label="passed" />
                  : c.status === "failed" ? <XCircle className="size-4 text-deny" aria-label="failed" />
                  : <CircleSlash className="size-4 text-fg-subtle" aria-label="not evaluated" />}
                <span className={c.status === "not_evaluated" ? "text-fg-subtle" : "text-fg"}>{CHECK_LABEL[c.name] ?? c.name}</span>
                {c.reason_codes.length > 0 && <span className="ml-auto font-mono text-[11px] text-deny">{c.reason_codes.join(", ")}</span>}
              </li>
            ))}
          </ul>
          <div className={clsx("mt-4 rounded-lg border px-3 py-2.5 text-[12.5px]", r.executed ? "border-trust/25 bg-trust-soft text-trust" : "border-line bg-ink-800 text-fg-muted")}>
            <b>Protected tool:</b> {humanize(r.execution_status)}
            {r.executed && r.result && (
              <span className="mt-1 block font-mono text-[11.5px] text-fg-muted">
                {Object.entries(r.result).map(([k, v]) => `${k}=${String(v)}`).join(" · ")}
              </span>
            )}
            {!r.executed && r.execution_status === "denied" && <span className="block text-[12px] text-fg-subtle">The tool handler was never invoked.</span>}
            {r.execution_status === "no_handler_registered" && (
              <span className="block text-[12px] text-fg-subtle">Authorized, but payment execution is a Phase 2 mock service — nothing was paid.</span>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

export function DevDemo() {
  const caps = useApi<SystemCapabilities>("/api/system/capabilities", { live: true });
  const enabled = caps.status === "success" && caps.data.developer_demo_enabled;
  const scenarios = useApi<DevScenarioInfo[]>(enabled ? "/api/dev/scenarios" : null);
  const [running, setRunning] = useState<string | null>(null);
  const [result, setResult] = useState<DevScenarioResult | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function run(key: string) {
    setRunning(key);
    setError(null);
    try {
      setResult(await apiPost<DevScenarioResult>(`/api/dev/scenarios/${key}/run`));
      invalidate("/api/audit", "/api/mandates");
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setRunning(null);
    }
  }

  return (
    <Card className="mb-6">
      <CardHeader
        icon={Terminal}
        title="Developer demonstration · real gateway"
        subtitle="Fixed server-side scenarios signed with dedicated development identities. The browser holds no keys and cannot choose the agent or parameters."
        right={<Badge tone="warn">Development only</Badge>}
      />
      {caps.status !== "success" ? (
        <ApiView state={caps} reload={caps.reload}>{() => null}</ApiView>
      ) : !enabled ? (
        <EmptyState icon={Terminal} title="Developer demonstration is disabled">
          Start the backend with <span className="font-mono">python run_dev.py</span> (sets <span className="font-mono">WAKALA_DEV_MODE=1</span>) to enable
          the predefined scenarios. They are off by default and answer local clients only.
        </EmptyState>
      ) : (
        <ApiView state={scenarios} reload={scenarios.reload}>
          {(list) => (
            <>
              <div className="grid gap-2 p-5 sm:grid-cols-2 xl:grid-cols-4">
                {list.map((s) => (
                  <button
                    key={s.key}
                    onClick={() => run(s.key)}
                    disabled={running !== null}
                    title={s.designed_to_test}
                    className={clsx(
                      "group flex flex-col items-start gap-1 rounded-xl border px-3.5 py-3 text-left transition-colors disabled:cursor-wait",
                      result?.scenario.key === s.key ? "border-trust/50 bg-ink-750" : "border-line bg-ink-800 hover:border-line-strong hover:bg-ink-750",
                    )}
                  >
                    <span className="flex w-full items-center gap-2 text-[13.5px] font-medium text-fg">
                      {running === s.key ? <Loader2 className="size-3.5 animate-spin" aria-hidden /> : <Play className="size-3.5 text-trust" aria-hidden />}
                      {s.title}
                    </span>
                    <span className="text-[12px] leading-snug text-fg-subtle">{s.description}</span>
                  </button>
                ))}
              </div>
              {error && <p className="mx-5 mb-5 rounded-lg border border-deny/30 bg-deny-soft px-3 py-2 text-[13px] text-deny">{error}</p>}
              {result ? (
                <div className="border-t border-line"><Result r={result} /></div>
              ) : (
                <p className="border-t border-line px-5 py-4 text-[13px] text-fg-subtle">
                  Choose a scenario. Each click sends one signed request through <span className="font-mono">Gateway.execute()</span> and writes one
                  real audit event (two for the replay scenario).
                </p>
              )}
            </>
          )}
        </ApiView>
      )}
    </Card>
  );
}
