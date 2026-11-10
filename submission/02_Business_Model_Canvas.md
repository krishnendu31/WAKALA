<style>
@page { size: A4 landscape; margin: 10mm; }
.bmc { display: grid; grid-template-columns: repeat(10, 1fr); grid-auto-rows: auto; gap: 6px; font-size: 8.4pt; line-height: 1.32; }
.bmc > div { border: 1px solid #c9d3e0; border-radius: 6px; padding: 6px 8px; background: #fff; }
.bmc h3 { margin: 0 0 4px; font-size: 9.4pt; color: #12234a; border-bottom: 1.5px solid #0d9488; padding-bottom: 2px; }
.bmc ul { margin: 0 0 0 14px; } .bmc li { margin: 1px 0; }
.kp { grid-column: 1 / 3; grid-row: 1 / 3; } .ka { grid-column: 3 / 5; grid-row: 1; } .kr { grid-column: 3 / 5; grid-row: 2; }
.vp { grid-column: 5 / 7; grid-row: 1 / 3; background: #e6f6f4 !important; } .cr { grid-column: 7 / 9; grid-row: 1; } .ch { grid-column: 7 / 9; grid-row: 2; }
.cs { grid-column: 9 / 11; grid-row: 1 / 3; } .cost { grid-column: 1 / 6; grid-row: 3; } .rev { grid-column: 6 / 11; grid-row: 3; }
</style>

<div class="cover"><div class="eyebrow">UAE Hackathon 2026 · Challenge #27 · Proposed model</div><h1>Business Model Canvas <span class="ar">وكالة</span></h1><p>WAKALA — an independent authorization, monitoring and recovery layer for government AI agents. Every partner listed is a target. No partnership, customer or price has been agreed.</p></div>

<div class="bmc">
<div class="kp"><h3>Key partners (targets)</h3><ul>
<li>Central digital-government authority: shared-service channel and interoperability standards</li>
<li>National cybersecurity authority: alignment with national cyber guidance and incident coordination</li>
<li>Agent-platform and model providers: adapters so their agents sign requests</li>
<li>System integrators already serving government entities</li>
<li>In-country cloud and key-management / HSM providers</li>
<li>Independent security testers for third-party assurance</li></ul></div>
<div class="ka"><h3>Key activities</h3><ul>
<li>Operate and harden the gateway, mandate and delegation engine</li>
<li>Build service and platform adapters</li>
<li>Write mandate templates with service owners</li>
<li>Continuous red-teaming (Attack Lab corpus)</li>
<li>Officer training and recovery drills</li></ul></div>
<div class="kr"><h3>Key resources</h3><ul>
<li>Working prototype: gateway, signed mandates, delegation chains, Behaviour Watch, audit chain, Document Shield, Shadow Mode</li>
<li>493-test suite and reproducible evidence harness</li>
<li>Attack scenarios and synthetic benchmark dataset</li>
<li>Security engineering and government-service know-how</li></ul></div>
<div class="vp"><h3>Value propositions</h3><ul>
<li><b>Prove</b> every agent action was authorized: who acted, for which citizen and case, under whose mandate</li>
<li><b>Prevent</b> out-of-mandate actions before they run (synthetic benchmark: 0/720 unauthorized executed, 0/480 legitimate denied)</li>
<li><b>Stop one agent, not the service:</b> selective suspension, officer reassignment, safe recovery</li>
<li><b>Platform-neutral:</b> sits at the service API, so different agent vendors meet one standard</li>
<li><b>Safe adoption path:</b> Shadow Mode predicts the impact before anything is enforced</li>
<li>Plain-language AI-activity receipts for citizens</li></ul></div>
<div class="cr"><h3>Customer relationships</h3><ul>
<li>Pilot co-design with the service owner</li>
<li>Dedicated onboarding and mandate-template workshops</li>
<li>Shared incident and recovery playbooks with the entity's security team</li>
<li>Conformance testing for platform suppliers</li></ul></div>
<div class="ch"><h3>Channels</h3><ul>
<li>Challenge owner → a 90-day pilot</li>
<li>National shared-service and procurement frameworks</li>
<li>System-integrator partners</li>
<li>Direct sales to entities with agentic AI programmes</li></ul></div>
<div class="cs"><h3>Customer segments</h3><ul>
<li><b>Primary:</b> ministries and authorities deploying AI agents in citizen services (accountable service owners, CISOs, CDOs)</li>
<li><b>Central:</b> digital-government and cybersecurity authorities that need cross-entity assurance and evidence</li>
<li><b>Suppliers:</b> agent-platform vendors and integrators that must show equivalent protection</li>
<li><b>Later:</b> sector regulators for high-impact services</li></ul></div>
<div class="cost"><h3>Cost structure</h3><ul>
<li>Engineering: production hardening (HA, durable database, external audit anchoring)</li>
<li>In-country hosting, key management and HSM</li>
<li>Independent penetration testing and certification</li>
<li>Integration and support staff; officer training</li>
<li>Licence review: PyMuPDF is AGPL, so a commercial licence or replacement is needed before commercial use</li></ul></div>
<div class="rev"><h3>Revenue streams (proposed)</h3><ul>
<li><b>Entity licence (annual):</b> tiered by number of protected services and registered agents</li>
<li><b>Fixed-scope pilot fee:</b> 90-day pilot on one service</li>
<li><b>Supplier conformance kit:</b> test suite and evidence pack for agent-platform vendors</li>
<li><b>Integration and assurance services:</b> adapters, mandate templates, recovery drills</li>
<li><i>Price levels are not set. They will be validated with the pilot entity. No revenue or market-size figures are claimed.</i></li></ul></div>
</div>

<p class="footer">Figures cited come from evidence/phase5/summary.json (synthetic prototype benchmark, not production government statistics). WAKALA is a prototype and is not integrated with any government system.</p>
