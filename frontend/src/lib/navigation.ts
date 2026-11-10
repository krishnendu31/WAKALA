import { Activity, BarChart3, Bot, Building2, Eye, FilePen, Swords, FileSearch, FileSignature, FlaskConical, Landmark, LayoutDashboard, Network, ReceiptText, ShieldAlert, type LucideIcon } from "lucide-react";

export interface NavItem {
  path: string;
  label: string;
  labelAr: string;
  icon: LucideIcon;
  section: "demo" | "platform";
}

/** First five: the presentation order for the end-to-end demonstration. The rest stay fully functional. */
export const NAV_ITEMS: NavItem[] = [
  { path: "/portal", label: "Government AI Portal", labelAr: "بوابة الخدمات الذكية", icon: Building2, section: "demo" },
  { path: "/attack-lab", label: "Attack Lab", labelAr: "مختبر الهجمات", icon: Swords, section: "demo" },
  { path: "/soc", label: "Security Operations", labelAr: "العمليات الأمنية", icon: ShieldAlert, section: "demo" },
  { path: "/delegation", label: "Delegation Network", labelAr: "شبكة التفويض", icon: Network, section: "demo" },
  { path: "/documents", label: "Document Shield", labelAr: "درع المستندات", icon: FileSearch, section: "demo" },
  { path: "/evidence", label: "Security Evidence", labelAr: "الأدلة الأمنية", icon: BarChart3, section: "demo" },
  { path: "/shadow", label: "Shadow Mode", labelAr: "وضع المراقبة", icon: Eye, section: "demo" },
  { path: "/policies", label: "Policy Drafting", labelAr: "صياغة السياسات", icon: FilePen, section: "demo" },
  { path: "/", label: "Command Center", labelAr: "مركز القيادة", icon: LayoutDashboard, section: "platform" },
  { path: "/workflow", label: "Government Workflow", labelAr: "سير العمل الحكومي", icon: Landmark, section: "platform" },
  { path: "/agents", label: "Agent Registry", labelAr: "سجل الوكلاء", icon: Bot, section: "platform" },
  { path: "/mandates", label: "Digital Mandates", labelAr: "التفويضات الرقمية", icon: FileSignature, section: "platform" },
  { path: "/events", label: "Security Events", labelAr: "الأحداث الأمنية", icon: Activity, section: "platform" },
  { path: "/transparency", label: "Citizen Transparency", labelAr: "الشفافية للمتعاملين", icon: ReceiptText, section: "platform" },
  { path: "/simulation", label: "Simulation Lab", labelAr: "مختبر المحاكاة", icon: FlaskConical, section: "platform" },
];
