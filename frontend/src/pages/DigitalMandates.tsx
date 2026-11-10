import clsx from "clsx";
import { BadgeCheck, Braces, CheckCircle2, FileSignature, Landmark, ListChecks, RefreshCw, XCircle } from "lucide-react";
import { useState, type ReactNode } from "react";
import { ApiView, Badge, Card, CardHeader, Notice, PageHeader, SyntheticBadge } from "@/components/ui";
import { useApi } from "@/hooks/useApi";
import { formatMoney, humanize } from "@/lib/format";
import { schemaRows } from "@/lib/schema";
import type { IssuerView, JsonSchema, ListResponse, MandateView } from "@/types/api";

const CONTRACTS = ["DigitalMandate", "TrustedIssuer", "SignedActionRequest", "ActionRequest", "AuthorizationDecision", "AuditEvent", "AgentPassport"] as const;

/** What each mandate field means for enforcement. */
const MANDATE_FIELD_NOTES: Record<string, string> = {
  mandate_id: "Referenced by the agent's request and by every decision and audit event.",
  version: "Recorded in audit events; a re-issued mandate gets a new ID.",
  agent_id: "The single agent this mandate is issued to. Checked against the authenticated agent.",
  issuer_id: "Only selects which registered key must have signed. Confers no trust by itself.",
  service_id: "Must be within the issuer's authority and match the tool's service.",
  purpose: "Human-readable reason, shown on citizen receipts.",
  citizen_or_request_scope: "Binds the mandate to one citizen and one request. Other records are out of scope.",
  allowed_tools: "Exhaustive allow-list; must be a subset of the issuer's tools. Anything else is denied.",
  denied_tools: "Explicit denials, reported as DENY_TOOL_EXPLICITLY_DENIED.",
  resource_constraints: "Explicit resource type, access mode and identifiers. Wildcards are not representable.",
  amount_limit: "Maximum payment, AED, Decimal; must not exceed the issuer's max_amount.",
  recipient_allowlist: "Only these synthetic destinations may receive funds.",
  issued_at: "Start of the validity window (timezone-aware).",
  expires_at: "Hard expiry; ≤ 24 h and ≤ the issuer's max lifetime.",
  status: "Status as signed. Later revocation is recorded server-side and also enforced.",
  parent_mandate_id: "Delegation link. Delegated requests are refused until Phase 2.",
  signature_metadata: "Ed25519 over \"WAKALA-MANDATE-v1\\n\" + canonical JSON (excluding this field).",
};

const ENFORCED_CHECKS = [
  ["Identity", "Request signature verifies against the agent's registered Ed25519 key", "DENY_REQUEST_SIGNATURE_INVALID"],
  ["Agent status", "Passport exists, is active, key is the registered one", "DENY_AGENT_NOT_ACTIVE"],
  ["Mandate integrity", "Signed by a trusted issuer, within its authority, issued to this agent", "DENY_SIGNATURE_INVALID"],
  ["Mandate validity", "Inside its time window, not revoked", "DENY_MANDATE_EXPIRED"],
  ["Tool permission", "Tool registered, not denied, explicitly allowed, same service", "DENY_TOOL_NOT_PERMITTED"],
  ["Resource scope", "Citizen, request and target resource inside the mandate", "DENY_SCOPE_VIOLATION"],
  ["Action constraints", "Strict parameters; amount ≤ limit; recipient allow-listed", "DENY_AMOUNT_EXCEEDS_LIMIT"],
  ["Request context", "Timestamp fresh, nonce unused, no delegation chain", "DENY_REPLAYED_REQUEST"],
] as const;

const STATUS_TONE = { active: "trust", revoked: "deny", expired: "warn", not_yet_valid: "warn", invalid: "deny" } as const;

function Check({ ok, label }: { ok: boolean; label: string }) {
  return (
    <span className={clsx("inline-flex items-center gap-1.5 text-[12.5px]", ok ? "text-trust" : "text-deny")}>
      {ok ? <CheckCircle2 className="size-3.5" aria-hidden /> : <XCircle className="size-3.5" aria-hidden />} {label}
    </span>
  );
}

function Row({ k, children }: { k: string; children: ReactNode }) {
  return (
    <div className="contents">
      <dt className="text-[12.5px] text-fg-subtle">{k}</dt>
      <dd className="break-words font-mono text-[12.5px] text-fg">{children}</dd>
    </div>
  );
}

function MandateCard({ view }: { view: MandateView }) {
  const m = view.mandate;
  const v = view.verification;
  const time = (iso: string) => new Date(iso).toLocaleString("en-GB", { day: "2-digit", month: "short", hour: "2-digit", minute: "2-digit" });
  return (
    <Card className="flex flex-col">
      <div className="flex items-start justify-between gap-4 border-b border-line p-5">
        <div className="min-w-0">
          <p className="eyebrow">Digital mandate · v{m.version}</p>
          <p className="mt-1 break-all font-mono text-[14px] font-semibold text-fg">{m.mandate_id}</p>
          <p className="mt-1 text-[13px] text-fg-muted">{m.purpose}</p>
        </div>
        <Badge tone={STATUS_TONE[v.effective_status]} dot>{humanize(v.effective_status)}</Badge>
      </div>
      <div className="flex flex-wrap gap-x-4 gap-y-1.5 border-b border-line bg-ink-900/40 px-5 py-3">
        <Check ok={v.signature_valid} label="Ed25519 signature" />
        <Check ok={v.issuer_trusted} label="Trusted issuer" />
        <Check ok={v.within_issuer_authority} label="Within issuer authority" />
        <Check ok={!view.revoked && v.effective_status !== "expired" && v.effective_status !== "not_yet_valid"} label="Validity window" />
      </div>
      <dl className="grid flex-1 gap-x-5 gap-y-2 p-5 sm:grid-cols-[140px_1fr]">
        <Row k="Agent">{m.agent_id}</Row>
        <Row k="Issuer">{m.issuer_id}</Row>
        <Row k="Service">{m.service_id}</Row>
        <Row k="Citizen · request">{m.citizen_or_request_scope.citizen_ref} · {m.citizen_or_request_scope.request_id}</Row>
        <Row k="Allowed tools"><span className="text-trust">{m.allowed_tools.join(", ")}</span></Row>
        <Row k="Denied tools"><span className="text-deny/90">{m.denied_tools.join(", ") || "—"}</span></Row>
        <Row k="Resources">
          {m.resource_constraints.map((r) => `${r.resource_type}:${r.access} [${r.identifiers.join(", ")}]`).join("; ") || "—"}
        </Row>
        <Row k="Amount limit">{m.amount_limit ? formatMoney(m.amount_limit) : "none — no monetary authority"}</Row>
        <Row k="Recipients">{m.recipient_allowlist.join(", ") || "—"}</Row>
        <Row k="Valid">{time(m.issued_at)} → {time(m.expires_at)}</Row>
        <Row k="Signed with">{m.signature_metadata ? `${m.signature_metadata.algorithm} · ${m.signature_metadata.key_id}` : "UNSIGNED"}</Row>
        <Row k="Signature">
          <span className="text-fg-subtle" title={m.signature_metadata?.signature}>{m.signature_metadata?.signature.slice(0, 32)}…</span>
        </Row>
      </dl>
      {(v.reason_codes.length > 0 || view.revoked) && (
        <div className="border-t border-line px-5 py-3 font-mono text-[11.5px] text-deny">
          {v.reason_codes.join(" · ")} {view.revocation_reason && <span className="text-fg-subtle">— {view.revocation_reason}</span>}
        </div>
      )}
    </Card>
  );
}

function Mandates() {
  const state = useApi<ListResponse<MandateView>>("/api/mandates", { live: true });
  return (
    <ApiView state={state} reload={state.reload}>
      {(data) => (
        <>
          <div className="mb-3 flex items-center justify-between">
            <p className="text-[13px] text-fg-muted">
              {data.count} stored mandate{data.count === 1 ? "" : "s"} · verified against registered issuer keys at{" "}
              {data.items[0] ? new Date(data.items[0].verification.checked_at).toLocaleTimeString("en-GB") : "—"}
            </p>
            <button onClick={state.reload} className="inline-flex items-center gap-1.5 rounded-lg border border-line px-2.5 py-1.5 text-[12px] text-fg-muted hover:bg-ink-750 hover:text-fg">
              <RefreshCw className="size-3.5" aria-hidden /> Re-verify
            </button>
          </div>
          <div className="grid gap-6 xl:grid-cols-2 2xl:grid-cols-3">
            {data.items.map((v) => <MandateCard key={v.mandate.mandate_id} view={v} />)}
          </div>
        </>
      )}
    </ApiView>
  );
}

function Issuers() {
  const state = useApi<ListResponse<IssuerView>>("/api/issuers");
  return (
    <Card>
      <CardHeader icon={Landmark} title="Trusted issuer registry" subtitle="GET /api/issuers · each issuer can grant only what is listed" />
      <ApiView state={state} reload={state.reload}>
        {(data) => (
          <ul className="divide-y divide-line">
            {data.items.map(({ issuer, key_fingerprint, key_registered }) => (
              <li key={issuer.issuer_id} className="px-5 py-4">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="font-mono text-[13px] font-semibold text-fg">{issuer.issuer_id}</span>
                  <Badge tone={issuer.status === "active" && key_registered ? "trust" : "deny"} dot>
                    {issuer.status === "active" && key_registered ? "Trusted" : "Not trusted"}
                  </Badge>
                </div>
                <p className="mt-0.5 text-[12.5px] text-fg-muted">{issuer.name}</p>
                <p className="mt-2 text-[12.5px] text-fg-muted">
                  Agents <span className="font-mono text-fg">{issuer.authority.agents.join(", ")}</span> · tools{" "}
                  <span className="font-mono text-fg">{issuer.authority.tools.join(", ")}</span> · max{" "}
                  <span className="text-fg">{issuer.authority.max_amount ? formatMoney(issuer.authority.max_amount) : "no money"}</span> · ≤{" "}
                  {issuer.authority.max_lifetime_hours} h
                </p>
                <p className="mt-1 break-all font-mono text-[11px] text-fg-subtle">{issuer.key_id} · {key_fingerprint ?? "no key registered"}</p>
              </li>
            ))}
          </ul>
        )}
      </ApiView>
    </Card>
  );
}

function EnforcedChecks() {
  return (
    <Card>
      <CardHeader icon={ListChecks} title="Enforced authorization checks" subtitle="Deterministic; checks 1–4 short-circuit, 5–8 report every violation" right={<Badge tone="trust">Active</Badge>} />
      <ol className="divide-y divide-line">
        {ENFORCED_CHECKS.map(([name, rule, code], i) => (
          <li key={name} className="flex gap-4 px-5 py-3">
            <span className="grid size-6 shrink-0 place-items-center rounded-full border border-trust/40 font-mono text-[11px] text-trust">{i + 1}</span>
            <div className="min-w-0">
              <p className="text-[13.5px] font-medium text-fg">{name}</p>
              <p className="text-[13px] text-fg-muted">{rule}</p>
              <p className="mt-0.5 font-mono text-[11px] text-deny/80">e.g. {code}</p>
            </div>
          </li>
        ))}
        <li className="flex gap-4 bg-ink-800/50 px-5 py-3">
          <span className="grid size-6 shrink-0 place-items-center rounded-full border border-deny/40 font-mono text-[11px] text-deny">∅</span>
          <p className="text-[13px] text-fg-muted">
            <span className="font-medium text-fg">Default:</span> anything not positively authorized — including evaluation
            errors — is denied.
          </p>
        </li>
      </ol>
    </Card>
  );
}

function SchemaExplorer() {
  const [name, setName] = useState<(typeof CONTRACTS)[number]>("DigitalMandate");
  const schema = useApi<JsonSchema>(`/api/schemas/${name}`);
  return (
    <Card>
      <CardHeader
        icon={Braces}
        title="Contract schemas"
        subtitle={<>Rendered live from the backend Pydantic models · <span className="font-mono">GET /api/schemas/{name}</span></>}
      />
      <div className="flex gap-1 overflow-x-auto border-b border-line px-4 pt-3" role="tablist">
        {CONTRACTS.map((c) => (
          <button
            key={c}
            role="tab"
            aria-selected={c === name}
            onClick={() => setName(c)}
            className={clsx(
              "shrink-0 rounded-t-lg border-b-2 px-3 pb-2.5 pt-1.5 font-mono text-[12.5px] transition-colors",
              c === name ? "border-trust text-fg" : "border-transparent text-fg-subtle hover:text-fg-muted",
            )}
          >
            {c}
          </button>
        ))}
      </div>
      <ApiView state={schema} reload={schema.reload}>
        {(data) => (
          <div className="overflow-x-auto">
            <table className="w-full min-w-[760px] text-left text-[13px]">
              <thead>
                <tr className="border-b border-line text-[11.5px] uppercase tracking-wider text-fg-subtle">
                  <th className="px-5 py-3 font-medium">Field</th>
                  <th className="px-5 py-3 font-medium">Type</th>
                  <th className="px-5 py-3 font-medium">Constraints</th>
                  {name === "DigitalMandate" && <th className="px-5 py-3 font-medium">Enforcement meaning</th>}
                </tr>
              </thead>
              <tbody>
                {schemaRows(data).map((row) => (
                  <tr key={row.name} className="border-b border-line/60 align-top last:border-0">
                    <td className="whitespace-nowrap px-5 py-3">
                      <span className="font-mono text-[12.5px] text-fg">{row.name}</span>
                      <span className={clsx("ml-2 text-[10.5px] uppercase tracking-wider", row.required ? "text-trust" : "text-fg-subtle")}>
                        {row.required ? "required" : "optional"}
                      </span>
                    </td>
                    <td className="whitespace-nowrap px-5 py-3 font-mono text-[12px] text-cyan">
                      {row.type}
                      {row.nullable && <span className="text-fg-subtle"> | null</span>}
                    </td>
                    <td className="px-5 py-3">
                      <div className="flex max-w-[360px] flex-wrap gap-1">
                        {row.constraints.length === 0 && <span className="text-fg-subtle">—</span>}
                        {row.constraints.map((c) => (
                          <span key={c} className="break-all rounded border border-line bg-ink-800 px-1.5 py-0.5 font-mono text-[11px] text-fg-muted">{c}</span>
                        ))}
                      </div>
                    </td>
                    {name === "DigitalMandate" && <td className="max-w-[340px] px-5 py-3 text-fg-muted">{MANDATE_FIELD_NOTES[row.name] ?? "—"}</td>}
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

export function DigitalMandates() {
  return (
    <>
      <PageHeader
        eyebrow="Authority"
        title="Digital Mandates"
        titleAr="التفويضات الرقمية"
        description="A mandate states who may do what, for whom, for how long and within which limits. It is trusted only because a registered issuer signed it — never because of what its fields claim."
        actions={<SyntheticBadge />}
      />
      <Notice tone="trust" icon={BadgeCheck} title="Live mandates, verified on every page load and every gateway decision">
        These are the signed development mandates in the server's store. Signatures are checked against the trusted issuer
        registry; any modification after signing marks a mandate invalid. Mandates are technical authorization artefacts,
        not legal powers of attorney.
      </Notice>
      <div className="mb-3 flex items-center gap-3">
        <h2 className="eyebrow flex items-center gap-2"><FileSignature className="size-3.5" aria-hidden /> Stored mandates</h2>
        <span className="h-px flex-1 bg-line" />
      </div>
      <Mandates />
      <div className="mt-6 grid gap-6 xl:grid-cols-[1.1fr_1fr]">
        <Issuers />
        <EnforcedChecks />
      </div>
      <div className="mt-6">
        <SchemaExplorer />
      </div>
    </>
  );
}
