import { CHART } from "@/lib/chartTheme";
import "@xyflow/react/dist/style.css";
import clsx from "clsx";
import {
  Ban, Bot, CheckCircle2, FileSignature, GitBranch, KeyRound, Landmark, Loader2, Play, RefreshCw, ShieldAlert, ShieldCheck,
  XCircle, type LucideIcon,
} from "lucide-react";
import { useMemo, useState } from "react";
import { Background, Handle, MarkerType, Position, ReactFlow, type Edge, type Node, type NodeProps } from "@xyflow/react";
import { ApiView, Badge, Card, CardHeader, EmptyState, Notice, PageHeader, SyntheticBadge } from "@/components/ui";
import { CaseView } from "@/components/CaseView";
import { invalidate, useApi } from "@/hooks/useApi";
import { apiPost } from "@/lib/api";
import { humanize, type Tone } from "@/lib/format";
import type {
  AuditEvent, AuthorityGraph, AuthorityGraphNode, CaseSummary, SystemCapabilities, WorkflowRun, WorkflowScenarioInfo,
} from "@/types/api";

const DELEGATION_SCENARIOS = ["delegated_renewal", "delegation_attacks", "selective_revocation"];

const KIND_ICON: Record<string, LucideIcon> = {
  case: Landmark, issuer: KeyRound, mandate: FileSignature, child_mandate: GitBranch, agent: Bot, denied_attempt: Ban,
};
const KIND_LABEL: Record<string, string> = {
  case: "Government case", issuer: "Mandate issuer", mandate: "Root mandate", child_mandate: "Delegated child mandate",
  agent: "Agent", denied_attempt: "Denied delegation attempt",
};
const COLUMN: Record<string, number> = { issuer: 0, case: 1, mandate: 2, child_mandate: 3, denied_attempt: 3, agent: 4 };

function statusTone(s: string): Tone {
  if (["active", "verified"].includes(s)) return "trust";
  if (["revoked", "expired", "not_yet_valid", "suspended"].includes(s)) return "warn";
  if (["invalid", "denied"].includes(s)) return "deny";
  return "neutral";
}
const EDGE_COLOR: Record<Tone, string> = { trust: CHART.emerald, warn: CHART.warn, deny: CHART.deny, plan: CHART.plan, neutral: CHART.neutral };

type FlowData = { node: AuthorityGraphNode };
type FlowNode = Node<FlowData, "authority">;

function AuthorityNode({ data, selected }: NodeProps<FlowNode>) {
  const n = data.node;
  const tone = statusTone(n.status);
  const Icon = KIND_ICON[n.kind] ?? FileSignature;
  return (
    <div className={clsx(
      "w-[210px] rounded-xl border bg-ink-800 px-3.5 py-3 transition-colors",
      n.kind === "child_mandate" && "border-cyan/40",
      n.kind === "denied_attempt" && "border-dashed border-deny/60 bg-deny-soft/40",
      n.kind !== "child_mandate" && n.kind !== "denied_attempt" && "border-line-strong",
      tone === "warn" && "border-warn/50", tone === "deny" && n.kind !== "denied_attempt" && "border-deny/50",
      selected && "!border-trust shadow-[0_0_0_3px_#0e4d4822]",
    )}>
      <Handle type="target" position={Position.Left} className="!size-2 !border-0 !bg-line-strong" />
      <div className="flex items-center gap-2">
        <Icon className={clsx("size-4 shrink-0", n.kind === "child_mandate" ? "text-cyan" : n.kind === "denied_attempt" ? "text-deny" : "text-fg-subtle")} aria-hidden />
        <p className="truncate font-mono text-[12px] font-semibold text-fg">{n.label}</p>
      </div>
      <p className="mt-1 truncate text-[11px] text-fg-subtle">{n.sublabel}</p>
      <span className={clsx("mt-2 inline-block rounded-full border px-1.5 py-px text-[10px] uppercase tracking-wider",
        tone === "trust" && "border-trust/30 text-trust", tone === "warn" && "border-warn/30 text-warn",
        tone === "deny" && "border-deny/30 text-deny", tone === "neutral" && "border-line text-fg-subtle")}>
        {n.status.replace(/_/g, " ")}
      </span>
      <Handle type="source" position={Position.Right} className="!size-2 !border-0 !bg-line-strong" />
    </div>
  );
}
const nodeTypes = { authority: AuthorityNode };

function layout(graph: AuthorityGraph): { nodes: FlowNode[]; edges: Edge[] } {
  const rows: Record<number, number> = {};
  const nodes: FlowNode[] = graph.nodes.map((n) => {
    const col = COLUMN[n.kind] ?? 2;
    const row = (rows[col] = (rows[col] ?? -1) + 1);
    return { id: n.id, type: "authority", position: { x: col * 270, y: row * 118 }, data: { node: n },
             draggable: false, connectable: false };
  });
  // Vertically centre each column.
  const heights: Record<number, number> = {};
  for (const [c, r] of Object.entries(rows)) heights[Number(c)] = (r + 1) * 118;
  const max = Math.max(...Object.values(heights));
  nodes.forEach((n) => { n.position.y += (max - (heights[COLUMN[n.data.node.kind] ?? 2] ?? max)) / 2; });
  const edges: Edge[] = graph.edges.map((e) => {
    const tone: Tone = e.kind === "denied_delegation" ? "deny" : statusTone(e.status);
    const color = e.kind === "delegated" && tone === "trust" ? CHART.navy : EDGE_COLOR[tone];
    return {
      id: e.id, source: e.source, target: e.target,
      label: e.kind === "delegated" ? e.label : e.kind === "denied_delegation" ? `denied · ${e.label.split(", ")[0]?.replace("DENY_", "")}` : undefined,
      style: { stroke: color, strokeWidth: e.kind === "delegated" ? 2 : 1.3,
               strokeDasharray: tone === "deny" || tone === "warn" ? "5 4" : undefined },
      markerEnd: { type: MarkerType.ArrowClosed, color, width: 15, height: 15 },
      labelStyle: { fill: CHART.tick, fontSize: 10.5 }, labelBgStyle: { fill: CHART.surface }, labelBgPadding: [5, 2] as [number, number],
    };
  });
  return { nodes, edges };
}

type MandateData = {
  mandate: { issuer_id: string; agent_id: string; case_id: string | null; parent_mandate_id: string | null;
             delegated_task: string | null; delegation_depth: number; max_delegation_depth: number;
             signature_metadata: { algorithm: string; key_id: string } | null };
  scope: { citizen_ref: string; request_id: string };
  effective_permissions: string[];
  commissionable_tasks: string[];
  resources: { resource_type: string; access: string; identifiers: string[] }[];
  expires_at: string;
  decision_counts: Record<string, number>;
  verification: { valid: boolean; reason_codes: string[]; chain_length: number };
};

function Row({ k, v }: { k: string; v: string }) {
  return <div className="contents"><dt className="text-fg-subtle">{k}</dt><dd className="break-all text-fg">{v}</dd></div>;
}

function Evidence({ node }: { node: AuthorityGraphNode }) {
  const d = node.data;
  const events: AuditEvent[] = d.audit_events ?? (d.audit_event ? [d.audit_event] : []);
  const m = d.mandate ? (d as MandateData) : null;
  return (
    <div className="space-y-4 p-5 text-[12.5px]">
      <div className="flex items-center gap-2">
        <Badge tone={statusTone(node.status)} dot>{node.status.replace(/_/g, " ")}</Badge>
        <span className="text-fg-subtle">{KIND_LABEL[node.kind]}</span>
      </div>
      {m && (
        <>
          <div className={clsx("rounded-lg border px-3 py-2", m.verification.valid ? "border-trust/30 bg-trust-soft" : "border-deny/30 bg-deny-soft")}>
            <p className={clsx("flex items-center gap-1.5 font-semibold", m.verification.valid ? "text-trust" : "text-deny")}>
              {m.verification.valid ? <CheckCircle2 className="size-4" aria-hidden /> : <XCircle className="size-4" aria-hidden />}
              {m.verification.valid ? `Verified now · chain of ${m.verification.chain_length}` : "Not usable"}
            </p>
            {m.verification.reason_codes.length > 0 && <p className="mt-1 font-mono text-[11px] text-deny">{m.verification.reason_codes.join(" · ")}</p>}
          </div>
          <dl className="grid grid-cols-[110px_1fr] gap-x-3 gap-y-1.5 font-mono text-[11.5px]">
            <Row k="issuer" v={m.mandate.issuer_id} />
            <Row k="agent" v={m.mandate.agent_id} />
            <Row k="case" v={m.mandate.case_id ?? "—"} />
            <Row k="citizen" v={m.scope.citizen_ref} />
            <Row k="may execute" v={m.effective_permissions.join(", ") || "—"} />
            <Row k="may commission" v={m.commissionable_tasks.join(", ") || "—"} />
            <Row k="resources" v={m.resources.map((r) => `${r.resource_type}:${r.access}[${r.identifiers.join(",")}]`).join(" ")} />
            <Row k="parent" v={m.mandate.parent_mandate_id ?? "— (root)"} />
            <Row k="task" v={m.mandate.delegated_task ?? "—"} />
            <Row k="depth" v={`${m.mandate.delegation_depth} / max ${m.mandate.max_delegation_depth}`} />
            <Row k="expires" v={new Date(m.expires_at).toLocaleTimeString("en-GB")} />
            <Row k="signature" v={`${m.mandate.signature_metadata?.algorithm ?? "UNSIGNED"} · ${m.mandate.signature_metadata?.key_id ?? ""}`} />
            <Row k="decisions" v={Object.entries(m.decision_counts).map(([k, v]) => `${k} ${v}`).join(" · ") || "none"} />
          </dl>
        </>
      )}
      {d.issuer && (
        <dl className="grid grid-cols-[110px_1fr] gap-x-3 gap-y-1.5 font-mono text-[11.5px]">
          <Row k="name" v={d.issuer.name} />
          <Row k="key" v={d.issuer.key_id} />
          <Row k="fingerprint" v={d.key_fingerprint ?? "—"} />
          <Row k="agents" v={d.issuer.authority.agents.join(", ")} />
          <Row k="tools" v={d.issuer.authority.tools.join(", ")} />
          <Row k="delegation only" v={String(d.issuer.authority.delegation_only)} />
        </dl>
      )}
      {d.case && (
        <p className="font-mono text-[11.5px] text-fg-muted">
          {d.case.citizen_ref} · {d.case.state} · {d.authority_model} authority · owner {d.service_owner}
          {d.case.authority_revoked ? " · AUTHORITY REVOKED" : ""}
        </p>
      )}
      {d.agent && <p className="break-all font-mono text-[11.5px] text-fg-muted">{d.agent.owner_entity} · {d.agent.status} · {d.agent.identity_key_reference.public_key_fingerprint}</p>}
      {events.length > 0 && (
        <div>
          <p className="eyebrow mb-2">Audit evidence</p>
          <ul className="space-y-1.5">
            {events.map((e) => (
              <li key={e.event_id} className="rounded-md border border-line bg-ink-900/60 px-2.5 py-1.5 font-mono text-[11px]">
                <span className={e.decision === "allowed" ? "text-trust" : e.decision === "denied" ? "text-deny" : "text-fg-subtle"}>
                  #{e.sequence} {e.decision}
                </span>{" "}
                <span className="text-fg">{e.action}</span>
                <span className="block text-fg-subtle">{e.reason_codes.join(" · ") || String(e.evidence_metadata.execution_status ?? "")} · {e.event_id}</span>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}

function GraphPanel({ caseId }: { caseId: string }) {
  const graph = useApi<AuthorityGraph>(`/api/workflow/cases/${caseId}/authority-graph`, { live: true });
  const [selected, setSelected] = useState<string | null>(null);
  const flow = useMemo(() => (graph.status === "success" ? layout(graph.data) : null), [graph.status, graph.data]);
  const node = graph.status === "success" ? graph.data.nodes.find((n) => n.id === selected) ?? null : null;
  return (
    <div className="grid gap-6 min-[1800px]:grid-cols-[1fr_380px]">
      <Card className="min-w-0 overflow-hidden">
        <CardHeader icon={GitBranch} title={`Authority chain · ${caseId}`}
          subtitle="Built from stored mandates, delegation records and audit events — click a node for evidence"
          right={
            <button onClick={graph.reload} className="inline-flex shrink-0 items-center gap-1.5 rounded-lg border border-line px-2.5 py-1.5 text-[12px] text-fg-muted hover:bg-ink-750">
              <RefreshCw className="size-3.5" aria-hidden /> Re-verify
            </button>
          } />
        <div className="flex flex-wrap items-center gap-x-4 gap-y-1 border-b border-line px-5 py-2 text-[11.5px] text-fg-subtle">
          <span className="flex items-center gap-1.5"><span className="h-0 w-5 border-t-2 border-cyan" /> verified delegation</span>
          <span className="flex items-center gap-1.5"><span className="h-0 w-5 border-t border-trust" /> verified signature / binding</span>
          <span className="flex items-center gap-1.5"><span className="h-0 w-5 border-t border-dashed border-warn" /> revoked / expired</span>
          <span className="flex items-center gap-1.5"><span className="h-0 w-5 border-t border-dashed border-deny" /> denied expansion / invalid</span>
        </div>
        <ApiView state={graph} reload={graph.reload}>
          {() => flow && (
            <div className="h-[520px] bg-ink-900/40">
              <ReactFlow key={caseId} nodes={flow.nodes.map((n) => ({ ...n, selected: n.id === selected }))} edges={flow.edges}
                nodeTypes={nodeTypes} onNodeClick={(_, n) => setSelected(n.id)} fitView fitViewOptions={{ padding: 0.08 }}
                nodesDraggable={false} nodesConnectable={false} zoomOnScroll={false} minZoom={0.3} maxZoom={1.5}
                proOptions={{ hideAttribution: true }}>
                <Background color={CHART.dots} gap={22} size={1} />
              </ReactFlow>
            </div>
          )}
        </ApiView>
      </Card>
      <Card className="min-w-0">
        <CardHeader icon={ShieldCheck} title={node ? node.label : "Evidence"} subtitle={node ? node.sublabel : "Select a node"} />
        {node ? <Evidence node={node} /> : <p className="p-5 text-[13px] text-fg-subtle">Click a case, issuer, mandate, agent or denied attempt.</p>}
      </Card>
    </div>
  );
}

function RunSteps({ run }: { run: WorkflowRun }) {
  return (
    <Card>
      <CardHeader icon={ShieldAlert} title={run.title}
        subtitle={`${run.steps.length} steps · ${run.steps.filter((s) => s.decision?.allowed).length} allowed · ${run.steps.filter((s) => s.decision && !s.decision.allowed).length} denied · real gateway decisions`} />
      <ol className="divide-y divide-line">
        {run.steps.map((s) => {
          const d = s.decision;
          const failed = s.checks.filter((c) => c.status === "failed").map((c) => c.name);
          return (
            <li key={s.index} className="grid gap-2 px-5 py-3 md:grid-cols-[28px_1fr_auto]">
              <span className="font-mono text-[11px] text-fg-subtle">{s.index}</span>
              <div className="min-w-0">
                <p className="text-[13px] text-fg">{s.title}</p>
                <p className="truncate font-mono text-[11px] text-fg-subtle">
                  {s.agent_id} · {s.tool_name} · mandate {s.mandate_id} · case {s.case_id}
                </p>
                {d && !d.allowed && (
                  <p className="mt-0.5 font-mono text-[11px] text-deny">{d.reason_codes.join(" · ")}{failed.length ? ` — failed: ${failed.join(", ")}` : ""}</p>
                )}
                {s.result && "child_mandate_id" in s.result && (
                  <p className="mt-0.5 font-mono text-[11px] text-cyan">
                    issued {String(s.result.child_mandate_id)} → {String(s.result.receiving_agent_id)} ({String(s.result.allowed_operations)})
                  </p>
                )}
                {s.note && <p className="mt-0.5 text-[11.5px] italic text-fg-subtle">{s.note}</p>}
              </div>
              <span className="flex items-start gap-1.5">
                {d ? <Badge tone={d.allowed ? "trust" : "deny"}>{d.allowed ? "ALLOW" : "DENY"}</Badge> : <Badge tone="warn">CONTROL</Badge>}
                {d && <span className="font-mono text-[11px] text-fg-subtle">{d.decision_latency_ms.toFixed(1)} ms</span>}
              </span>
            </li>
          );
        })}
      </ol>
    </Card>
  );
}

export default function DelegationNetwork() {
  const caps = useApi<SystemCapabilities>("/api/system/capabilities", { live: true });
  const scenarios = useApi<WorkflowScenarioInfo[]>("/api/workflow/scenarios");
  const cases = useApi<CaseSummary[]>("/api/workflow/cases", { live: true });
  const [caseId, setCaseId] = useState<string | null>(new URLSearchParams(window.location.search).get("case"));
  const [mode, setMode] = useState<"case" | "graph">("case");
  const [run, setRun] = useState<WorkflowRun | null>(null);
  const [running, setRunning] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const enabled = caps.status === "success" && caps.data.developer_demo_enabled;

  async function start(key: string) {
    setRunning(key);
    setError(null);
    try {
      const r = await apiPost<WorkflowRun>(`/api/workflow/scenarios/${key}/run`, { citizen_ref: "C-1001" });
      setRun(r);
      setCaseId(r.case.case_id);
      invalidate("/api/audit", "/api/mandates", "/api/workflow");
      cases.reload();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setRunning(null);
    }
  }

  const runCases = run ? [run.case, ...run.related_cases] : [];
  const delegated = cases.status === "success" ? cases.data.filter((c) => c.authority_model === "delegated") : [];

  return (
    <>
      <PageHeader eyebrow="Phase 3 · Mandate chains" title="Delegation Network" titleAr="شبكة التفويض"
        description="Verifiable agent-to-agent delegation that never expands the authority granted for the original case. Every child mandate is issued by WAKALA after a gateway-authorized commission, signed, and re-verified link by link on every use."
        actions={<SyntheticBadge />} />
      <Notice tone="trust" icon={GitBranch} title="Live delegation records">
        The graph is generated from stored mandates, trusted delegation records and audit events. Agents are deterministic
        simulations; keys are local development keys; enforcement runs in a single process.
      </Notice>

      <div className="grid gap-6 xl:grid-cols-[300px_1fr]">
        <div className="flex flex-col gap-6">
          <Card>
            <CardHeader icon={Play} title="Delegation scenarios" subtitle="Real signed requests through the gateway" />
            {caps.status === "success" && !enabled ? (
              <p className="px-5 py-4 text-[13px] text-fg-muted">Disabled. Start the backend with <span className="font-mono">python run_dev.py</span>.</p>
            ) : (
              <ApiView state={scenarios} reload={scenarios.reload}>
                {(list) => (
                  <div className="space-y-2 p-3">
                    {list.filter((s) => DELEGATION_SCENARIOS.includes(s.key)).map((s) => (
                      <button key={s.key} onClick={() => start(s.key)} disabled={running !== null}
                        className={clsx("w-full rounded-xl border px-3.5 py-3 text-left transition-colors disabled:cursor-wait",
                          run?.scenario === s.key ? "border-trust/50 bg-ink-750" : "border-line bg-ink-800 hover:border-line-strong")}>
                        <span className="flex items-center gap-2 text-[13.5px] font-medium text-fg">
                          {running === s.key ? <Loader2 className="size-4 animate-spin" aria-hidden /> : <Play className="size-4 text-trust" aria-hidden />}
                          {s.title}
                        </span>
                        <span className="mt-1 block text-[12px] leading-snug text-fg-subtle">{s.description}</span>
                      </button>
                    ))}
                  </div>
                )}
              </ApiView>
            )}
          </Card>
          <Card>
            <CardHeader icon={Landmark} title="Delegated cases" subtitle="authority model: delegated" />
            <ApiView state={cases} reload={cases.reload}>
              {() => delegated.length === 0 ? <p className="px-5 py-4 text-[13px] text-fg-subtle">None yet — run a scenario.</p> : (
                <ul className="max-h-[360px] overflow-y-auto p-2">
                  {delegated.map((c) => (
                    <li key={c.case_id}>
                      <button onClick={() => setCaseId(c.case_id)}
                        className={clsx("flex w-full items-center justify-between rounded-lg px-3 py-2 text-left hover:bg-ink-800", caseId === c.case_id && "bg-ink-750")}>
                        <span>
                          <span className="block font-mono text-[12.5px] text-fg">{c.case_id}</span>
                          <span className="font-mono text-[11px] text-fg-subtle">{c.citizen_ref} · {humanize(c.state.toLowerCase())}</span>
                        </span>
                        {c.authority_revoked ? <Badge tone="warn">revoked</Badge> : <Badge tone="trust">active</Badge>}
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
          {runCases.length > 1 && (
            <div className="flex flex-wrap gap-2" role="tablist">
              {runCases.map((c, i) => (
                <button key={c.case_id} role="tab" aria-selected={caseId === c.case_id} onClick={() => setCaseId(c.case_id)}
                  className={clsx("rounded-lg border px-3 py-1.5 font-mono text-[12px]", caseId === c.case_id ? "border-trust/50 bg-ink-750 text-fg" : "border-line text-fg-subtle hover:text-fg-muted")}>
                  Case {i + 1} · {c.case_id}{c.authority_revoked ? " · revoked" : ""}
                </button>
              ))}
            </div>
          )}
          {caseId && (
            <div className="flex gap-2" role="tablist">
              {(["case", "graph"] as const).map((m) => (
                <button key={m} role="tab" aria-selected={mode === m} onClick={() => setMode(m)}
                  className={clsx("rounded-lg border px-3 py-1.5 text-[12.5px]", mode === m ? "border-trust/50 bg-ink-750 text-fg" : "border-line text-fg-subtle")}>
                  {m === "case" ? "Case View (presentation)" : "Full authority graph"}
                </button>
              ))}
            </div>
          )}
          {caseId ? (mode === "case" ? <CaseView caseId={caseId} /> : <GraphPanel caseId={caseId} />) : (
            <Card><EmptyState icon={GitBranch} title="Run a delegation scenario or pick a delegated case">
              The graph shows the case, the issuers that signed its mandates, the Residency Agent's root mandate, every child
              mandate WAKALA issued from it, and any denied attempt to expand authority.
            </EmptyState></Card>
          )}
          {run && <RunSteps run={run} />}
        </div>
      </div>
    </>
  );
}
