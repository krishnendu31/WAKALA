# Phase 6 — Behaviour Watch 2.0, Attack Lab, Case View, My AI Activity, Shadow Mode, Policy Drafting, Precise Revocation

All features run on synthetic data in a single-process development prototype. Nothing here is a production UAE government
system, and nothing connects to real services or payment providers.

The judges' five questions and where each is answered:

| Question | Where |
|---|---|
| **Who** is the AI agent? | Case View (agent lanes, identities), Attack Lab (actor), receipt (agents) |
| **What** was it authorized to do? | Case View (allowed tools, case-bound scope), Attack Lab ("original authority") |
| **Who delegated** its authority? | Case View (child mandate → parent, verified chain) |
| **Why** was an operation allowed, blocked or escalated? | Plain sentence everywhere; reason codes in technical details |
| **How** did the service safely continue? | Security Operations recovery, Case View "recovered", receipt "after review" |

## M1 — Behaviour Watch 2.0 and the recovery regression

**Root cause of the Phase 5 shared-environment failure (2/20).** Two agent-wide counters attached their incidents to
whichever case the agent had touched last:
1. REQUEST_RATE counted an agent's requests across all cases.
2. REPEATED_DENIALS counted an agent's denials across all cases.

On `contain` cases, an active incident gates sensitive operations behind approval. So brand-new legitimate cases
inherited incidents caused by unrelated activity.

**Fix (smallest justified):**
- **REQUEST_RATE** now counts one agent's requests *within one case*. The threshold is unchanged at 30 per 60 s.
- **AGENT_REQUEST_VOLUME** is a new, separate agent-wide signal (60 per 60 s). It never contains a case. When the
  volume is spread over ≥5 cases with ≤10 % denials, it is recorded as OBSERVE ("legitimate batch").
- **REPEATED_DENIALS** spread over several cases becomes an agent-level **ALERT**. Inside one case, the Phase 5
  behaviour is unchanged.
- **ALERT never gates or contains.** Approval gating considers only incidents at REQUIRE_APPROVAL or above.

**New signals:**
- UNEXPECTED_DATA_CATEGORY: a tool outside the agent's declared service categories.
- OFF_SCHEDULE: configurable with `WAKALA_WATCH_HOURS`, e.g. `06:00-22:00` UAE time. A single event is OBSERVE; three
  off-hours denials raise an ALERT.
- EXPIRED_AUTHORITY_REUSE: one use is OBSERVE, three uses raise an ALERT.

The existing signals (cross-citizen access, delegation escalation, action after revocation, credential failures)
keep their Phase 4 behaviour.

**Intervention ladder:** NORMAL → OBSERVE → ALERT → REQUIRE_APPROVAL → SUSPEND_SPECIFIC_AUTHORITY → REVOKE.
- OBSERVE is a stored observation, never an incident.
- Every finding records: agent, case, signal, observed activity, expected pattern or threshold, concern, severity,
  level, action taken, and audit events.
- These are rule-based thresholds, **not AI threat prediction**. Monitoring never authorizes anything; the gateway
  decides independently.

**Before and after, on identical traffic** (`evidence/phase6/RECOVERY_REGRESSION.md`, generated from clean commit
`4440f91`):

| Policy | Shared back-to-back | Legit. denied | Legit. held unexpectedly | REQUEST_RATE incidents |
|---|---|---|---|---|
| phase5-original | **2/20** | 24 | 10 | 35 |
| watch-2.0 | **20/20** | 0 | 0 | 0 |

Independent incidents are 20/20 under both policies. One trade-off to note: under watch-2.0 the same attacking agent's
third cross-citizen attempt within 30 minutes escalates to critical. As a result, 18 of the 20 affected child mandates
were **revoked** rather than suspended. Recovery still completes through the standby agent.

Reproduce:

```bash
cd backend
.venv\Scripts\python -m app.evaluation.watch_regression
```

## M2 — Attack Lab (`/attack-lab`)

Each of the eight attacks (A–H) runs in **fresh isolated environments**:
- **WAKALA side:** the Phase 5 harness, configuration C, through the real `Gateway.execute()`.
- **Baseline side:** the Phase 5 role-only baseline, evaluating the same abstract request.
- **G (prompt-injection PDF):** uses Document Shield plus the simulated manipulated agent, a deterministic script with
  no LLM.

No authorization logic is duplicated.

Each run records:
- run ID, timestamps and seed fingerprint;
- executed / data returned / state modified, on both sides;
- exact reason codes and a plain sentence;
- Behaviour Watch signals;
- the isolated environment's audit events, copied into the run with the chain verification result.

**Results:**
- The baseline executed 7 of 8 attacks; WAKALA executed 0 of 8.
- **B (delegation escalation) is denied in both**: the role-only baseline's insurance role does not include
  delegation, and the lab shows that.
- C and E note that a baseline with nonce or signature checks would also stop them.

Dev-mode and local-client only. Reset starts a new lab session and deletes nothing.

## M3 — Case View (Delegation Network)

The Case View is the default view on the existing page. It reads:

citizen request → Residency Agent → delegated agent → protected services

It is built only from the verified stored mandate chain and the case's audit decisions. States shown: authorized,
denied, suspended, revoked, pending approval, recovered. Selecting an item shows a plain explanation, with a
technical-details panel. The full graph is still one click away.

## M4 — My AI Activity (portal)

A synthetic receipt for the selected case.

**Accuracy rules:**
- An action is "completed" only when the gateway allowed it **and** the protected service recorded an `executed`
  outcome.
- A blocked action is "blocked before it ran — no data returned".
- The headline sentence is generated from counted events, e.g. "3 government AI agents completed actions … every
  completed action was authorized for your case".

**Privacy filtering** removes:
- other citizens' references and names;
- officer identities;
- rule IDs and thresholds;
- incident intelligence;
- mandate, event and reason-code IDs (replaced with opaque `R-` references).

The portal still has **no citizen login** and remains a local/dev-only demonstration.

## M5 — Shadow Mode (`/shadow`)

`ShadowEvaluator` applies the gateway's own `authenticate()` and `authorize()` to **copies** of synthetic signed
requests, using read-only inputs. It is **not** a flag on `Gateway.execute()`. It has:
- no dispatcher and no protected-service calls;
- no audit writes;
- no shared nonce consumption (it keeps its own replay memory);
- no monitoring, approvals or containment.

Result on 11 copied events:
- 7 agree with the source system.
- 3 **would block** where the source system allowed. This is a counterfactual: nothing was prevented.
- 1 **false-denial candidate**: a legitimate completion 3 hours after the case opened hits the 2-hour mandate expiry.
  It is reported as a policy conflict, with the advice "do not simply disable expiry".
- The source state is byte-for-byte unchanged during observation.

The same event specifications are then **enforced in a separate fresh environment**. The shadow prediction matched
enforcement on **11/11** events, with the same reason codes.

## M6 — Policy Drafting (`/policies`) — draft-only

1. A **deterministic restricted template parser** (no AI model) produces the draft: agent role, action, citizen and
   case scope, limit, expiry, receiving service and approval level. Unrecognised wording is rejected.
2. Schema and conflict checks: the agent's service, case-bound scope, mandate lifetime, approval required for payments,
   and no silent replacement of an approved policy.
3. Approval requires an authenticated officer **of the entity that owns the receiving service**, with
   `policies.approve`. For insurance that is OFF-0202. The draft is re-validated at approval time.
4. The approved draft is signed with Ed25519 by that entity's issuer key, and can be verified afterwards. Tampering
   breaks verification.
5. Status `approved_signed_not_enforced`: **approved policies do not change live authorization.** Enforcing them
   (mapping fields onto mandate issuance and the policy engine) is not implemented.

## M7 — Precise revocation (Security Operations → Revocation)

Scopes, each reusing the existing services:
- **Single mandate.** Its children stay on record but fail chain verification on use.
- **Mandate plus dependent delegations.**
- **One citizen case** (`cases.revoke_authority`).
- **Agent identity:** reversible suspension (`agents.suspend`, supervisor only).

A read-only blast-radius preview runs before any change. Tested: revoking Mariam's case authority leaves Omar's case
completing normally.

**Version-scoped revocation is not offered.** Agent passports carry no deployment version that is cryptographically
bound to the identity key, so revoking "by version" would trust an agent-supplied string.

## Remaining limitations

- Single process, SQLite, development keys and passwords; the portal has no citizen authentication.
- Behaviour Watch is threshold-based. Thresholds are hand-set and the operating schedule is off by default (24/7).
  OBSERVE records are not yet summarised for officers beyond the list.
- Attack Lab baseline: it is deliberately weak and does not represent all real IAM systems.
- Approved policy drafts are not enforced.
- The optional model-driven agent has still not been run against a live model in this environment.
- Phase 5 benchmark evidence (`evidence/phase5`) was produced under the original monitoring policy and is preserved
  unchanged. Re-running the full security benchmark under watch-2.0 was not part of this phase; only the recovery
  benchmark was re-run.
