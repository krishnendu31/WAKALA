import clsx from "clsx";
import { FlaskConical, ShieldCheck } from "lucide-react";
import { Fragment, useEffect } from "react";
import { NavLink, Outlet, useLocation } from "react-router-dom";
import { useApi } from "@/hooks/useApi";
import { API_BASE_URL } from "@/lib/api";
import { NAV_ITEMS } from "@/lib/navigation";
import type { Health, SystemCapabilities } from "@/types/api";

function BrandMark() {
  return (
    <svg viewBox="0 0 32 32" className="size-9 shrink-0" aria-hidden>
      <rect width="32" height="32" rx="9" fill="#0d172b" stroke="#263a5e" />
      <path d="M16 6 8 9.2v5.9c0 4.8 3.4 8.6 8 9.9 4.6-1.3 8-5.1 8-9.9V9.2L16 6Z" fill="none" stroke="#2dd4bf" strokeWidth="1.6" strokeLinejoin="round" />
      <path d="m12.2 15.4 2.7 2.7 5-5.4" fill="none" stroke="#2dd4bf" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

function ApiStatus() {
  const health = useApi<Health>("/health");
  const online = health.status === "success";
  const label = health.status === "loading" ? "Connecting" : online ? `API online · v${health.data.version}` : "API offline";
  return (
    <div className="flex items-center gap-2 text-xs text-fg-muted" title={API_BASE_URL}>
      <span className="relative flex size-2">
        {online && <span className="absolute inline-flex size-full animate-ping rounded-full bg-trust/50 [animation-duration:2.4s]" />}
        <span className={clsx("relative inline-flex size-2 rounded-full", online ? "bg-trust" : health.status === "loading" ? "bg-fg-subtle" : "bg-deny")} />
      </span>
      {label}
    </div>
  );
}

function PhaseIndicator() {
  const caps = useApi<SystemCapabilities>("/api/system/capabilities");
  if (caps.status !== "success") return null;
  const engine = caps.data.enforcement_engine_connected;
  return (
    <div className="hidden items-center gap-2 text-xs md:flex">
      <span className="rounded-md border border-line bg-ink-800 px-2 py-1 text-fg-muted">
        Phase {caps.data.current_phase} · Security engine
      </span>
      <span
        className={clsx(
          "rounded-md border px-2 py-1",
          engine ? "border-trust/30 bg-trust-soft text-trust" : "border-plan/25 bg-plan-soft text-plan",
        )}
      >
        Enforcement engine: {engine ? "connected" : "not connected"}
      </span>
    </div>
  );
}

export function AppLayout() {
  const location = useLocation();
  const current = NAV_ITEMS.find((n) => (n.path === "/" ? location.pathname === "/" : location.pathname.startsWith(n.path)));

  useEffect(() => {
    document.title = `${current?.label ?? "WAKALA"} · WAKALA | وكالة`;
    window.scrollTo({ top: 0 });
  }, [current]);

  return (
    <div className="flex min-h-screen">
      <aside className="sticky top-0 hidden h-screen w-[268px] shrink-0 flex-col border-r border-line bg-ink-950/70 backdrop-blur lg:flex">
        <div className="flex items-center gap-3 px-5 pb-6 pt-6">
          <BrandMark />
          <div className="min-w-0">
            <p className="flex items-baseline gap-2 text-[17px] font-semibold tracking-[0.08em] text-fg">
              WAKALA
              <span className="text-line-strong">|</span>
              <span lang="ar" className="text-[17px] tracking-normal">وكالة</span>
            </p>
            <p className="truncate text-[11.5px] text-fg-subtle">Autonomous AI. Accountable Authority.</p>
          </div>
        </div>

        <nav className="flex-1 space-y-0.5 overflow-y-auto px-3" aria-label="Main">
          {NAV_ITEMS.map(({ path, label, labelAr, icon: Icon, section }, i) => (<Fragment key={path}>
            {(i === 0 || NAV_ITEMS[i - 1]!.section !== section) && (
              <p className={clsx("eyebrow px-3 pb-2", i > 0 && "pt-5")}>{section === "demo" ? "Live demonstration" : "Platform"}</p>
            )}
            <NavLink
              key={path}
              to={path}
              end={path === "/"}
              title={`${label} · ${labelAr}`}
              className={({ isActive }) =>
                clsx(
                  "group relative flex items-center gap-3 rounded-lg px-3 py-2.5 text-[14px] transition-colors duration-150",
                  isActive ? "bg-ink-750 text-fg" : "text-fg-muted hover:bg-ink-800 hover:text-fg",
                )
              }
            >
              {({ isActive }) => (
                <>
                  <span
                    className={clsx(
                      "absolute inset-y-2 left-0 w-[3px] rounded-r-full transition-colors",
                      isActive ? "bg-trust" : "bg-transparent",
                    )}
                    aria-hidden
                  />
                  <Icon className={clsx("size-[18px] shrink-0", isActive ? "text-trust" : "text-fg-subtle group-hover:text-fg-muted")} aria-hidden />
                  <span className="flex-1 truncate">{label}</span>
                </>
              )}
            </NavLink>
          </Fragment>))}
        </nav>

        <div className="m-3 rounded-xl border border-warn/20 bg-warn-soft p-3.5">
          <p className="flex items-center gap-2 text-[12px] font-semibold uppercase tracking-wider text-warn">
            <FlaskConical className="size-3.5" aria-hidden /> Synthetic environment
          </p>
          <p className="mt-1.5 text-[12px] leading-relaxed text-fg-muted">
            All agents, citizens, accounts and documents are fictional. No real government or banking system is connected.
          </p>
        </div>
        <div className="border-t border-line px-5 py-4">
          <ApiStatus />
        </div>
      </aside>

      <div className="flex min-w-0 flex-1 flex-col">
        <header className="sticky top-0 z-20 flex h-14 items-center justify-between gap-4 border-b border-line bg-ink-900/80 px-5 backdrop-blur-md lg:px-8">
          <div className="flex min-w-0 items-center gap-3">
            <div className="flex items-center gap-2 lg:hidden">
              <ShieldCheck className="size-5 text-trust" aria-hidden />
              <span className="font-semibold tracking-wider">WAKALA</span>
            </div>
            <nav className="hidden items-center gap-2 text-[13px] text-fg-subtle sm:flex" aria-label="Breadcrumb">
              <span>WAKALA Console</span>
              <span aria-hidden>/</span>
              <span className="text-fg">{current?.label}</span>
            </nav>
          </div>
          <div className="flex items-center gap-3">
            <PhaseIndicator />
            <span className="lg:hidden">
              <ApiStatus />
            </span>
          </div>
        </header>

        {/* Mobile / narrow navigation */}
        <nav className="flex gap-1 overflow-x-auto border-b border-line px-3 py-2 lg:hidden" aria-label="Main (compact)">
          {NAV_ITEMS.map(({ path, label, icon: Icon }) => (
            <NavLink
              key={path}
              to={path}
              end={path === "/"}
              className={({ isActive }) =>
                clsx(
                  "flex shrink-0 items-center gap-1.5 rounded-md px-2.5 py-1.5 text-[13px]",
                  isActive ? "bg-ink-750 text-fg" : "text-fg-muted",
                )
              }
            >
              <Icon className="size-4" aria-hidden /> {label}
            </NavLink>
          ))}
        </nav>

        <main className="mx-auto w-full max-w-[1480px] flex-1 px-5 py-8 lg:px-10 lg:py-10">
          <Outlet />
        </main>
        <footer className="border-t border-line px-5 py-4 text-[12px] text-fg-subtle lg:px-10">
          WAKALA prototype · UAE Hackathon 2026 · Challenge #27 — Secure Agentic AI for Government Services. Conceptual
          “digital power of attorney” model; mandates are technical authorization artefacts, not legal instruments.
        </footer>
      </div>
    </div>
  );
}
