<div class="cover"><div class="eyebrow">UAE Hackathon 2026 · Challenge #27 · Feasibility and planning</div><h1>90-day pilot roadmap <span class="ar">وكالة</span></h1><p>One government entity · one low-risk service · observe first, then enforce one case type, then decide on measured results.</p><span class="badge">Proposed plan · no pilot agreed yet</span></div>

## Pilot scope

- **One service:** a low-risk, high-volume service where AI agents prepare or carry out case steps (the prototype models a residency-permit renewal).
- **One entity:** a sponsor who is accountable for the service, a service owner, a small officer team and a security contact.
- **Out of scope:** payments to real accounts in the first 60 days, multi-entity delegation, and high-impact decisions such as eligibility determinations. WAKALA authorizes and records actions. It never decides eligibility.

## Prerequisites from the pilot entity (week 0)

| Need | Why |
|---|---|
| Sandbox environment with test data | The prototype uses synthetic data only. The pilot must not use live personal data until approved |
| Named sponsor, service owner, 2–4 officers, security contact | Mandates need an accountable owner. Interventions need authenticated officers |
| Entity identity provider and key management (KMS/HSM) | Replaces the prototype's development keys and CLI-issued officer passwords |
| Read access to the agent platform's tool calls (or an adapter point) | So each agent action reaches the gateway as a signed request |
| Data-protection and security approval for the sandbox | Pilot governance |

## Timeline

| Days | Phase | Activities | Milestone and exit evidence | Owner |
|---|---|---|---|---|
| 1–10 | Mobilise | Kick-off. Agent inventory for the service. Threat model with the security team. Agree success measures. | Signed scope, inventory, agreed KPI targets | Entity + WAKALA |
| 11–20 | Configure | Deploy in the entity sandbox. Connect the identity provider and key management. Write mandate templates with the service owner (tools, limits, expiry, approval rules). | Gateway running in the sandbox with entity keys | WAKALA |
| 21–30 | **Observe (Shadow Mode)** | Copied requests are evaluated by the gateway logic. Nothing is blocked and no state changes. | **Shadow report:** agreement rate, would-block events, false-denial candidates, policy conflicts | WAKALA → sponsor |
| 31–40 | Prepare to enforce | Fix the policy conflicts the shadow run found. Train officers on suspend, reassign, resume and approve. | Officers certified on the playbook | Entity officers |
| 41–55 | **Enforce one case type** | The gateway enforces on one case type in the sandbox. Officers approve sensitive steps. Tune Behaviour Watch thresholds on pilot traffic. | Weekly report: decisions, denials, holds, incidents | WAKALA + officers |
| 56–60 | Independent test | Third-party security test using the Attack Lab scenarios and the tester's own attacks | Test report; no unauthorized action executed | Independent tester |
| 61–75 | **Recover** | Delegation and selective-revocation drills. Timed recovery drills (incident → safe resume). Audit export to the entity security team. | Recovery-drill results with timings | Entity security + WAKALA |
| 76–85 | Citizen view | Usability test of the plain-language AI-activity receipt with test users | Usability findings | Service owner |
| 86–90 | **Decide** | Evaluation report against the agreed KPIs | **Go / no-go** decision by the sponsor | Sponsor |

## Success measures (targets to be agreed in days 1–10)

| Measure | Proposed target | How it is measured |
|---|---|---|
| Unauthorized actions executed | 0 | Gateway decisions reconciled with service records |
| Legitimate actions wrongly denied | Below a limit agreed with the service owner | Shadow report, then the enforcement log reviewed by officers |
| Added latency per authorized action | Agreed budget (prototype median ≈ 19 ms in memory and ≈ 55 ms with persisted SQLite on one laptop; must be re-measured) | Gateway timing logs |
| Incident → safe resume | Measured baseline, then improvement | Recovery drills |
| Audit completeness | 100 % of decisions in a verified audit chain | Chain verification and reconciliation |
| Officer effort | Recorded hours per week | Officer log |

## What changes from prototype to pilot

| Prototype today | Pilot change |
|---|---|
| Development signing keys in a git-ignored folder | Entity KMS/HSM |
| SQLite, single process | Managed database; single-region deployment is acceptable for one service |
| Officer passwords issued by the CLI | Entity identity provider (single sign-on) |
| Deterministic offline planner; no live model verified | Connect the entity's chosen agent platform through an adapter; run the real-model injection test |
| Hash chain without external anchoring | Periodic anchoring of the chain head to an external store |
| Policy drafts signed but not enforced | Keep draft-only in the pilot; enforcement needs a separate approval |

## Risks and mitigations

| Risk | Mitigation |
|---|---|
| False denials disrupt the service | Shadow Mode first; enforce on one case type only; officers can approve held steps |
| Agent platform cannot sign requests | Server-side adapter signs on the agent's behalf with a per-agent key (the prototype already does this) |
| Thresholds tuned on synthetic traffic misfire | Re-tune on shadow data. ALERT level never blocks |
| Officer availability | Exception-only review. Held steps wait safely and nothing executes |
| Scope creep | One service, one case type, fixed 90 days |
