import clsx from "clsx";
import { Eye, ReceiptText, UserRound } from "lucide-react";
import { useState } from "react";
import { ApiView, Badge, Card, CardHeader, KeyValue, Notice, PageHeader, SyntheticBadge } from "@/components/ui";
import { useApi } from "@/hooks/useApi";
import { formatDate, formatMoney, humanize, type Tone } from "@/lib/format";
import type { AgentPassport, Citizen, GovernmentService, ListResponse } from "@/types/api";

const residencyTone: Record<Citizen["residency"]["status"], Tone> = { active: "trust", expiring_soon: "warn", expired: "deny" };
const insuranceTone: Record<Citizen["insurance"]["status"], Tone> = { valid: "trust", expired: "deny", none: "warn" };

function Receipt({ citizen, agents, service }: { citizen: Citizen; agents: AgentPassport[]; service: GovernmentService }) {
  return (
    <div className="relative mx-auto max-w-[620px] overflow-hidden rounded-2xl border border-line-strong bg-[#0c1528] shadow-[0_24px_60px_-30px_#000]">
      <div
        className="pointer-events-none absolute inset-0 grid select-none place-items-center text-[38px] font-bold uppercase tracking-[0.22em] text-warn/[0.06] [transform:rotate(-18deg)]"
        aria-hidden
      >
        Illustrative preview
      </div>
      <div className="relative border-b border-dashed border-line-strong px-7 py-6">
        <div className="flex items-start justify-between gap-4">
          <div>
            <p className="eyebrow text-trust/80">Mandate receipt</p>
            <p className="mt-1 text-[19px] font-semibold text-fg">Who acted on your behalf</p>
            <p lang="ar" dir="rtl" className="mt-0.5 text-[16px] text-fg-muted">من تصرّف نيابةً عنك</p>
          </div>
          <div className="text-right">
            <p className="text-[11px] uppercase tracking-wider text-fg-subtle">Receipt no.</p>
            <p className="font-mono text-[13px] text-fg-subtle">— not issued —</p>
          </div>
        </div>
      </div>

      <div className="relative space-y-6 px-7 py-6">
        <dl className="grid grid-cols-2 gap-4">
          <KeyValue label="Citizen">
            {citizen.full_name}
            <span lang="ar" className="block text-[13px] text-fg-muted">{citizen.full_name_ar}</span>
          </KeyValue>
          <KeyValue label="Reference" mono>{citizen.citizen_ref}</KeyValue>
          <KeyValue label="Service">{service.name}</KeyValue>
          <KeyValue label="Authorized fee">{formatMoney(service.fee)} <span className="text-[12px] text-warn">synthetic</span></KeyValue>
        </dl>

        <div>
          <p className="mb-2.5 text-[11.5px] font-medium uppercase tracking-wider text-fg-subtle">Agents in this workflow</p>
          <ul className="divide-y divide-line rounded-xl border border-line">
            {agents.map((a) => (
              <li key={a.agent_id} className="flex items-center justify-between gap-4 px-4 py-3">
                <div className="min-w-0">
                  <p className="text-[13.5px] font-medium text-fg">{a.name}</p>
                  <p className="truncate text-[12px] text-fg-subtle">
                    {a.owner_entity} · accountable: {a.accountable_officer.name}
                  </p>
                </div>
                <span className="shrink-0 font-mono text-[11.5px] text-fg-subtle">{a.agent_id}</span>
              </li>
            ))}
          </ul>
        </div>

        <div>
          <p className="mb-2.5 text-[11.5px] font-medium uppercase tracking-wider text-fg-subtle">Actions taken &amp; decisions</p>
          <div className="rounded-xl border border-dashed border-line-strong px-4 py-5 text-center text-[13px] text-fg-muted">
            No actions recorded. Each allowed or denied action, its mandate and its reason will be listed here from the
            audit trail once the enforcement engine is connected (Phase 3).
          </div>
        </div>

        <p className="border-t border-dashed border-line-strong pt-4 text-[11.5px] leading-relaxed text-fg-subtle">
          Layout preview using synthetic records. This receipt is not a legal document and does not reflect any real
          transaction.
        </p>
      </div>
    </div>
  );
}

export function CitizenTransparency() {
  const citizens = useApi<ListResponse<Citizen>>("/api/citizens");
  const agents = useApi<ListResponse<AgentPassport>>("/api/agents");
  const services = useApi<ListResponse<GovernmentService>>("/api/services");
  const [ref, setRef] = useState("C-1001");

  return (
    <>
      <PageHeader
        eyebrow="Transparency"
        title="Citizen Transparency"
        titleAr="الشفافية للمتعاملين"
        description="Citizens should be able to see, in plain language, which AI agents acted for them, under which mandate, and what was allowed or refused."
        actions={<SyntheticBadge />}
      />
      <Notice tone="warn" icon={Eye} title="Illustrative preview">
        This is a conceptual receipt layout populated with synthetic registry data. No receipts are generated in Phase 0.
      </Notice>

      <ApiView state={citizens} reload={citizens.reload}>
        {(cdata) => {
          const citizen = cdata.items.find((c) => c.citizen_ref === ref) ?? cdata.items[0]!;
          return (
            <div className="grid gap-6 xl:grid-cols-[340px_1fr]">
              <div className="flex flex-col gap-6">
                <Card>
                  <CardHeader icon={UserRound} title="Synthetic citizens" subtitle="GET /api/citizens" />
                  <ul className="p-2">
                    {cdata.items.map((c) => (
                      <li key={c.citizen_ref}>
                        <button
                          onClick={() => setRef(c.citizen_ref)}
                          aria-pressed={c.citizen_ref === citizen.citizen_ref}
                          className={clsx(
                            "flex w-full items-center justify-between gap-3 rounded-lg px-3 py-2.5 text-left transition-colors",
                            c.citizen_ref === citizen.citizen_ref ? "bg-ink-750" : "hover:bg-ink-800",
                          )}
                        >
                          <span className="min-w-0">
                            <span className="block truncate text-[13.5px] font-medium text-fg">{c.full_name}</span>
                            <span className="font-mono text-[11.5px] text-fg-subtle">{c.citizen_ref}</span>
                          </span>
                          <Badge tone={residencyTone[c.residency.status]}>{humanize(c.residency.status)}</Badge>
                        </button>
                      </li>
                    ))}
                  </ul>
                </Card>
                <Card>
                  <CardHeader title="Profile" subtitle="Synthetic service attributes" />
                  <dl className="grid grid-cols-2 gap-4 p-5">
                    <KeyValue label="Residency" mono>{citizen.residency.permit_ref}</KeyValue>
                    <KeyValue label="Expires">{formatDate(citizen.residency.expiry_date)}</KeyValue>
                    <KeyValue label="Emirate">{citizen.residency.emirate}</KeyValue>
                    <KeyValue label="Sponsor">{humanize(citizen.service_attributes.sponsor_type)}</KeyValue>
                    <KeyValue label="Insurance">
                      <Badge tone={insuranceTone[citizen.insurance.status]}>{humanize(citizen.insurance.status)}</Badge>
                    </KeyValue>
                    <KeyValue label="Valid until">{formatDate(citizen.insurance.valid_until)}</KeyValue>
                    <KeyValue label="Fines">{formatMoney(citizen.service_attributes.outstanding_fines)}</KeyValue>
                    <KeyValue label="Renewal eligible">{citizen.service_attributes.renewal_eligible ? "Yes" : "No"}</KeyValue>
                    <KeyValue label="Test account" mono>{citizen.account_ref}</KeyValue>
                  </dl>
                </Card>
              </div>

              <Card>
                <CardHeader icon={ReceiptText} title="Receipt preview" right={<Badge tone="warn">Illustrative</Badge>} />
                <div className="p-5 sm:p-8">
                  {agents.status === "success" && services.status === "success" && services.data.items[0] ? (
                    <Receipt citizen={citizen} agents={agents.data.items} service={services.data.items[0]} />
                  ) : (
                    <ApiView state={agents.status !== "success" ? agents : services} reload={agents.reload}>
                      {() => null}
                    </ApiView>
                  )}
                </div>
              </Card>
            </div>
          );
        }}
      </ApiView>
    </>
  );
}
