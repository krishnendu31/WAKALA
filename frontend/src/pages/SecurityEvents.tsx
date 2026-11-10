import clsx from "clsx";
import { Activity, Link2, PlugZap, RefreshCw, ShieldAlert, ShieldCheck } from "lucide-react";
import { Fragment, useState } from "react";
import { ApiView, Badge, Card, CardHeader, EmptyState, PageHeader, SyntheticBadge } from "@/components/ui";
import { useApi } from "@/hooks/useApi";
import type { AuditEvent, AuditEventList, AuditIntegrity } from "@/types/api";

const COLUMNS = ["#", "Time (UTC)", "Actor", "Tool", "Decision", "Reason codes", "Mandate", "Latency"];

function Integrity() {
  const state = useApi<AuditIntegrity>("/api/audit/integrity", { live: true });
  if (state.status !== "success") return null;
  const d = state.data;
  return (
    <div className={clsx("mb-6 flex flex-wrap items-start gap-3 rounded-xl border px-4 py-3", d.valid ? "border-trust/25 bg-trust-soft" : "border-deny/30 bg-deny-soft")}>
      {d.valid ? <ShieldCheck className="mt-0.5 size-4 text-trust" aria-hidden /> : <ShieldAlert className="mt-0.5 size-4 text-deny" aria-hidden />}
      <div className="min-w-0 flex-1 text-[13px]">
        <p className={clsx("font-semibold", d.valid ? "text-trust" : "text-deny")}>
          Audit hash chain {d.valid ? "verified" : `broken at event #${d.first_broken_sequence}`} · {d.event_count} events
        </p>
        <p className="mt-0.5 break-all font-mono text-[11.5px] text-fg-muted">head {d.head_hash}</p>
        <p className="mt-1 text-[12px] text-fg-subtle">{d.scope_note}</p>
      </div>
    </div>
  );
}

function EventRow({ e }: { e: AuditEvent }) {
  const [open, setOpen] = useState(false);
  const tone = e.decision === "allowed" ? "trust" : e.decision === "denied" ? "deny" : "warn";
  return (
    <Fragment>
      <tr className="cursor-pointer border-b border-line/60 hover:bg-ink-800/60" onClick={() => setOpen((v) => !v)} aria-expanded={open}>
        <td className="px-4 py-3 font-mono text-[12px] text-fg-subtle">{e.sequence}</td>
        <td className="whitespace-nowrap px-4 py-3 font-mono text-[12px]">{e.timestamp.slice(0, 19).replace("T", " ")}</td>
        <td className="px-4 py-3">
          <span className={clsx("font-mono text-[12px]", e.authenticated ? "text-fg" : "text-warn")}>{e.actor}</span>
          {!e.authenticated && e.claimed_agent_id && <span className="block text-[11px] text-fg-subtle">claimed {e.claimed_agent_id}</span>}
        </td>
        <td className="px-4 py-3 font-mono text-[12px]">{e.action}</td>
        <td className="px-4 py-3"><Badge tone={tone} dot>{e.decision.toUpperCase()}</Badge></td>
        <td className="px-4 py-3 font-mono text-[11.5px] text-fg-muted">{e.reason_codes.join(" · ")}</td>
        <td className="px-4 py-3 font-mono text-[11.5px] text-fg-muted">{e.related_mandate ?? "—"}{e.mandate_version ? ` v${e.mandate_version}` : ""}</td>
        <td className="px-4 py-3 text-right font-mono text-[12px] tabular-nums text-fg-muted">{e.decision_latency_ms?.toFixed(2)} ms</td>
      </tr>
      {open && (
        <tr className="border-b border-line/60 bg-ink-900/60">
          <td colSpan={COLUMNS.length} className="px-4 py-3">
            <dl className="grid gap-x-6 gap-y-1.5 font-mono text-[11.5px] sm:grid-cols-[160px_1fr]">
              {[
                ["event_id", e.event_id], ["decision_id", e.decision_id], ["request_id", e.request_id], ["policy_version", e.policy_version],
                ...Object.entries(e.evidence_metadata).map(([k, v]) => [k, String(v)]),
                ["previous_event_hash", e.previous_event_hash], ["event_hash", e.event_hash],
              ].map(([k, v]) => (
                <div key={k as string} className="contents">
                  <dt className="text-fg-subtle">{k}</dt>
                  <dd className="break-all text-fg-muted">{v ?? "—"}</dd>
                </div>
              ))}
            </dl>
          </td>
        </tr>
      )}
    </Fragment>
  );
}

export function SecurityEvents() {
  const events = useApi<AuditEventList>("/api/audit/events?limit=200", { live: true });
  const [, force] = useState(0);
  return (
    <>
      <PageHeader
        eyebrow="Audit"
        title="Security Events"
        titleAr="الأحداث الأمنية"
        description="Every authorization decision — allowed or denied — recorded by the gateway as a hash-chained audit event. Nothing on this page is simulated."
        actions={<SyntheticBadge />}
      />
      <Integrity key={events.status === "success" ? events.data.count : -1} />
      <Card>
        <CardHeader
          icon={Activity}
          title="Authorization event stream"
          subtitle={<span className="font-mono">GET /api/audit/events · newest first · click a row for evidence</span>}
          right={
            <div className="flex items-center gap-2">
              {events.status === "success" && (
                <>
                  <Badge tone="trust">{events.data.allowed_count} allowed</Badge>
                  <Badge tone={events.data.denied_count ? "deny" : "neutral"}>{events.data.denied_count} denied</Badge>
                </>
              )}
              <button
                onClick={() => { events.reload(); force((n) => n + 1); }}
                className="inline-flex items-center gap-1.5 rounded-lg border border-line px-2.5 py-1.5 text-[12px] text-fg-muted hover:bg-ink-750 hover:text-fg"
              >
                <RefreshCw className="size-3.5" aria-hidden /> Refresh
              </button>
            </div>
          }
        />
        <ApiView state={events} reload={events.reload}>
          {(data) =>
            data.count === 0 ? (
              <EmptyState icon={PlugZap} title="No authorization events yet.">
                The gateway is connected and the audit store holds <b className="text-fg">0</b> events. Run a developer
                scenario in the Simulation Lab, or send a signed request to <span className="font-mono">POST /api/gateway/execute</span>.
              </EmptyState>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full min-w-[980px] text-left text-[13px]">
                  <thead>
                    <tr className="border-b border-line text-[11.5px] uppercase tracking-wider text-fg-subtle">
                      {COLUMNS.map((c) => <th key={c} className={clsx("px-4 py-3 font-medium", c === "Latency" && "text-right")}>{c}</th>)}
                    </tr>
                  </thead>
                  <tbody>{data.items.map((e) => <EventRow key={e.event_id} e={e} />)}</tbody>
                </table>
                <p className="flex items-center gap-1.5 border-t border-line px-5 py-3 text-[12px] text-fg-subtle">
                  <Link2 className="size-3.5" aria-hidden /> Each event commits to its predecessor's hash. Logged evidence is
                  limited to digests and identifiers — no keys, signatures, parameter values or personal records.
                </p>
              </div>
            )
          }
        </ApiView>
      </Card>
    </>
  );
}
