import clsx from "clsx";
import { ArrowRight, Bot, CheckCircle2, Circle, Database, FileSignature, Gauge, Landmark, Link2, RefreshCw, ShieldCheck, Users, type LucideIcon } from "lucide-react";
import type { ReactNode } from "react";
import { Link } from "react-router-dom";
import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { ApiView, Badge, Card, CardHeader, PageHeader, SyntheticBadge } from "@/components/ui";
import { useApi } from "@/hooks/useApi";
import { agentStatusTone, humanize, riskTone } from "@/lib/format";
import type { AgentPassport, AuditEventList, AuditIntegrity, Citizen, IssuerView, ListResponse, MandateView, SystemCapabilities } from "@/types/api";

function StatCard({ icon: Icon, label, value, detail, source }: { icon: LucideIcon; label: string; value: ReactNode; detail: ReactNode; source: string }) {
  return (
    <div className="card flex flex-col justify-between p-5">
      <div className="flex items-center justify-between">
        <p className="text-[13px] font-medium text-fg-muted">{label}</p>
        <Icon className="size-4 text-fg-subtle" aria-hidden />
      </div>
      <p className="mt-3 text-[34px] font-semibold leading-none tracking-tight text-fg tabular-nums">{value}</p>
      <p className="mt-2 text-[13px] text-fg-muted">{detail}</p>
      <p className="mt-4 border-t border-line pt-3 font-mono text-[11px] text-fg-subtle">source · {source}</p>
    </div>
  );
}

function Skeleton() {
  return <span className="inline-block h-8 w-12 animate-pulse rounded bg-ink-750" />;
}

function SetupInventory() {
  const agents = useApi<ListResponse<AgentPassport>>("/api/agents");
  const mandates = useApi<ListResponse<MandateView>>("/api/mandates", { live: true });
  const issuers = useApi<ListResponse<IssuerView>>("/api/issuers");
  const citizens = useApi<ListResponse<Citizen>>("/api/citizens");

  const a = agents.data?.items;
  const m = mandates.data?.items;
  const i = issuers.data?.items;
  const c = citizens.data?.items;

  return (
    <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
      <StatCard
        icon={Bot}
        label="Registered agents"
        value={a ? a.length : <Skeleton />}
        detail={a ? `${a.filter((x) => x.identity_key_reference.provisioning_status === "provisioned").length} with registered Ed25519 key · ${a.filter((x) => x.status === "active").length} active` : "…"}
        source="GET /api/agents"
      />
      <StatCard
        icon={FileSignature}
        label="Valid signed mandates"
        value={m ? m.filter((x) => x.verification.valid).length : <Skeleton />}
        detail={m ? `of ${m.length} stored · verified now` : "…"}
        source="GET /api/mandates"
      />
      <StatCard
        icon={Landmark}
        label="Trusted issuers"
        value={i ? i.filter((x) => x.issuer.status === "active" && x.key_registered).length : <Skeleton />}
        detail={i ? "each limited to its declared authority" : "…"}
        source="GET /api/issuers"
      />
      <StatCard
        icon={Users}
        label="Synthetic citizens"
        value={c ? c.length : <Skeleton />}
        detail={c ? `${c.filter((x) => x.service_attributes.renewal_eligible).length} eligible for renewal` : "…"}
        source="GET /api/citizens"
      />
    </div>
  );
}

function SecurityActivity() {
  const events = useApi<AuditEventList>("/api/audit/events?limit=500", { live: true });
  const integrity = useApi<AuditIntegrity>("/api/audit/integrity", { live: true });
  const reload = () => {
    events.reload();
    integrity.reload();
  };
  return (
    <Card>
      <CardHeader
        icon={ShieldCheck}
        title="Measured security activity"
        subtitle="Counted from the audit trail. Every number is a real gateway decision."
        right={
          <div className="flex items-center gap-2">
            <Badge tone="trust" dot>Enforcement engine connected</Badge>
            <button onClick={reload} className="inline-flex items-center gap-1.5 rounded-lg border border-line px-2.5 py-1.5 text-[12px] text-fg-muted hover:bg-ink-750 hover:text-fg">
              <RefreshCw className="size-3.5" aria-hidden /> Refresh
            </button>
          </div>
        }
      />
      <ApiView state={events} reload={events.reload}>
        {(data) => {
          const latencies = data.items.map((e) => e.decision_latency_ms).filter((x): x is number => x !== null).sort((x, y) => x - y);
          const median = latencies.length ? latencies[Math.floor(latencies.length / 2)] : null;
          const tiles = [
            { label: "Authorization decisions", value: String(data.count), note: "audit_events rows" },
            { label: "Allowed", value: String(data.allowed_count), note: "passed all eight checks", tone: "text-trust" },
            { label: "Denied", value: String(data.denied_count), note: "default-deny outcomes", tone: data.denied_count ? "text-deny" : undefined },
            {
              label: "Audit chain",
              value: integrity.status === "success" ? (integrity.data.valid ? "Intact" : "Broken") : "…",
              note: integrity.status === "success" ? `${integrity.data.event_count} events hash-chained` : "verifying",
              tone: integrity.status === "success" ? (integrity.data.valid ? "text-trust" : "text-deny") : undefined,
            },
          ];
          return (
            <>
              <div className="grid divide-y divide-line sm:grid-cols-2 sm:divide-y-0 xl:grid-cols-4 xl:divide-x">
                {tiles.map((t) => (
                  <div key={t.label} className="px-5 py-5">
                    <p className="text-[13px] text-fg-muted">{t.label}</p>
                    <p className={clsx("mt-2 text-[28px] font-semibold leading-none tabular-nums", t.tone ?? "text-fg")}>{t.value}</p>
                    <p className="mt-2 text-[12px] text-fg-subtle">{t.note}</p>
                  </div>
                ))}
              </div>
              <p className="border-t border-line px-5 py-3 text-[12px] text-fg-subtle">
                {data.count === 0
                  ? "No decisions recorded yet. Run a developer scenario in the Simulation Lab or call POST /api/gateway/execute."
                  : `Median measured gateway latency ${median?.toFixed(2)} ms across the last ${latencies.length} recorded decisions (local machine; not a benchmark).`}
              </p>
            </>
          );
        }}
      </ApiView>
    </Card>
  );
}

const PATH_STEPS = [
  { title: "AI agent", detail: "Signs a tool request with its Ed25519 key. Untrusted.", icon: Bot },
  { title: "WAKALA gateway", detail: "Verifies identity and signed mandate, runs 8 checks, audits. Default-deny.", icon: ShieldCheck },
  { title: "Protected tool", detail: "Runs only via the server-side registry, only if allowed.", icon: Database },
];

function EnforcementPath() {
  return (
    <Card className="flex flex-col">
      <CardHeader icon={Gauge} title="Enforcement path" subtitle="Every sensitive action is independently authorized" right={<Badge tone="trust">Phase 1 · active</Badge>} />
      <div className="flex flex-1 flex-col justify-center p-5">
        <ol className="flex flex-col items-stretch gap-3 md:flex-row md:items-center">
          {PATH_STEPS.map((step, i) => (
            <li key={step.title} className="flex flex-1 items-center gap-3">
              <div className={clsx("flex-1 rounded-xl border p-4", i === 1 ? "border-trust/30 bg-trust-soft" : "border-line bg-ink-800")}>
                <step.icon className={clsx("size-5", i === 1 ? "text-trust" : "text-fg-subtle")} aria-hidden />
                <p className="mt-3 text-[14px] font-semibold text-fg">{step.title}</p>
                <p className="mt-1 text-[12.5px] leading-snug text-fg-muted">{step.detail}</p>
              </div>
              {i < PATH_STEPS.length - 1 && <ArrowRight className="hidden size-4 shrink-0 text-fg-subtle md:block" aria-hidden />}
            </li>
          ))}
        </ol>
        <p className="mt-5 rounded-lg border border-line bg-ink-900/60 px-4 py-3 text-[13px] leading-relaxed text-fg-muted">
          <span className="font-semibold text-fg">Core rule.</span> An agent never gains authority merely because it runs
          inside a trusted government system. Instructions in documents or prompts carry no authority; only a valid,
          issuer-signed, task-limited mandate does.
        </p>
      </div>
    </Card>
  );
}

function CapabilityStatusCard() {
  const caps = useApi<SystemCapabilities>("/api/system/capabilities");
  return (
    <Card>
      <CardHeader icon={CheckCircle2} title="Capability status" subtitle="Reported by GET /api/system/capabilities" />
      <ApiView state={caps} reload={caps.reload}>
        {(data) => {
          const phases = [...new Set(data.capabilities.map((c) => c.phase))].sort();
          const chart = phases.map((p) => ({
            phase: `Phase ${p}`,
            implemented: data.capabilities.filter((c) => c.phase === p && c.status === "implemented").length,
            planned: data.capabilities.filter((c) => c.phase === p && c.status === "planned").length,
          }));
          return (
            <div className="p-5">
              <div className="mb-4 flex items-center gap-4 text-[13px]">
                <span className="flex items-center gap-2 text-fg-muted">
                  <span className="size-2.5 rounded-sm bg-trust" /> Implemented <b className="text-fg">{data.implemented_count}</b>
                </span>
                <span className="flex items-center gap-2 text-fg-muted">
                  <span className="size-2.5 rounded-sm bg-plan/60" /> Planned <b className="text-fg">{data.planned_count}</b>
                </span>
              </div>
              <div className="h-[150px]">
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart data={chart} margin={{ top: 4, right: 4, bottom: 0, left: -24 }} barCategoryGap="28%">
                    <CartesianGrid vertical={false} stroke="#1b2a46" />
                    <XAxis dataKey="phase" tick={{ fill: "#64748f", fontSize: 12 }} axisLine={false} tickLine={false} />
                    <YAxis allowDecimals={false} tick={{ fill: "#64748f", fontSize: 12 }} axisLine={false} tickLine={false} />
                    <Tooltip
                      cursor={{ fill: "#16243f66" }}
                      contentStyle={{ background: "#0d172b", border: "1px solid #263a5e", borderRadius: 10, fontSize: 12 }}
                      labelStyle={{ color: "#e7edf7" }}
                    />
                    <Bar dataKey="implemented" stackId="a" fill="#2dd4bf" name="Implemented" />
                    <Bar dataKey="planned" stackId="a" fill="#a5b4fc99" name="Planned" radius={[4, 4, 0, 0]} />
                  </BarChart>
                </ResponsiveContainer>
              </div>
              <ul className="mt-5 space-y-2 border-t border-line pt-4">
                {data.capabilities.map((cap) => (
                  <li key={cap.key} className="flex min-w-0 items-center gap-2.5 text-[13px]">
                    {cap.status === "implemented" ? (
                      <CheckCircle2 className="size-3.5 shrink-0 text-trust" aria-label="Implemented" />
                    ) : (
                      <Circle className="size-3.5 shrink-0 text-plan/70" aria-label="Planned" />
                    )}
                    <span className={clsx("truncate", cap.status === "implemented" ? "text-fg" : "text-fg-muted")} title={cap.description}>
                      {cap.name}
                    </span>
                    <span className="ml-auto font-mono text-[11px] text-fg-subtle">P{cap.phase}</span>
                  </li>
                ))}
              </ul>
            </div>
          );
        }}
      </ApiView>
    </Card>
  );
}

function AgentInventory() {
  const agents = useApi<ListResponse<AgentPassport>>("/api/agents");
  return (
    <Card>
      <CardHeader
        icon={Bot}
        title="Agent inventory"
        subtitle="Synthetic registry records with live key state"
        right={
          <Link to="/agents" className="inline-flex items-center gap-1 text-[13px] text-trust hover:underline">
            Open registry <ArrowRight className="size-3.5" aria-hidden />
          </Link>
        }
      />
      <ApiView state={agents} reload={agents.reload}>
        {(data) => (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-[13.5px]">
              <thead>
                <tr className="border-b border-line text-[11.5px] uppercase tracking-wider text-fg-subtle">
                  <th className="px-5 py-3 font-medium">Agent</th>
                  <th className="px-5 py-3 font-medium">Owning entity</th>
                  <th className="px-5 py-3 font-medium">Risk</th>
                  <th className="px-5 py-3 font-medium">Status</th>
                  <th className="px-5 py-3 font-medium">Identity key</th>
                </tr>
              </thead>
              <tbody>
                {data.items.map((a) => (
                  <tr key={a.agent_id} className="border-b border-line/60 last:border-0 hover:bg-ink-800/60">
                    <td className="px-5 py-3.5">
                      <p className="font-medium text-fg">{a.name}</p>
                      <p className="font-mono text-[11.5px] text-fg-subtle">{a.agent_id}</p>
                    </td>
                    <td className="px-5 py-3.5 text-fg-muted">{a.owner_entity}</td>
                    <td className="px-5 py-3.5"><Badge tone={riskTone[a.risk_level]}>{humanize(a.risk_level)}</Badge></td>
                    <td className="px-5 py-3.5"><Badge tone={agentStatusTone[a.status]} dot>{humanize(a.status)}</Badge></td>
                    <td className="px-5 py-3.5">
                      <span className="flex items-center gap-2">
                        <Badge tone={a.identity_key_reference.provisioning_status === "provisioned" ? "trust" : "warn"}>
                          {humanize(a.identity_key_reference.provisioning_status)}
                        </Badge>
                        <span className="hidden font-mono text-[11px] text-fg-subtle lg:inline" title={a.identity_key_reference.public_key_fingerprint ?? ""}>
                          <Link2 className="mr-1 inline size-3" aria-hidden />
                          {a.identity_key_reference.public_key_fingerprint?.slice(7, 19) ?? "—"}…
                        </span>
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </ApiView>
    </Card>
  );
}

export function CommandCenter() {
  return (
    <>
      <PageHeader
        eyebrow="Phase 1 · Security engine"
        title="Command Center"
        titleAr="مركز القيادة"
        description="Operational overview of the WAKALA authorization layer. Registry inventory is synthetic configuration data; security activity is counted from real, audited gateway decisions."
        actions={<SyntheticBadge />}
      />

      <div className="mb-3 flex items-center gap-3">
        <h2 className="eyebrow">Registry inventory</h2>
        <span className="h-px flex-1 bg-line" />
        <span className="text-[12px] text-fg-subtle">Synthetic configuration · not security activity</span>
      </div>
      <SetupInventory />

      <div className="mb-3 mt-9 flex items-center gap-3">
        <h2 className="eyebrow">Security activity</h2>
        <span className="h-px flex-1 bg-line" />
        <span className="text-[12px] text-fg-subtle">Measured from the audit trail</span>
      </div>
      <SecurityActivity />

      <div className="mt-6 grid gap-6 xl:grid-cols-2">
        <EnforcementPath />
        <CapabilityStatusCard />
      </div>
      <div className="mt-6">
        <AgentInventory />
      </div>
    </>
  );
}
