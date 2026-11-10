import { lazy, Suspense } from "react";
import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import { AppLayout } from "@/layouts/AppLayout";
import { CommandCenter } from "@/pages/CommandCenter";
import { AgentRegistry } from "@/pages/AgentRegistry";
import { GovernmentWorkflow } from "@/pages/GovernmentWorkflow";
import { SecurityOperations } from "@/pages/SecurityOperations";
import { SecurityEvidence } from "@/pages/SecurityEvidence";
import { DocumentShield } from "@/pages/DocumentShield";
import { GovernmentPortal } from "@/pages/GovernmentPortal";
import { AttackLab } from "@/pages/AttackLab";
import { ShadowMode } from "@/pages/ShadowMode";
import { PolicyDrafting } from "@/pages/PolicyDrafting";
import { DigitalMandates } from "@/pages/DigitalMandates";
import { SecurityEvents } from "@/pages/SecurityEvents";
import { CitizenTransparency } from "@/pages/CitizenTransparency";
import { SimulationLab } from "@/pages/SimulationLab";
import { Welcome } from "@/pages/Welcome";
import { GuidedDemo } from "@/pages/GuidedDemo";

// React Flow is only needed on one page; load it on demand.
const DelegationNetwork = lazy(() => import("@/pages/DelegationNetwork"));

export function App() {
  return (
    <BrowserRouter>
      <Routes>
        {/* First-time visitors: welcome page and a focused guided demo, without console navigation. */}
        <Route index element={<Welcome />} />
        <Route path="demo" element={<GuidedDemo />} />
        <Route element={<AppLayout />}>
          <Route path="command-center" element={<CommandCenter />} />
          <Route path="portal" element={<GovernmentPortal />} />
          <Route path="attack-lab" element={<AttackLab />} />
          <Route path="shadow" element={<ShadowMode />} />
          <Route path="policies" element={<PolicyDrafting />} />
          <Route path="soc" element={<SecurityOperations />} />
          <Route path="evidence" element={<SecurityEvidence />} />
          <Route path="documents" element={<DocumentShield />} />
          <Route path="workflow" element={<GovernmentWorkflow />} />
          <Route path="agents" element={<AgentRegistry />} />
          <Route path="mandates" element={<DigitalMandates />} />
          <Route
            path="delegation"
            element={
              <Suspense fallback={<p className="text-sm text-fg-subtle">Loading graph…</p>}>
                <DelegationNetwork />
              </Suspense>
            }
          />
          <Route path="events" element={<SecurityEvents />} />
          <Route path="transparency" element={<CitizenTransparency />} />
          <Route path="simulation" element={<SimulationLab />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Route>
      </Routes>
    </BrowserRouter>
  );
}
