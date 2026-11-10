import { Braces, CreditCard, FileCheck2, FileSignature, KeyRound, ShieldAlert, Stethoscope, type LucideIcon } from "lucide-react";
import { useState } from "react";
import { ApiView, Badge, Card, KeyValue, Notice, PageHeader, SyntheticBadge } from "@/components/ui";
import { useApi } from "@/hooks/useApi";
import { agentStatusTone, humanize, riskTone } from "@/lib/format";
import type { AgentPassport, ListResponse, MandateView } from "@/types/api";
import { formatMoney } from "@/lib/format";

const ROLE_ICON: Record<string, LucideIcon> = {
  "AGT-RES-001": FileCheck2,
  "AGT-INS-001": Stethoscope,
  "AGT-PAY-001": CreditCard,
};

function RawPassport({ agentId }: { agentId: string }) {
  const state = useApi<AgentPassport>(`/api/agents/${agentId}`);
  return (
    <ApiView state={state} reload={state.reload}>
      {(data) => (
        <pre className="max-h-72 overflow-auto rounded-lg border border-line bg-ink-950 p-4 font-mono text-[11.5px] leading-relaxed text-fg-muted">
          {JSON.stringify(data, null, 2)}
        </pre>
      )}
    </ApiView>
  );
}

const MANDATE_TONE = { active: "trust", revoked: "deny", expired: "warn", not_yet_valid: "warn", invalid: "deny" } as const;

function AgentMandates({ agentId }: { agentId: string }) {
  const state = useApi<ListResponse<MandateView>>(`/api/mandates?agent_id=${agentId}`, { live: true });
  return (
    <div>
      <p className="text-[11.5px] font-medium uppercase tracking-wider text-fg-subtle">Mandates (verified now)</p>
      <ApiView state={state} reload={state.reload}>
        {(data) =>
          data.items.length === 0 ? (
            <p className="mt-2 text-[13px] text-warn">No mandate issued — every action will be denied.</p>
          ) : (
            <ul className="mt-2 space-y-1.5">
              {data.items.slice(0, 3).map((m) => (
                <li key={m.mandate.mandate_id} className="flex flex-wrap items-center gap-2 rounded-lg border border-line bg-ink-800/60 px-3 py-2">
                  <FileSignature className="size-3.5 text-fg-subtle" aria-hidden />
                  <span className="font-mono text-[12px] text-fg">{m.mandate.mandate_id}</span>
                  <Badge tone={MANDATE_TONE[m.verification.effective_status]} dot>{humanize(m.verification.effective_status)}</Badge>
                  <span className="text-[12px] text-fg-subtle">
                    by {m.mandate.issuer_id}
                    {m.mandate.amount_limit ? ` · ≤ ${formatMoney(m.mandate.amount_limit)}` : ""} · expires{" "}
                    {new Date(m.mandate.expires_at).toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit" })}
                  </span>
                </li>
              ))}
            </ul>
          )
        }
      </ApiView>
    </div>
  );
}

function PassportCard({ agent }: { agent: AgentPassport }) {
  const [showRaw, setShowRaw] = useState(false);
  const Icon = ROLE_ICON[agent.agent_id] ?? FileCheck2;
  const key = agent.identity_key_reference;
  return (
    <Card className="flex flex-col">
      <div className="flex items-start gap-4 border-b border-line p-5">
        <span className="grid size-11 shrink-0 place-items-center rounded-xl border border-trust/25 bg-trust-soft text-trust">
          <Icon className="size-5" aria-hidden />
        </span>
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-baseline gap-x-3">
            <h2 className="text-[17px] font-semibold text-fg">{agent.name}</h2>
            <span lang="ar" className="text-[15px] text-fg-subtle">{agent.name_ar}</span>
          </div>
          <p className="mt-0.5 font-mono text-[12px] text-fg-subtle">{agent.agent_id}</p>
          <div className="mt-3 flex flex-wrap gap-1.5">
            <Badge tone={agentStatusTone[agent.status]} dot>{humanize(agent.status)}</Badge>
            <Badge tone={riskTone[agent.risk_level]}>{humanize(agent.risk_level)} risk</Badge>
            <Badge tone="warn">Synthetic</Badge>
          </div>
        </div>
      </div>

      <div className="flex flex-1 flex-col gap-5 p-5">
        <p className="text-[13.5px] leading-relaxed text-fg-muted">{agent.description}</p>

        <dl className="grid grid-cols-1 gap-4 sm:grid-cols-2">
          <KeyValue label="Owning entity">{agent.owner_entity}</KeyValue>
          <KeyValue label="Platform">{agent.platform}</KeyValue>
          <KeyValue label="Accountable officer">
            {agent.accountable_officer.name}
            <span className="block truncate text-[12px] text-fg-subtle">
              {agent.accountable_officer.title} · {agent.accountable_officer.officer_id}
            </span>
          </KeyValue>
          <KeyValue label="Identity key">
            <span className="inline-flex items-center gap-1.5 font-mono text-[12.5px]">
              <KeyRound className="size-3.5 text-fg-subtle" aria-hidden /> {key.key_id}
            </span>
            <span className={key.provisioning_status === "provisioned" ? "block text-[12px] text-trust" : "block text-[12px] text-warn"}>
              {key.algorithm} · {humanize(key.provisioning_status)}
            </span>
            {key.public_key_fingerprint && (
              <span className="block break-all font-mono text-[11px] text-fg-subtle" title="SHA-256 of the registered public key">
                {key.public_key_fingerprint}
              </span>
            )}
          </KeyValue>
        </dl>

        <div>
          <p className="text-[11.5px] font-medium uppercase tracking-wider text-fg-subtle">Declared tools</p>
          <div className="mt-2 flex flex-wrap gap-1.5">
            {agent.declared_tools.map((t) => (
              <span key={t} className="rounded-md border border-line bg-ink-800 px-2 py-1 font-mono text-[11.5px] text-fg-muted">
                {t}
              </span>
            ))}
          </div>
          <p className="mt-2 text-[12px] text-fg-subtle">Declared ≠ authorized. Every call requires a valid signed mandate.</p>
        </div>

        <AgentMandates agentId={agent.agent_id} />

        <div>
          <p className="text-[11.5px] font-medium uppercase tracking-wider text-fg-subtle">Registered restrictions</p>
          <ul className="mt-2 space-y-1.5">
            {agent.restrictions.map((r) => (
              <li key={r} className="flex gap-2 text-[13px] text-fg-muted">
                <ShieldAlert className="mt-0.5 size-3.5 shrink-0 text-fg-subtle" aria-hidden /> {r}
              </li>
            ))}
          </ul>
        </div>

        <div className="mt-auto border-t border-line pt-4">
          <button
            onClick={() => setShowRaw((v) => !v)}
            className="inline-flex items-center gap-1.5 text-[13px] text-trust hover:underline"
            aria-expanded={showRaw}
          >
            <Braces className="size-3.5" aria-hidden /> {showRaw ? "Hide" : "View"} raw passport
            <span className="font-mono text-[11px] text-fg-subtle">GET /api/agents/{agent.agent_id}</span>
          </button>
          {showRaw && <div className="mt-3"><RawPassport agentId={agent.agent_id} /></div>}
        </div>
      </div>
    </Card>
  );
}

export function AgentRegistry() {
  const agents = useApi<ListResponse<AgentPassport>>("/api/agents");
  return (
    <>
      <PageHeader
        eyebrow="Identity"
        title="Agent Registry"
        titleAr="سجل الوكلاء"
        description="Every agent has a passport: an owning entity, a named accountable officer, a risk level and a registered public key. A passport identifies an agent; only a valid request signature authenticates one."
        actions={<SyntheticBadge />}
      />
      <Notice tone="trust" icon={KeyRound} title="Identity is proven by signature, never by agent ID">
        Each agent has an Ed25519 key pair. Only the public key and its fingerprint are registered here; the gateway
        rejects any request whose signature does not verify against it. These are local <b>development keys</b> for
        synthetic identities — production would use workload identity or managed signing keys.
      </Notice>
      <ApiView state={agents} reload={agents.reload}>
        {(data) => (
          <div className="grid gap-6 lg:grid-cols-2 2xl:grid-cols-3">
            {data.items.map((a) => (
              <PassportCard key={a.agent_id} agent={a} />
            ))}
          </div>
        )}
      </ApiView>
    </>
  );
}
