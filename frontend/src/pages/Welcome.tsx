import { ArrowRight, FlaskConical, LayoutDashboard, ShieldCheck, ShieldX, UserCog, type LucideIcon } from "lucide-react";
import { useEffect } from "react";
import { Link } from "react-router-dom";
import { BrandMark } from "@/layouts/AppLayout";

const STORY: { icon: LucideIcon; tone: string; title: string; text: string }[] = [
  { icon: ShieldCheck, tone: "text-trust bg-trust-soft", title: "A citizen's request is handled by AI agents",
    text: "Mariam asks to renew her residency permit. Three AI agents do the work. WAKALA checks every action before it runs." },
  { icon: ShieldX, tone: "text-deny bg-deny-soft", title: "One agent tries something it is not allowed to do",
    text: "The Insurance Agent asks for a different citizen's record. WAKALA blocks it before anything is executed." },
  { icon: UserCog, tone: "text-navy bg-navy-soft", title: "A security officer fixes it, and the service finishes",
    text: "An officer signs in, replaces the agent and approves the next step. Mariam's renewal completes. Other citizens are not affected." },
];

/** First screen for a first-time visitor: what WAKALA is, what they will see, and what to click. */
export function Welcome() {
  useEffect(() => { document.title = "WAKALA | وكالة — Welcome"; }, []);
  return (
    <div className="min-h-screen bg-ink-900">
      <header className="border-b border-line bg-ink-850">
        <div className="mx-auto flex max-w-[1180px] items-center justify-between px-6 py-4">
          <div className="flex items-center gap-3">
            <BrandMark />
            <p className="flex items-baseline gap-2 text-[18px] font-semibold tracking-[0.08em] text-navy">
              WAKALA <span className="text-line-strong">|</span><span lang="ar" className="tracking-normal text-gold">وكالة</span>
            </p>
          </div>
          <span className="inline-flex items-center gap-1.5 rounded-full border border-gold/35 bg-gold-soft px-3 py-1 text-[12px] font-medium uppercase tracking-wider text-gold-strong">
            <FlaskConical className="size-3.5" aria-hidden /> Fictional citizens · synthetic services
          </span>
        </div>
      </header>

      <main className="mx-auto max-w-[1180px] px-6 pb-12 pt-12">
        <p className="eyebrow mb-3">Secure AI agents for government services</p>
        <h1 className="max-w-[900px] text-[38px] font-semibold leading-[1.15] tracking-tight text-navy">
          WAKALA protects government AI agents by verifying what each agent is allowed to do before sensitive actions execute.
        </h1>
        <p className="mt-4 max-w-[780px] text-[18px] leading-relaxed text-fg-muted">
          In this demonstration you will follow one government service from start to finish, see an unauthorized action stopped,
          and watch a security officer bring the service back safely.
        </p>

        <div className="mt-8 flex flex-wrap items-center gap-3">
          <Link to="/demo" className="inline-flex items-center gap-2 rounded-xl bg-trust px-6 py-3.5 text-[17px] font-semibold text-ink-950 shadow-[var(--shadow-card)] hover:bg-trust-strong">
            Start Guided Demo <ArrowRight className="size-5" aria-hidden />
          </Link>
          <Link to="/command-center" className="inline-flex items-center gap-2 rounded-xl border border-line-strong bg-ink-850 px-5 py-3.5 text-[16px] font-medium text-navy hover:bg-ink-800">
            <LayoutDashboard className="size-5" aria-hidden /> Explore Security Console
          </Link>
        </div>
        <p className="mt-3 text-[14px] text-fg-subtle">About 4 minutes. The officer step needs a demo officer password, issued by the person running the demo.</p>

        <h2 className="mt-12 text-[15px] font-semibold uppercase tracking-[0.12em] text-fg-subtle">What you will see</h2>
        <ol className="mt-4 grid gap-4 md:grid-cols-3">
          {STORY.map((s, i) => (
            <li key={s.title} className="card p-5">
              <div className="flex items-center gap-3">
                <span className={`flex size-10 items-center justify-center rounded-full ${s.tone}`}><s.icon className="size-5" aria-hidden /></span>
                <span className="text-[13px] font-semibold text-fg-subtle">Step {i + 1}</span>
              </div>
              <p className="mt-3 text-[17px] font-semibold text-fg">{s.title}</p>
              <p className="mt-1.5 text-[15px] leading-relaxed text-fg-muted">{s.text}</p>
            </li>
          ))}
        </ol>

        <div className="mt-8 rounded-xl border border-gold/30 bg-gold-soft p-4 text-[14.5px] leading-relaxed text-fg">
          <b>Everything here is fictional.</b> Citizens, agencies, payments and documents are synthetic. No real government or banking
          system is connected. Each result on screen comes from the running WAKALA prototype, not from a script of expected answers.
        </div>
      </main>
    </div>
  );
}
