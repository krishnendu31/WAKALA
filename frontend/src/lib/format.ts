import type { AgentStatus, Money, RiskLevel } from "@/types/api";

export function formatMoney(m: Money): string {
  const n = Number(m.amount);
  return `${m.currency} ${n.toLocaleString("en-AE", { minimumFractionDigits: 0, maximumFractionDigits: 2 })}`;
}

export function formatDate(iso: string | null): string {
  if (!iso) return "—";
  const d = new Date(`${iso}T00:00:00Z`);
  return d.toLocaleDateString("en-GB", { day: "2-digit", month: "short", year: "numeric", timeZone: "UTC" });
}

export function humanize(value: string): string {
  return value.replace(/_/g, " ").replace(/^\w/, (c) => c.toUpperCase());
}

export type Tone = "trust" | "warn" | "deny" | "plan" | "neutral";

export const riskTone: Record<RiskLevel, Tone> = { low: "trust", medium: "plan", high: "warn", critical: "deny" };
export const agentStatusTone: Record<AgentStatus, Tone> = {
  active: "trust",
  pending_review: "warn",
  suspended: "warn",
  revoked: "deny",
};
