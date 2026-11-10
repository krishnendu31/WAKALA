import clsx from "clsx";
import { AlertTriangle, FlaskConical, Loader2, RefreshCw, type LucideIcon } from "lucide-react";
import type { ReactNode } from "react";
import type { Tone } from "@/lib/format";
import type { ApiState } from "@/hooks/useApi";

const toneClasses: Record<Tone, string> = {
  trust: "border-trust/25 bg-trust-soft text-trust",
  warn: "border-warn/25 bg-warn-soft text-warn",
  deny: "border-deny/30 bg-deny-soft text-deny",
  plan: "border-plan/25 bg-plan-soft text-plan",
  neutral: "border-line-strong bg-ink-750 text-fg-muted",
};

const dotClasses: Record<Tone, string> = {
  trust: "bg-trust",
  warn: "bg-warn",
  deny: "bg-deny",
  plan: "bg-plan",
  neutral: "bg-fg-subtle",
};

export function Badge({ tone = "neutral", children, dot, className }: { tone?: Tone; children: ReactNode; dot?: boolean; className?: string }) {
  return (
    <span
      className={clsx(
        "inline-flex items-center gap-1.5 whitespace-nowrap rounded-full border px-2 py-0.5 text-[11px] font-medium leading-4",
        toneClasses[tone],
        className,
      )}
    >
      {dot && <span className={clsx("size-1.5 rounded-full", dotClasses[tone])} aria-hidden />}
      {children}
    </span>
  );
}

export function SyntheticBadge({ label = "Synthetic data" }: { label?: string }) {
  return (
    <Badge className="border-gold/35 bg-gold-soft uppercase tracking-wider text-gold-strong">
      <FlaskConical className="size-3" aria-hidden />
      {label}
    </Badge>
  );
}

export function PageHeader({
  eyebrow,
  title,
  titleAr,
  description,
  actions,
}: {
  eyebrow?: string;
  title: string;
  titleAr: string;
  description: ReactNode;
  actions?: ReactNode;
}) {
  return (
    <header className="mb-7 flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
      <div className="max-w-3xl">
        {eyebrow && <p className="eyebrow mb-2">{eyebrow}</p>}
        <div className="flex flex-wrap items-baseline gap-x-4 gap-y-1">
          <h1 className="text-[28px] font-semibold tracking-tight text-navy">{title}</h1>
          <span lang="ar" dir="rtl" className="text-xl text-gold">
            {titleAr}
          </span>
        </div>
        <p className="mt-2 text-[15px] leading-relaxed text-fg-muted">{description}</p>
      </div>
      {actions && <div className="flex shrink-0 items-center gap-2">{actions}</div>}
    </header>
  );
}

export function Card({ children, className }: { children: ReactNode; className?: string }) {
  return <section className={clsx("card animate-fade-in", className)}>{children}</section>;
}

export function CardHeader({ title, subtitle, icon: Icon, right }: { title: string; subtitle?: ReactNode; icon?: LucideIcon; right?: ReactNode }) {
  return (
    <div className="card-header">
      <div className="flex min-w-0 items-start gap-3">
        {Icon && (
          <span className="mt-0.5 grid size-8 shrink-0 place-items-center rounded-lg border border-line bg-ink-800 text-fg-muted">
            <Icon className="size-4" aria-hidden />
          </span>
        )}
        <div className="min-w-0">
          <h2 className="text-[15px] font-semibold text-fg">{title}</h2>
          {subtitle && <p className="mt-0.5 text-[13px] text-fg-subtle">{subtitle}</p>}
        </div>
      </div>
      {right}
    </div>
  );
}

/** A banner that makes clear the content below is illustrative, not live. */
export function Notice({ tone = "plan", icon: Icon = AlertTriangle, title, children }: { tone?: Tone; icon?: LucideIcon; title: string; children: ReactNode }) {
  return (
    <div className={clsx("mb-6 flex gap-3 rounded-xl border px-4 py-3", toneClasses[tone])} role="note">
      <Icon className="mt-0.5 size-4 shrink-0" aria-hidden />
      <div className="text-[13.5px] leading-relaxed">
        <p className="font-semibold">{title}</p>
        <div className="text-fg-muted">{children}</div>
      </div>
    </div>
  );
}

export function EmptyState({ icon: Icon, title, children }: { icon: LucideIcon; title: string; children?: ReactNode }) {
  return (
    <div className="flex flex-col items-center justify-center px-6 py-16 text-center">
      <span className="mb-4 grid size-12 place-items-center rounded-2xl border border-line bg-ink-800 text-fg-subtle">
        <Icon className="size-5" aria-hidden />
      </span>
      <p className="text-base font-semibold text-fg">{title}</p>
      {children && <div className="mt-2 max-w-md text-sm leading-relaxed text-fg-muted">{children}</div>}
    </div>
  );
}

/** Renders loading / error states for a useApi result, children on success. */
export function ApiView<T>({ state, children, reload }: { state: ApiState<T>; reload?: () => void; children: (data: T) => ReactNode }) {
  if (state.status === "loading") {
    return (
      <div className="flex items-center gap-2 px-5 py-10 text-sm text-fg-subtle" role="status">
        <Loader2 className="size-4 animate-spin" aria-hidden /> Loading from WAKALA API…
      </div>
    );
  }
  if (state.status === "error") {
    return (
      <div className="m-5 flex items-start justify-between gap-4 rounded-xl border border-deny/30 bg-deny-soft px-4 py-3 text-sm" role="alert">
        <div>
          <p className="font-semibold text-deny">Could not load data</p>
          <p className="mt-0.5 text-fg-muted">{state.error.message}</p>
          <p className="mt-1 text-xs text-fg-subtle">
            Start the backend: <span className="kbd">uvicorn app.main:app --port 8000</span>
          </p>
        </div>
        {reload && (
          <button onClick={reload} className="inline-flex items-center gap-1.5 rounded-lg border border-line px-2.5 py-1.5 text-xs text-fg-muted hover:bg-ink-750 hover:text-fg">
            <RefreshCw className="size-3.5" aria-hidden /> Retry
          </button>
        )}
      </div>
    );
  }
  return <>{children(state.data)}</>;
}

export function KeyValue({ label, children, mono }: { label: string; children: ReactNode; mono?: boolean }) {
  return (
    <div className="min-w-0">
      <dt className="text-[11.5px] font-medium uppercase tracking-wider text-fg-subtle">{label}</dt>
      <dd className={clsx("mt-1 break-words text-[13.5px] leading-snug text-fg", mono && "break-all font-mono text-[12.5px]")}>{children}</dd>
    </div>
  );
}
