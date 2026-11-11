/* eslint-disable @typescript-eslint/no-explicit-any */
/**
 * Live Authority Map for the judge experience.
 *
 * Every node and edge is derived from two real backend reads for ONE case:
 *   - GET /api/portal/cases/{id}            (gateway decision timeline, delegation records, task assignments,
 *                                            pending approvals, case state)
 *   - GET /api/workflow/cases/{id}/case-view (per-mandate lanes: verified signed mandate status, actions + targets)
 * Conceptual roles (the citizen's case, the gateway, the protected services) are fixed and labelled as such.
 * A delegation edge is drawn as authorized ONLY when a stored delegation record exists. A denied request is drawn
 * as a red path that ends AT the gateway: it never reaches a service, and it never creates a delegation.
 */
import clsx from "clsx";
import { Bot, Building2, CreditCard, HeartPulse, Landmark, ShieldCheck, UserRound, type LucideIcon } from "lucide-react";
import type { ReactNode } from "react";

type Any = Record<string, any>;
export type Tone = "ok" | "deny" | "hold" | "idle" | "off" | "info";

export const AGENT = { res: "AGT-RES-001", ins: "AGT-INS-001", sb: "AGT-INS-002", pay: "AGT-PAY-001" } as const;

const STROKE: Record<Tone, string> = { ok: "#0e4d48", deny: "#b42318", hold: "#c06a0a", idle: "#cdd5d4", off: "#9aa6ad", info: "#193e60" };

export interface MapNode {
  id: string; x: number; y: number; w: number; h: number; icon: LucideIcon; title: string; role: string;
  status: { tone: Tone; text: string }; kind: "case" | "agent" | "gateway" | "service"; conceptual?: boolean;
  tech: [string, string][];
}
export interface MapEdge { id: string; d: string; tone: Tone; label?: string; lx?: number; ly?: number; blocked?: [number, number] }
export interface MapModel { nodes: MapNode[]; edges: MapEdge[]; counts: { allowed: number; denied: number; held: number }; delegationMid?: number }

const W = 1000;
const H = 420;

function latestBy(timeline: Any[], agent: string): Any | null {
  const rows = timeline.filter((t) => t.agent_id === agent);
  return rows.length ? rows[rows.length - 1]! : null;
}

function laneFor(cv: Any | null, agent: string): Any | null {
  const lanes = (cv?.lanes ?? []).filter((l: Any) => l.agent_id === agent);
  return lanes.length ? lanes[lanes.length - 1] : null;
}

function laneStatus(lane: Any | null, fallback: { tone: Tone; text: string }): { tone: Tone; text: string } {
  if (!lane) return fallback;
  switch (lane.state) {
    case "authorized": return { tone: "ok", text: "Verified · authorized" };
    case "recovered": return { tone: "ok", text: "Recovered the service" };
    case "suspended": return { tone: "hold", text: "Suspended for review" };
    case "pending_approval": return { tone: "hold", text: "Awaiting officer" };
    case "revoked": return { tone: "off", text: "Authority revoked" };
    default: return { tone: "deny", text: "Not usable" };
  }
}

function laneTech(lane: Any | null, agentId: string, last: Any | null): [string, string][] {
  const t = lane?.technical ?? {};
  const rows: [string, string][] = [["agent", agentId]];
  if (lane) {
    rows.push(["signed mandate", lane.mandate_id], ["issuer", t.issuer ?? "—"], ["signature", t.signature ?? "—"],
      ["verified now", t.verification_valid ? `yes · chain of ${t.chain_length}` : `no ${(t.verification_codes ?? []).join(", ")}`]);
    if (t.parent_mandate_id) rows.push(["delegated from", t.parent_mandate_id]);
    if (lane.task) rows.push(["delegated task", lane.task]);
    if (t.expires_at) rows.push(["expires", new Date(t.expires_at).toLocaleTimeString("en-GB")]);
  } else rows.push(["signed mandate", "none for this case"]);
  if (last) rows.push(["last gateway decision", `${last.decision} · ${last.tool_name}`], ["reason codes", last.reason_codes.join(", ") || "—"], ["audit event", last.event_id]);
  return rows;
}

/** Builds the map for one case. `portal` and `cv` may be null (nothing started yet): everything is then neutral. */
export function buildAuthorityMap(portal: Any | null, cv: Any | null, opts: { showStandby: boolean }): MapModel {
  const timeline: Any[] = portal?.timeline ?? [];
  const delegations: Any[] = portal?.delegations ?? [];
  const pending: Any[] = portal?.pending_approvals ?? [];
  const assignments: Record<string, string> = portal?.task_assignments ?? {};
  const first = (portal?.citizen_name ?? "Mariam").split(" ")[0];
  const standby = opts.showStandby || delegations.some((d) => d.to_agent === AGENT.sb) || timeline.some((t) => t.agent_id === AGENT.sb)
    || Object.values(assignments).includes(AGENT.sb);

  const rows = standby ? { res: 60, ins: 165, sb: 270, pay: 365 } : { res: 70, ins: 210, sb: 0, pay: 350 };
  const AH = 74, AW = 200;
  const nodes: MapNode[] = [];
  const edges: MapEdge[] = [];

  // --- the citizen's case (conceptual role, bound to a real case record when one exists)
  const st = portal?.state as string | undefined;
  const caseStatus: { tone: Tone; text: string } = !portal ? { tone: "idle", text: "No request yet" }
    : st === "COMPLETED" ? { tone: "ok", text: portal.recovery_status === "recovered" ? "Recovered · completed" : "Completed" }
    : st === "PAUSED_FOR_REVIEW" ? { tone: "hold", text: "Paused for review" }
    : st === "FAILED" ? { tone: "deny", text: "Could not complete" }
    : st === "AWAITING_PAYMENT" ? { tone: "info", text: "Awaiting fee" } : { tone: "info", text: "In progress" };
  nodes.push({ id: "case", kind: "case", x: 14, y: 150, w: 176, h: 120, icon: UserRound, title: first, role: "Residency renewal",
    status: caseStatus, conceptual: !portal,
    tech: portal ? [["case", portal.case_id], ["citizen", portal.citizen_ref], ["state", portal.state], ["recovery", portal.recovery_status]] : [["case", "not started"]] });

  // --- agents
  const agentDefs: { key: keyof typeof AGENT; title: string; role: string; icon: LucideIcon; x: number }[] = [
    { key: "res", title: "Residency Agent", role: "Coordinates the case", icon: Bot, x: 230 },
    { key: "ins", title: "Insurance Agent", role: "Delegated insurance check", icon: Bot, x: 284 },
    ...(standby ? [{ key: "sb" as const, title: "Standby Agent", role: "Replacement on standby", icon: Bot, x: 284 }] : []),
    { key: "pay", title: "Payment Agent", role: "Collects the AED 500 fee", icon: Bot, x: 230 },
  ];
  for (const a of agentDefs) {
    const id = AGENT[a.key];
    const lane = laneFor(cv, id);
    const last = latestBy(timeline, id);
    let fallback: { tone: Tone; text: string } = { tone: "idle", text: portal ? "Not active" : "Waiting" };
    if (a.key === "ins" && portal) fallback = { tone: "idle", text: "Not yet delegated" };
    if (a.key === "sb") fallback = Object.values(assignments).includes(id) ? { tone: "info", text: "Assigned by officer" } : { tone: "idle", text: "Standby · not used" };
    let status = laneStatus(lane, fallback);
    if (a.key === "ins" && last?.decision === "denied" && lane?.state === "authorized") status = { tone: "deny", text: "Request denied" };
    nodes.push({ id, kind: "agent", x: a.x, y: rows[a.key] - AH / 2, w: AW, h: AH, icon: a.icon, title: a.title, role: a.role, status,
      tech: laneTech(lane, id, last) });
  }

  // --- gateway (conceptual role: the independent authorization gateway every protected action passes through)
  const allowed = timeline.filter((t) => t.decision === "allowed").length;
  const denied = timeline.filter((t) => t.decision === "denied").length;
  const held = timeline.filter((t) => t.decision === "escalated").length;
  nodes.push({ id: "gateway", kind: "gateway", x: 572, y: 14, w: 92, h: H - 28, icon: ShieldCheck, title: "WAKALA", role: "Gateway",
    status: { tone: denied ? "deny" : allowed ? "ok" : "idle", text: "" },
    tech: [["decisions on this case", `${allowed} allowed · ${denied} denied · ${held} held for an officer`], ["source", "hash-chained audit trail"]] });

  // --- protected services (conceptual roles: fictional government services)
  const svc: { key: string; title: string; icon: LucideIcon; cy: number }[] = [
    { key: "residency", title: "Residency service", icon: Landmark, cy: 80 },
    { key: "insurance", title: "Insurance records", icon: HeartPulse, cy: 210 },
    { key: "payment", title: "Payment service", icon: CreditCard, cy: 340 },
  ];
  for (const s of svc) {
    const reached = timeline.filter((t) => t.decision === "allowed" && String(t.tool_name).startsWith(`${s.key}.`)).length;
    nodes.push({ id: `svc-${s.key}`, kind: "service", x: 794, y: s.cy - 37, w: 192, h: 74, icon: s.icon ?? Building2, title: s.title,
      role: "Fictional protected service", conceptual: true,
      status: reached ? { tone: "ok", text: `${reached} authorized ${reached === 1 ? "action" : "actions"}` } : { tone: "idle", text: "Not reached" },
      tech: [["reachable only via", "Gateway.execute()"], ["authorized actions on this case", String(reached)]] });
    edges.push({ id: `g-${s.key}`, d: `M664 ${s.cy} L794 ${s.cy}`, tone: reached ? "ok" : "idle" });
  }

  // --- case mandates: the Residency and Payment agents each hold a signed mandate bound to this case (mandate_refs)
  const refs: Record<string, string> = portal?.mandate_refs ?? {};
  const caseEdge = (agent: string, y: number, sy: number) => {
    const lane = laneFor(cv, agent);
    const tone: Tone = !refs[agent] ? "idle" : lane?.technical?.verification_valid ? "ok" : lane ? "hold" : "info";
    return { id: `m-${agent}`, d: `M190 ${sy} C212 ${sy} 212 ${y} 230 ${y}`, tone };
  };
  edges.push(caseEdge(AGENT.res, rows.res, 196));
  edges.push(caseEdge(AGENT.pay, rows.pay, 224));

  // --- delegation: only from stored delegation records (or a real pending approval for one)
  const delegEdge = (to: string, y: number): MapEdge => {
    const rec = [...delegations].reverse().find((d) => d.to_agent === to);
    const lane = laneFor(cv, to);
    const d = `M256 ${rows.res + AH / 2} L256 ${y - 10} Q256 ${y} 266 ${y} L284 ${y}`;
    if (rec) {
      const tone: Tone = lane?.state === "suspended" ? "hold" : lane?.state === "revoked" ? "off" : "ok";
      return { id: `d-${to}`, d, tone };
    }
    const waiting = pending.some((p) => p.agent_id === AGENT.res && p.tool_name === "delegation.commission_task") && Object.values(assignments).includes(to);
    if (waiting) return { id: `d-${to}`, d, tone: "hold" };
    return { id: `d-${to}`, d, tone: "idle" };
  };
  edges.push(delegEdge(AGENT.ins, rows.ins));
  if (standby) edges.push(delegEdge(AGENT.sb, rows.sb));

  // --- each agent's requests to the gateway, coloured by its latest real gateway decision
  for (const a of agentDefs) {
    const id = AGENT[a.key];
    const y = rows[a.key];
    const x0 = a.x + AW;
    const mine = timeline.filter((t) => t.agent_id === id);
    const last = mine.at(-1);
    if (!last) { edges.push({ id: `r-${id}`, d: `M${x0} ${y} L572 ${y}`, tone: "idle" }); continue; }
    const ok = mine.filter((t) => t.decision === "allowed").length;
    const lx = (x0 + 572) / 2;
    if (last.decision === "denied") {
      edges.push({ id: `r-${id}`, d: `M${x0} ${y} L572 ${y}`, tone: "deny", label: "DENIED", lx, ly: y, blocked: [572, y] });
    } else if (last.decision === "escalated") {
      edges.push({ id: `r-${id}`, d: `M${x0} ${y} L572 ${y}`, tone: "hold", label: "held", lx, ly: y });
    } else {
      edges.push({ id: `r-${id}`, d: `M${x0} ${y} L572 ${y}`, tone: "ok", label: `${ok} allowed`, lx, ly: y });
    }
  }
  return { nodes, edges, counts: { allowed, denied, held }, delegationMid: (rows.res + AH / 2 + rows.ins) / 2 + 4 };
}

// ------------------------------------------------------------------------------------------------ rendering
const CHIP: Record<Tone, string> = {
  ok: "bg-trust-soft text-trust", deny: "bg-deny-soft text-deny", hold: "bg-warn-soft text-warn", idle: "bg-ink-800 text-fg-subtle",
  off: "bg-ink-750 text-fg-muted", info: "bg-navy-soft text-navy",
};
const BORDER: Record<Tone, string> = {
  ok: "border-trust/45", deny: "border-deny/60", hold: "border-warn/55", idle: "border-line", off: "border-line-strong", info: "border-navy/30",
};

function NodeBox({ n, selected, onSelect }: { n: MapNode; selected: boolean; onSelect: (id: string) => void }) {
  if (n.kind === "gateway") {
    return (
      <button onClick={() => onSelect(n.id)} title="WAKALA authorization gateway — click for details"
        className={clsx("flex h-full w-full flex-col items-center justify-center gap-2 rounded-2xl border-2 bg-navy text-white transition-shadow",
          selected ? "border-gold shadow-[0_0_0_4px_#b48a5533]" : "border-navy")}>
        <ShieldCheck className="size-8 text-[#d9b77e]" aria-hidden />
        <span className="text-[15px] font-semibold tracking-[0.12em]">WAKALA</span>
        <span className="text-[12px] text-white/75">Gateway</span>
        <span className="mt-3 text-center text-[11px] leading-snug text-white/70">checks<br />every<br />protected<br />action</span>
      </button>
    );
  }
  return (
    <button onClick={() => onSelect(n.id)}
      className={clsx("flex h-full w-full flex-col justify-center rounded-xl border-2 bg-ink-850 px-3 text-left shadow-[var(--shadow-card)] transition-colors",
        BORDER[n.status.tone], selected && "!border-gold shadow-[0_0_0_4px_#b48a5533]", n.status.tone === "idle" && "opacity-75")}>
      <span className="flex items-center gap-2">
        <n.icon className={clsx("size-[18px] shrink-0", n.kind === "service" ? "text-fg-muted" : n.kind === "case" ? "text-navy" : "text-trust")} aria-hidden />
        <span className={clsx("truncate font-semibold text-fg", n.kind === "case" ? "text-[19px]" : "text-[15.5px]")}>{n.title}</span>
      </span>
      <span className="mt-0.5 truncate text-[12.5px] text-fg-muted">{n.role}</span>
      {n.status.text && <span className={clsx("mt-1.5 inline-flex w-fit max-w-full truncate rounded-full px-2 py-0.5 text-[12px] font-semibold", CHIP[n.status.tone])}>{n.status.text}</span>}
    </button>
  );
}

function EdgeLabel({ e }: { e: MapEdge }) {
  if (!e.label || e.lx === undefined || e.ly === undefined) return null;
  const w = e.label.length * 6.6 + 18;
  const strong = e.tone === "deny";
  return (
    <g>
      <rect x={e.lx - w / 2} y={e.ly - 10} width={w} height={20} rx={10} fill={strong ? STROKE.deny : "#ffffff"} stroke={STROKE[e.tone]} strokeWidth={1.2} />
      <text x={e.lx} y={e.ly + 4} textAnchor="middle" fontSize={11} fontWeight={strong ? 700 : 600} fill={strong ? "#ffffff" : STROKE[e.tone]}
        style={{ fontFamily: "var(--font-sans)", letterSpacing: strong ? "0.08em" : undefined }}>{e.label}</text>
    </g>
  );
}

export function AuthorityMap({ model, selected, onSelect, header }: { model: MapModel; selected: string | null; onSelect: (id: string) => void; header?: ReactNode }) {
  return (
    <div>
      {header}
      {/* desktop / projector: spatial map */}
      <div className="hidden md:block">
        <svg viewBox={`0 0 ${W} ${H}`} className="block h-auto w-full" role="img" aria-label="Live authority map: citizen case, AI agents, WAKALA gateway and protected services">
          <defs>
            {(Object.keys(STROKE) as Tone[]).map((t) => (
              <marker key={t} id={`arrow-${t}`} viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">
                <path d="M0 0 L10 5 L0 10 z" fill={STROKE[t]} />
              </marker>
            ))}
          </defs>
          <text x={102} y={H - 6} textAnchor="middle" fontSize={10.5} fill="#75828b" style={{ letterSpacing: "0.12em" }}>CITIZEN</text>
          <text x={384} y={H - 6} textAnchor="middle" fontSize={10.5} fill="#75828b" style={{ letterSpacing: "0.12em" }}>AI AGENTS</text>
          <text transform={`translate(248 ${model.delegationMid ?? 130}) rotate(-90)`} textAnchor="middle" fontSize={10} fill="#687783" style={{ letterSpacing: "0.1em" }}>DELEGATES</text>
          <text x={890} y={H - 6} textAnchor="middle" fontSize={10.5} fill="#75828b" style={{ letterSpacing: "0.12em" }}>PROTECTED SERVICES</text>
          {model.edges.map((e) => (
            <path key={e.id} d={e.d} fill="none" stroke={STROKE[e.tone]} strokeWidth={e.tone === "idle" ? 1.6 : e.tone === "deny" ? 3.2 : 2.6}
              strokeDasharray={e.tone === "idle" ? "4 5" : e.tone === "hold" ? "7 5" : e.tone === "off" ? "3 4" : undefined}
              markerEnd={e.tone === "idle" ? undefined : `url(#arrow-${e.tone})`}
              className={clsx("transition-[stroke] duration-500", e.tone === "hold" && "wk-march")} />
          ))}
          {model.nodes.map((n) => (
            <foreignObject key={n.id} x={n.x} y={n.y} width={n.w} height={n.h}>
              <NodeBox n={n} selected={selected === n.id} onSelect={onSelect} />
            </foreignObject>
          ))}
          {model.edges.map((e) => <EdgeLabel key={`l-${e.id}`} e={e} />)}
          {model.edges.filter((e) => e.blocked).map((e) => (
            <g key={`b-${e.id}`} transform={`translate(${e.blocked![0] - 4} ${e.blocked![1]})`}>
              <circle r={13} fill="#ffffff" stroke={STROKE.deny} strokeWidth={3} />
              <path d="M-5 -5 L5 5 M5 -5 L-5 5" stroke={STROKE.deny} strokeWidth={3} strokeLinecap="round" />
            </g>
          ))}
        </svg>
      </div>
      {/* phone (QR preview): the same model as a list */}
      <ul className="space-y-2 md:hidden">
        {model.nodes.filter((n) => n.kind !== "gateway").map((n) => {
          const edge = model.edges.find((e) => e.id === `r-${n.id}`);
          return (
            <li key={n.id}>
              <button onClick={() => onSelect(n.id)} className={clsx("flex w-full items-center gap-3 rounded-xl border-2 bg-ink-850 px-3 py-2.5 text-left", BORDER[n.status.tone],
                n.kind === "agent" && (n.id === AGENT.ins || n.id === AGENT.sb) && "ml-5 w-[calc(100%-1.25rem)]")}>
                <n.icon className="size-5 shrink-0 text-navy" aria-hidden />
                <span className="min-w-0 flex-1"><span className="block text-[15px] font-semibold leading-snug text-fg">{n.title}</span>
                  <span className="block text-[12px] leading-snug text-fg-muted">{n.role}</span></span>
                <span className="flex shrink-0 flex-col items-end gap-1">
                  {n.status.text && <span className={clsx("rounded-full px-2 py-0.5 text-[11px] font-semibold", CHIP[n.status.tone])}>{n.status.text}</span>}
                  {edge?.label && <span className={clsx("rounded-full px-2 py-0.5 text-[11px] font-semibold", CHIP[edge.tone])}>Gateway: {edge.label}</span>}
                </span>
              </button>
            </li>
          );
        })}
      </ul>
      <div className="mt-3 flex flex-wrap items-center gap-x-5 gap-y-1.5 text-[12.5px] text-fg-muted">
        <Legend tone="ok" text="Authorized" /><Legend tone="deny" text="Attempt denied" /><Legend tone="hold" text="Pending human review" /><Legend tone="idle" text="Not yet active" />
        <span className="ml-auto text-fg-subtle">Select any box for verification details</span>
      </div>
    </div>
  );
}

function Legend({ tone, text }: { tone: Tone; text: string }) {
  return (
    <span className="inline-flex items-center gap-1.5">
      <svg width="26" height="8" aria-hidden><line x1="1" y1="4" x2="25" y2="4" stroke={STROKE[tone]} strokeWidth={tone === "idle" ? 1.6 : 2.6} strokeDasharray={tone === "idle" ? "4 4" : tone === "hold" ? "6 4" : undefined} /></svg>
      {text}
    </span>
  );
}
