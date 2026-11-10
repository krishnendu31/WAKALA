/* eslint-disable @typescript-eslint/no-explicit-any */
import clsx from "clsx";
import { CheckCircle2, Clock, Printer, ReceiptText, ShieldX, UserCheck, X } from "lucide-react";
import { useEffect, useState } from "react";
import { apiGet } from "@/lib/api";

const t = (iso: string) => new Date(iso).toLocaleString();

/** "My AI Activity" — citizen transparency receipt, read live from /api/portal/cases/{id}/receipt. */
export function AiActivityReceipt({ caseId, onClose }: { caseId: string; onClose: () => void }) {
  const [r, setR] = useState<any | null>(null);
  const [err, setErr] = useState<string | null>(null);
  useEffect(() => { apiGet<any>(`/api/portal/cases/${caseId}/receipt`).then(setR).catch((e) => setErr(String(e))); }, [caseId]);
  return (
    <div className="fixed inset-0 z-50 flex items-start justify-center overflow-y-auto bg-fg/45 p-4" role="dialog" aria-modal="true" aria-label="My AI Activity">
      <div className="my-8 w-full max-w-[760px] rounded-2xl border border-line bg-ink-900 shadow-2xl">
        <div className="flex items-center gap-3 border-b border-line px-6 py-4">
          <ReceiptText className="size-5 text-trust" />
          <div className="flex-1"><p className="text-[17px] font-semibold text-fg">My AI Activity</p>{r && <p className="font-mono text-[11.5px] text-fg-subtle">{r.receipt_id} · {r.case_id}</p>}</div>
          <button onClick={() => window.print()} className="rounded-lg p-1.5 text-fg-muted hover:bg-ink-800" aria-label="Print"><Printer className="size-4" /></button>
          <button onClick={onClose} className="rounded-lg p-1.5 text-fg-muted hover:bg-ink-800" aria-label="Close"><X className="size-4" /></button>
        </div>
        {err && <p className="px-6 py-4 text-[13px] text-deny">{err}</p>}
        {!r && !err && <p className="px-6 py-6 text-[13px] text-fg-subtle">Loading your receipt…</p>}
        {r && (
          <div className="space-y-5 px-6 py-5">
            <p className="rounded-lg border border-warn/40 bg-warn-soft px-3 py-2 text-[11.5px] font-medium uppercase tracking-wider text-warn">{r.label}</p>
            <div className="flex flex-wrap items-baseline gap-x-6 gap-y-1">
              <p className="text-[15px] text-fg">{r.citizen.name} <span className="font-mono text-[12px] text-fg-subtle">{r.citizen.ref}</span></p>
              <p className="text-[13px] text-fg-muted">{r.service}</p>
              <p className={clsx("ml-auto text-[14px] font-semibold", r.final_status === "Completed" ? "text-trust" : "text-warn")}>{r.final_status}{r.recovered_after_review ? " · after review" : ""}</p>
            </div>
            <div className="space-y-1.5 rounded-xl border border-trust/30 bg-trust-soft/40 p-4">{r.summary.map((l: string) => <p key={l} className="text-[14px] text-fg">{l}</p>)}</div>
            <section>
              <p className="mb-2 text-[12px] uppercase tracking-wider text-fg-subtle">What the AI agents did for you</p>
              <ul className="divide-y divide-line rounded-xl border border-line">{r.actions.map((a: any) => (
                <li key={a.reference} className="flex items-start gap-3 px-4 py-2.5">
                  <CheckCircle2 className={clsx("mt-0.5 size-4 shrink-0", a.completed ? "text-trust" : "text-fg-subtle")} />
                  <div className="min-w-0 flex-1"><p className="text-[13.5px] text-fg">{a.purpose}</p><p className="text-[12px] text-fg-muted">{a.agent}{a.delegated ? " · delegated task" : ""} · {a.status}</p></div>
                  <span className="text-right text-[11px] text-fg-subtle">{t(a.at)}<br /><span className="font-mono">{a.reference}</span></span>
                </li>
              ))}</ul>
            </section>
            {r.held.length > 0 && <section><p className="mb-2 text-[12px] uppercase tracking-wider text-fg-subtle">Steps held for a human</p>
              {r.held.map((a: any) => <p key={a.reference} className="flex items-center gap-2 text-[13px] text-fg"><Clock className="size-4 text-warn" />{a.purpose} — {a.status} <span className="font-mono text-[11px] text-fg-subtle">{a.reference}</span></p>)}</section>}
            {r.blocked.length > 0 && <section><p className="mb-2 text-[12px] uppercase tracking-wider text-fg-subtle">Blocked by WAKALA</p>
              {r.blocked.map((a: any) => <p key={a.reference} className="flex items-start gap-2 text-[13px] text-fg"><ShieldX className="mt-0.5 size-4 shrink-0 text-deny" /><span>{a.agent}: {a.why} {a.status}. <span className="font-mono text-[11px] text-fg-subtle">{a.reference}</span></span></p>)}</section>}
            {r.officer_review.length > 0 && <section><p className="mb-2 text-[12px] uppercase tracking-wider text-fg-subtle">Human review</p>
              {r.officer_review.map((a: any) => <p key={a.reference} className="flex items-center gap-2 text-[13px] text-fg"><UserCheck className="size-4 text-trust" />{a.what} <span className="text-[11px] text-fg-subtle">{t(a.at)}</span></p>)}</section>}
            <p className="text-[11.5px] text-fg-subtle">{r.privacy_note} Quote a reference (R-…) to a service officer if you have a question.</p>
          </div>
        )}
      </div>
    </div>
  );
}
