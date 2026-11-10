/* eslint-disable @typescript-eslint/no-explicit-any */
import clsx from "clsx";
import { Eye, Radar } from "lucide-react";
import { useEffect, useState } from "react";
import { Badge, Card, CardHeader } from "@/components/ui";
import { officerRequest } from "@/lib/api";
import type { Tone } from "@/lib/format";

const LEVEL_TONE: Record<string, Tone> = {
  NORMAL: "neutral", OBSERVE: "neutral", ALERT: "warn", REQUIRE_APPROVAL: "warn", SUSPEND_SPECIFIC_AUTHORITY: "deny", REVOKE: "deny",
};

/** Behaviour Watch 2.0 findings, read live from /api/officer/watch (officer session required). */
export function BehaviourWatch() {
  const [data, setData] = useState<any | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [open, setOpen] = useState<string | null>(null);
  const [showObs, setShowObs] = useState(true);
  useEffect(() => {
    let live = true;
    const tick = () => officerRequest<any>("/api/officer/watch").then((d) => live && setData(d)).catch((e) => live && setErr(String(e)));
    tick();
    const id = setInterval(tick, 4000);
    return () => { live = false; clearInterval(id); };
  }, []);
  const findings = (data?.findings ?? []).filter((f: any) => showObs || f.kind !== "observation");
  return (
    <Card>
      <CardHeader icon={Radar} title="Behaviour Watch" subtitle={data ? `Policy ${data.policy} · operating hours ${data.operating_hours ?? "24/7"}` : "Loading…"}
        right={<label className="flex items-center gap-1.5 text-[12px] text-fg-muted"><input type="checkbox" checked={showObs} onChange={(e) => setShowObs(e.target.checked)} /> show observations</label>} />
      {err && <p className="px-5 py-2 text-[12px] text-deny">{err}</p>}
      <div className="flex flex-wrap items-center gap-1.5 border-b border-line px-5 py-2.5 text-[11px] text-fg-subtle">
        {(data?.levels ?? []).map((l: string, i: number) => <span key={l} className="flex items-center gap-1.5">{i > 0 && "→"}<Badge tone={LEVEL_TONE[l] ?? "neutral"}>{l.replace(/_/g, " ")}</Badge></span>)}
      </div>
      {data && <p className="px-5 pt-3 text-[11.5px] text-fg-subtle">{data.note}</p>}
      <ul className="divide-y divide-line">
        {findings.length === 0 && <li className="px-5 py-6 text-[13px] text-fg-subtle">No signals yet.</li>}
        {findings.map((f: any) => (
          <li key={f.id} className="px-5 py-3">
            <button onClick={() => setOpen(open === f.id ? null : f.id)} className="w-full text-left">
              <div className="flex flex-wrap items-center gap-2">
                {f.kind === "observation" ? <Eye className="size-4 text-fg-subtle" /> : <Radar className="size-4 text-warn" />}
                <Badge tone={LEVEL_TONE[f.level] ?? "neutral"}>{String(f.level).replace(/_/g, " ")}</Badge>
                <span className="font-mono text-[12px] text-fg">{f.signal}</span>
                <span className="text-[12px] text-fg-muted">{f.agent_id} · {f.case_id ?? "agent-level (no case)"}</span>
                <span className="ml-auto text-[11px] text-fg-subtle">{f.status} · {new Date(f.last_seen).toLocaleTimeString()}</span>
              </div>
              <p className="mt-1 text-[13px] text-fg">{f.concern}</p>
            </button>
            {open === f.id && (
              <dl className={clsx("mt-2 grid gap-x-4 gap-y-1 rounded-lg border border-line bg-ink-900/60 p-3 text-[12px] sm:grid-cols-[150px_1fr]")}>
                <dt className="text-fg-subtle">Observed</dt><dd className="text-fg">{f.observed}</dd>
                <dt className="text-fg-subtle">Expected / threshold</dt><dd className="text-fg">{f.expected}</dd>
                <dt className="text-fg-subtle">Severity</dt><dd className="text-fg">{f.severity}</dd>
                <dt className="text-fg-subtle">Action taken</dt><dd className="text-fg">{Array.isArray(f.action_taken) ? f.action_taken.join(" · ") : f.action_taken}</dd>
                <dt className="text-fg-subtle">Audit events</dt><dd className="break-all font-mono text-[11px] text-fg-muted">{(f.evidence_event_ids ?? []).join(", ")}</dd>
                <dt className="text-fg-subtle">Policy</dt><dd className="font-mono text-[11px] text-fg-muted">{f.policy}</dd>
              </dl>
            )}
          </li>
        ))}
      </ul>
    </Card>
  );
}
