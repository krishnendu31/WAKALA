import clsx from "clsx";
import { FileWarning, FlaskConical, Lock, Play, ScrollText, ShieldQuestion } from "lucide-react";
import { DevDemo } from "@/components/DevDemo";
import { ApiView, Badge, Card, KeyValue, Notice, PageHeader, SyntheticBadge } from "@/components/ui";
import { useApi } from "@/hooks/useApi";
import type { ListResponse, ScenarioWithDocument } from "@/types/api";

/** Highlights the HTML-comment payload in the injected fixture. */
function DocumentViewer({ content, injected }: { content: string; injected: boolean }) {
  const start = content.indexOf("<!--");
  const end = content.indexOf("-->");
  const hasPayload = injected && start >= 0 && end > start;
  return (
    <>
      {hasPayload && (
        <div className="mb-3 rounded-lg border border-deny/30 bg-deny-soft p-3.5">
          <p className="text-[11.5px] font-semibold uppercase tracking-wider text-deny">Embedded instruction in fixture</p>
          <p className="mt-1.5 font-mono text-[11.5px] leading-relaxed text-fg">
            {content.slice(start + 4, end).replace(/\s+/g, " ").trim()}
          </p>
          <p className="mt-2 text-[12px] text-fg-muted">
            Document text is data, not authority. Under WAKALA, this instruction cannot create a mandate, raise a limit or
            add a recipient.
          </p>
        </div>
      )}
      <pre className="max-h-[340px] overflow-auto whitespace-pre-wrap break-words rounded-lg border border-line bg-ink-950 p-4 font-mono text-[11.5px] leading-relaxed text-fg-muted">
      {hasPayload ? (
        <>
          {content.slice(0, start)}
          <mark className="rounded bg-deny-soft px-0.5 text-deny ring-1 ring-deny/30">{content.slice(start, end + 3)}</mark>
          {content.slice(end + 3)}
        </>
      ) : (
        content
      )}
      </pre>
    </>
  );
}

function ScenarioCard({ item }: { item: ScenarioWithDocument }) {
  const { scenario: s, document: d } = item;
  const attack = s.category === "prompt_injection";
  return (
    <Card className="flex flex-col">
      <div className="flex items-start justify-between gap-4 border-b border-line p-5">
        <div className="flex items-start gap-3.5">
          <span
            className={clsx(
              "grid size-10 shrink-0 place-items-center rounded-xl border",
              attack ? "border-warn/30 bg-warn-soft text-warn" : "border-trust/25 bg-trust-soft text-trust",
            )}
          >
            {attack ? <FileWarning className="size-5" aria-hidden /> : <ScrollText className="size-5" aria-hidden />}
          </span>
          <div>
            <p className="font-mono text-[11.5px] text-fg-subtle">{s.scenario_id}</p>
            <h2 className="text-[16px] font-semibold text-fg">{s.title}</h2>
            <div className="mt-2 flex flex-wrap gap-1.5">
              <Badge tone={attack ? "warn" : "trust"}>{attack ? "Prompt injection fixture" : "Baseline"}</Badge>
              <Badge tone="plan">Target: Phase {s.target_phase}</Badge>
            </div>
          </div>
        </div>
        <button
          disabled
          aria-disabled
          title="Agent-driven execution arrives in Phase 3"
          className="inline-flex shrink-0 cursor-not-allowed items-center gap-1.5 rounded-lg border border-line bg-ink-800 px-3 py-2 text-[13px] text-fg-subtle"
        >
          <Lock className="size-3.5" aria-hidden /> Run
          <Play className="size-3.5 opacity-40" aria-hidden />
        </button>
      </div>

      <div className="flex flex-1 flex-col gap-5 p-5">
        <p className="text-[13.5px] leading-relaxed text-fg-muted">{s.summary}</p>

        <div className="rounded-xl border border-line bg-ink-800/60 p-4">
          <p className="flex items-center gap-2 text-[11.5px] font-medium uppercase tracking-wider text-fg-subtle">
            <ShieldQuestion className="size-3.5" aria-hidden /> Planned expected outcome
          </p>
          <p className="mt-1.5 text-[13.5px] leading-relaxed text-fg">{s.planned_expected_outcome}</p>
          <p className="mt-2 text-[12px] text-fg-subtle">Not yet run with an agent. Gateway-level behaviour is demonstrated above.</p>
        </div>

        <div>
          <div className="mb-2 flex items-center justify-between gap-3">
            <p className="text-[11.5px] font-medium uppercase tracking-wider text-fg-subtle">Document fixture</p>
            <Badge tone="neutral">Untrusted input</Badge>
          </div>
          <DocumentViewer content={d.content} injected={d.contains_injected_instruction} />
          <dl className="mt-3 grid grid-cols-2 gap-3">
            <KeyValue label="Document" mono>{d.document_id}</KeyValue>
            <KeyValue label="Citizen" mono>{d.citizen_ref}</KeyValue>
            <div className="col-span-2">
              <KeyValue label="SHA-256" mono>
                <span title={d.sha256}>{d.sha256}</span>
              </KeyValue>
            </div>
          </dl>
        </div>
      </div>
    </Card>
  );
}

export function SimulationLab() {
  const scenarios = useApi<ListResponse<ScenarioWithDocument>>("/api/scenarios");
  return (
    <>
      <PageHeader
        eyebrow="Evaluation"
        title="Simulation Lab"
        titleAr="مختبر المحاكاة"
        description="Controlled scenarios for testing the enforcement engine against legitimate and adversarial inputs. Documents are always treated as untrusted data, never as instructions."
        actions={<SyntheticBadge />}
      />
      <DevDemo />
      <div className="mb-3 flex items-center gap-3">
        <h2 className="eyebrow">Agent-driven document fixtures</h2>
        <span className="h-px flex-1 bg-line" />
      </div>
      <Notice icon={FlaskConical} title="Full agent-driven runs arrive in Phase 3">
        The enforcement engine is live (see the developer demonstration above, whose "Invalid amount" scenario sends exactly
        the AED 50,000 transfer this document asks for). Running these documents through an actual AI agent end to end is
        scheduled for Phase 3, so these Run buttons stay disabled. The injected instruction targets a fictional account and
        is never connected to any payment system.
      </Notice>
      <ApiView state={scenarios} reload={scenarios.reload}>
        {(data) => (
          <div className="grid gap-6 xl:grid-cols-2">
            {data.items.map((item) => (
              <ScenarioCard key={item.scenario.scenario_id} item={item} />
            ))}
          </div>
        )}
      </ApiView>
    </>
  );
}
