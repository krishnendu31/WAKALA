import "@xyflow/react/dist/style.css";
import clsx from "clsx";
import { Bot, Database, GitBranch, ShieldCheck, User } from "lucide-react";
import { useMemo, useState } from "react";
import { Background, Handle, MarkerType, Position, ReactFlow, type Edge, type Node, type NodeProps } from "@xyflow/react";
import { Badge, Card, CardHeader, Notice, PageHeader, SyntheticBadge } from "@/components/ui";

type Kind = "citizen" | "agent" | "gateway" | "service";
type FlowData = { title: string; subtitle: string; kind: Kind; detail: string };
type FlowNode = Node<FlowData, "wakala">;

const KIND_STYLE: Record<Kind, { icon: typeof Bot; ring: string; iconColor: string }> = {
  citizen: { icon: User, ring: "border-line-strong", iconColor: "text-fg-muted" },
  agent: { icon: Bot, ring: "border-line-strong", iconColor: "text-cyan" },
  gateway: { icon: ShieldCheck, ring: "border-trust/50 shadow-[0_0_0_4px_#2dd4bf14]", iconColor: "text-trust" },
  service: { icon: Database, ring: "border-line-strong", iconColor: "text-fg-muted" },
};

function WakalaNode({ data, selected }: NodeProps<FlowNode>) {
  const s = KIND_STYLE[data.kind];
  const Icon = s.icon;
  return (
    <div
      className={clsx(
        "w-[200px] rounded-xl border bg-ink-800 px-3.5 py-3 transition-colors",
        s.ring,
        selected && "!border-trust",
        data.kind === "gateway" && "w-[210px] bg-ink-750 py-5",
      )}
    >
      <Handle type="target" position={Position.Left} className="!size-2 !border-0 !bg-line-strong" />
      <div className="flex items-center gap-2.5">
        <Icon className={clsx("size-4 shrink-0", s.iconColor)} aria-hidden />
        <p className="truncate text-[13px] font-semibold text-fg">{data.title}</p>
      </div>
      <p className="mt-1 truncate font-mono text-[10.5px] text-fg-subtle">{data.subtitle}</p>
      <Handle type="source" position={Position.Right} className="!size-2 !border-0 !bg-line-strong" />
    </div>
  );
}

const nodeTypes = { wakala: WakalaNode };

const NODE_SPECS: Pick<FlowNode, "id" | "position" | "data">[] = [
  { id: "citizen", position: { x: 0, y: 165 }, data: { kind: "citizen", title: "Renewal request", subtitle: "C-1001 · synthetic", detail: "A synthetic citizen (Mariam Al Hashimi, C-1001) requests residency renewal. The request defines the scope every mandate in this workflow will be bound to." } },
  { id: "res", position: { x: 270, y: 165 }, data: { kind: "agent", title: "Residency Agent", subtitle: "AGT-RES-001", detail: "Holds the root mandate for this one request: read residency status, prepare the renewal, and delegate an insurance check and a fee payment of at most AED 500 to the official destination." } },
  { id: "ins", position: { x: 560, y: 40 }, data: { kind: "agent", title: "Insurance Agent", subtitle: "AGT-INS-001", detail: "Receives a child mandate limited to insurance.verify_eligibility for C-1001 only. It cannot read unrelated records or request payments." } },
  { id: "pay", position: { x: 560, y: 290 }, data: { kind: "agent", title: "Payment Agent", subtitle: "AGT-PAY-001", detail: "Receives a child mandate limited to payment.request_fee_payment, amount ≤ AED 500, recipient SYNTH-GOV-TREASURY-0001. It cannot change destinations." } },
  { id: "gw", position: { x: 860, y: 155 }, data: { kind: "gateway", title: "WAKALA Gateway", subtitle: "policy checkpoint · live", detail: "The single path to protected tools (implemented in Phase 1). Verifies the agent's request signature, the issuer-signed mandate, validity, tool, scope, limits, freshness and replay — default-deny — and audits every decision. Delegated requests are refused until Phase 2." } },
  { id: "svc-res", position: { x: 1150, y: 20 }, data: { kind: "service", title: "Residency registry", subtitle: "simulated service", detail: "Synthetic residency records. Will accept only gateway-authorized calls." } },
  { id: "svc-ins", position: { x: 1150, y: 165 }, data: { kind: "service", title: "Insurance registry", subtitle: "simulated service", detail: "Synthetic insurance status records. Read-only." } },
  { id: "svc-pay", position: { x: 1150, y: 310 }, data: { kind: "service", title: "Payment service", subtitle: "simulated · no real funds", detail: "Fictional payment endpoint. Not connected to any bank. Only SYNTH-GOV-TREASURY-0001 is a valid destination." } },
];
const NODES: FlowNode[] = NODE_SPECS.map((n) => ({ ...n, type: "wakala", draggable: false, connectable: false }));

const edgeBase = { markerEnd: { type: MarkerType.ArrowClosed, color: "#3b5280", width: 16, height: 16 }, style: { stroke: "#3b5280", strokeWidth: 1.4 } };
const labelStyle = { labelStyle: { fill: "#9aa9c3", fontSize: 11 }, labelBgStyle: { fill: "#0a1222" }, labelBgPadding: [6, 3] as [number, number], labelBgBorderRadius: 4 };
const delegateStyle = { stroke: "#38bdf8", strokeWidth: 1.4, strokeDasharray: "5 4" };

const EDGES: Edge[] = [
  { id: "e1", source: "citizen", target: "res", label: "request", ...edgeBase, ...labelStyle },
  { id: "e2", source: "res", target: "ins", label: "delegates · narrowed", ...edgeBase, ...labelStyle, style: delegateStyle, markerEnd: { type: MarkerType.ArrowClosed, color: "#38bdf8" } },
  { id: "e3", source: "res", target: "pay", label: "delegates · ≤ AED 500", ...edgeBase, ...labelStyle, style: delegateStyle, markerEnd: { type: MarkerType.ArrowClosed, color: "#38bdf8" } },
  { id: "e4", source: "res", target: "gw", ...edgeBase },
  { id: "e5", source: "ins", target: "gw", ...edgeBase },
  { id: "e6", source: "pay", target: "gw", ...edgeBase },
  { id: "e7", source: "gw", target: "svc-res", ...edgeBase, style: { stroke: "#2dd4bf", strokeWidth: 1.4 }, markerEnd: { type: MarkerType.ArrowClosed, color: "#2dd4bf" } },
  { id: "e8", source: "gw", target: "svc-ins", ...edgeBase, style: { stroke: "#2dd4bf", strokeWidth: 1.4 }, markerEnd: { type: MarkerType.ArrowClosed, color: "#2dd4bf" } },
  { id: "e9", source: "gw", target: "svc-pay", ...edgeBase, style: { stroke: "#2dd4bf", strokeWidth: 1.4 }, markerEnd: { type: MarkerType.ArrowClosed, color: "#2dd4bf" } },
];

const NARROWING_RULES = [
  ["Tools", "child ⊆ parent"],
  ["Denied tools", "child ⊇ parent"],
  ["Citizen & request", "identical"],
  ["Amount limit", "child ≤ parent"],
  ["Recipients", "child ⊆ parent"],
  ["Expiry", "child ≤ parent"],
];

export default function DelegationNetwork() {
  const [selected, setSelected] = useState<string>("gw");
  const node = useMemo(() => NODES.find((n) => n.id === selected) ?? NODES[4]!, [selected]);

  return (
    <>
      <PageHeader
        eyebrow="Delegation"
        title="Delegation Network"
        titleAr="شبكة التفويض"
        description="How authority is planned to flow through the residency renewal workflow. Delegation can only narrow authority — an agent can never hand on more than it holds."
        actions={<SyntheticBadge />}
      />
      <Notice title="Illustrative graph — delegation is not functioning yet">
        The gateway and the three signed mandates are live (Phase 1), but each agent currently acts only under its own
        mandate. Any request carrying a delegation chain is denied. Verification of non-expanding delegation is
        scheduled for Phase 2.
      </Notice>

      <div className="grid gap-6">
        <Card className="overflow-hidden">
          <CardHeader
            icon={GitBranch}
            title="Residency renewal · planned flow"
            subtitle="Select a node for details"
            right={
              <div className="hidden items-center gap-4 text-[12px] text-fg-subtle md:flex">
                <span className="flex items-center gap-1.5"><span className="h-0 w-5 border-t border-dashed border-cyan" /> delegation</span>
                <span className="flex items-center gap-1.5"><span className="h-0 w-5 border-t border-trust" /> authorized call</span>
              </div>
            }
          />
          <div className="h-[440px] bg-ink-900/40">
            <ReactFlow
              nodes={NODES.map((n) => ({ ...n, selected: n.id === selected }))}
              edges={EDGES}
              nodeTypes={nodeTypes}
              onNodeClick={(_, n) => setSelected(n.id)}
              fitView
              fitViewOptions={{ padding: 0.08 }}
              nodesDraggable={false}
              nodesConnectable={false}
              panOnScroll={false}
              zoomOnScroll={false}
              minZoom={0.4}
              maxZoom={1.6}
              proOptions={{ hideAttribution: true }}
            >
              <Background color="#1b2a46" gap={22} size={1} />
            </ReactFlow>
          </div>
        </Card>

        <div className="grid gap-6 lg:grid-cols-2">
          <Card>
            <CardHeader title={node.data.title} subtitle={<span className="font-mono">{node.data.subtitle}</span>} right={<Badge tone="plan">Planned</Badge>} />
            <p className="p-5 text-[13.5px] leading-relaxed text-fg-muted">{node.data.detail}</p>
          </Card>
          <Card>
            <CardHeader title="Non-expanding delegation" subtitle="Rules a child mandate must satisfy" right={<Badge tone="plan">Phase 2</Badge>} />
            <dl className="divide-y divide-line">
              {NARROWING_RULES.map(([k, v]) => (
                <div key={k} className="flex items-center justify-between px-5 py-2.5 text-[13px]">
                  <dt className="text-fg-muted">{k}</dt>
                  <dd className="font-mono text-[12px] text-fg">{v}</dd>
                </div>
              ))}
            </dl>
            <p className="border-t border-line px-5 py-3 text-[12px] leading-relaxed text-fg-subtle">
              Violations will be denied with <span className="font-mono text-deny/80">DENY_DELEGATION_EXPANDS_AUTHORITY</span>.
            </p>
          </Card>
        </div>
      </div>
    </>
  );
}
