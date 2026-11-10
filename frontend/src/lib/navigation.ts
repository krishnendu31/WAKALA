import { Activity, BarChart3, Bot, FileSearch, FileSignature, FlaskConical, Landmark, LayoutDashboard, Network, ReceiptText, ShieldAlert, type LucideIcon } from "lucide-react";

export interface NavItem {
  path: string;
  label: string;
  labelAr: string;
  icon: LucideIcon;
}

export const NAV_ITEMS: NavItem[] = [
  { path: "/", label: "Command Center", labelAr: "مركز القيادة", icon: LayoutDashboard },
  { path: "/soc", label: "Security Operations", labelAr: "العمليات الأمنية", icon: ShieldAlert },
  { path: "/evidence", label: "Security Evidence", labelAr: "الأدلة الأمنية", icon: BarChart3 },
  { path: "/documents", label: "Document Shield", labelAr: "درع المستندات", icon: FileSearch },
  { path: "/workflow", label: "Government Workflow", labelAr: "سير العمل الحكومي", icon: Landmark },
  { path: "/agents", label: "Agent Registry", labelAr: "سجل الوكلاء", icon: Bot },
  { path: "/mandates", label: "Digital Mandates", labelAr: "التفويضات الرقمية", icon: FileSignature },
  { path: "/delegation", label: "Delegation Network", labelAr: "شبكة التفويض", icon: Network },
  { path: "/events", label: "Security Events", labelAr: "الأحداث الأمنية", icon: Activity },
  { path: "/transparency", label: "Citizen Transparency", labelAr: "الشفافية للمتعاملين", icon: ReceiptText },
  { path: "/simulation", label: "Simulation Lab", labelAr: "مختبر المحاكاة", icon: FlaskConical },
];
