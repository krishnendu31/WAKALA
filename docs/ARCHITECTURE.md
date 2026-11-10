# WAKALA Architecture (Phase 4)

> Development prototype on synthetic data. Not production-ready and not government-certified.

## Component boundaries

| Component | Location | Trust | Status |
|---|---|---|---|
| AI agents (Residency, Insurance, Payment) | external runtime; simulated by `app/devtools/agent_client.py` | **Untrusted** | signing simulated |
| Crypto primitives (canonical JSON, Ed25519, domain tags) | `app/core/crypto.py` | Trusted | ✅ Phase 1 |
| Request authentication | `app/core/identity/authentication.py` | Trusted | ✅ Phase 1 |
| Mandate verification (signature, issuer trust, authority, lifecycle) | `app/core/mandates/verification.py` | Trusted | ✅ Phase 1 |
| Policy engine (pure, 8 checks, default-deny) | `app/core/authorization/engine.py` | Trusted | ✅ Phase 1 |
| Gateway and execution boundary | `app/core/execution/gateway.py` | Trusted | ✅ Phase 1 |
| Trusted tool registry | `app/core/execution/tools.py` | Trusted | ✅ Phase 1 |
| Replay guard | `app/core/replay.py` | Trusted | ✅ Phase 1 |
| Audit sink and hash chain | `app/core/audit/` | Trusted, append-only | ✅ Phase 1 |
| Public key, issuer and mandate stores | `app/services/repository.py`, `mandate_store.py` (SQLite) | Trusted storage | ✅ Phase 1 |
| Development keystore, issuance, CLI, demo scenarios | `app/devtools/` | **Dev only** | ✅ Phase 1 |
| Case store and state machine | `app/services/cases.py`, `schemas/case.py` | Trusted | ✅ Phase 2 |
| Protected services (residency, insurance, payment and ledger) | `app/services/government.py` | Protected; reachable only as registry handlers | ✅ Phase 2 |
| Agent adapter interface and transports | `app/agents/interface.py` | Untrusted caller side | ✅ Phase 2 |
| Simulated agents (deterministic scripts) | `app/agents/simulated.py` | Untrusted | ✅ Phase 2 |
| LLM tool-use adapter (interface only) | `app/agents/llm.py` | Untrusted | ⏳ Phase 3 |
| Case intake, scenarios A–D, officer CLI actions | `app/workflow/` | Dev orchestration | ✅ Phase 2 |
| Weak RBAC baseline (test-only, isolated) | `app/workflow/baseline.py` | Not a WAKALA component | ✅ Phase 2 |
| Task catalogue + chain verifier (pure) | `app/core/delegation/tasks.py`, `chain.py` | Trusted | ✅ Phase 3 |
| Delegation service (child mandate issuance) | `app/services/delegation.py` | Trusted; registry handler only | ✅ Phase 3 |
| Revocation (mandate, case, agent; cascading, persistent) | `app/services/revocation.py` | Trusted (officer/CLI) | ✅ Phase 3 |
| Outcome reconciliation | `app/services/reconciliation.py` | Trusted | ✅ Phase 3 |
| Authority graph (read model) | `app/workflow/authority_graph.py` | Read-only | ✅ Phase 3 |

`app/core` never imports `app/devtools`, and a test enforces this. The enforcement path verifies with public keys only.

## Request path

```
Agent runtime (holds its own private key)
  │  ActionRequest {action_id, request_id, agent_id, mandate_id, tool_name, parameters,
  │                 target_resource, purpose, delegation_chain, timestamp, nonce}
  │  signature = Ed25519( "WAKALA-ACTION-REQUEST-v1\n" + canonical JSON(request) )
  ▼
POST /api/gateway/execute        (or /authorize for a policy query only)
  │ 1  strict Pydantic validation             → 422 on malformed input (no decision)
  │ 2  authenticate(): registered public key for the claimed agent_id, key_id match, signature verify
  │ 3  replay guard: record (agent_id, nonce), only if authenticated
  │ 4  load mandate by ID from the server-side store (agents never submit mandate bodies)
  │ 5  authorize(request, principal, mandate, PolicyContext)  — pure function, 8 checks
  │ 6  append hash-chained AuditEvent         → if this fails: 503, nothing executes
  │ 7  denied  → 403, handler never invoked
  │    allowed → ToolDispatcher: checks the grant's request digest, then calls the registry handler
  ▼
Protected tool (Phase 1: residency.read_status, insurance.verify_eligibility are executable;
                residency.prepare_renewal and payment.request_fee_payment are authorization-only)
```

### Why authorization and execution are separate concerns

- `authorize()` is a pure function. It is easy to test exhaustively, it does no I/O, and it uses no LLM.
- `Gateway.execute()` is the only code path that calls a tool. It runs authentication, authorization, audit and dispatch
  in a single call on a single immutable request object. The handler receives the parameters parsed from exactly that
  object, so they cannot change between check and use.
- `/authorize` never produces a reusable "allowed" token. It also consumes the nonce, so a request that was only
  queried cannot later be executed.
- The dispatcher refuses to run if the request digest differs from the authorized one (defence in depth), if the tool
  is unregistered, or if no grant exists.
- Tools are looked up by name in a fixed mapping built in code. No request field is ever treated as a function, module,
  path, URL or expression.

## Phase 2: case-bound protected workflow

```
Citizen application ──► case intake (front office, dev simulation)
                         • creates RenewalCase (CREATED, 2 h expiry)
                         • each issuer signs a mandate scoped to THIS case's citizen, request and resources
Simulated agent ──ToolCall──► SigningAgentAdapter ──SignedActionRequest{…, case_id}──► GatewayTransport
                                                                     │ in-process or HTTP
                                                                     ▼
                                    Gateway.execute(): checks 1–8, where check 6 now also verifies the case:
                                      case exists · same citizen and request as the mandate · agent assigned with
                                      this mandate · operation authorized by the case · purpose (service) matches ·
                                      state permits the tool · case not expired
                                                                     │ ALLOW only
                                                                     ▼
                                    ToolDispatcher → ProtectedServices handler(params, ExecutionContext)
                                      • re-checks the case inside ONE DB transaction (compare-and-swap on version)
                                      • mutates service storage + case state, or raises ServiceRefusal → full rollback
                                    audit: decision event (before) + execution event (after, result digest only)
```

| Case state | Operation permitted (policy) | Effect (service) |
|---|---|---|
| CREATED | `residency.register_renewal_case` | → VERIFYING |
| VERIFYING | `residency.check_eligibility`, `insurance.verify_case_eligibility` | Each records a prerequisite; both together → AWAITING_PAYMENT. Ineligible → FAILED |
| AWAITING_PAYMENT | `payment.collect_renewal_fee` | Ledger row, `fee_paid` → READY_TO_COMPLETE |
| READY_TO_COMPLETE | `payment.collect_renewal_fee` (idempotent retry only), `residency.complete_renewal` | Renewal record → COMPLETED |
| PAUSED_FOR_REVIEW, FAILED, COMPLETED | none | — |

Invalid transitions raise `InvalidTransition` (pure `next_case`). Prerequisite guards make AWAITING_PAYMENT,
READY_TO_COMPLETE and COMPLETED unreachable without the required steps.

Each case-bound tool call carries a server-built `ExecutionContext` (agent, request, case, decision ID, audit reference
and time). The agent cannot supply it, and the dispatcher refuses case tools without it.

### Agent adapters

`AgentAdapter` is the integration point for any framework:

1. The adapter turns a `ToolCall` (tool, parameters, target, purpose) into a request signed with the agent's own key.
2. It submits the request through a `GatewayTransport`:
   - `InProcessGatewayTransport` calls the gateway directly, in-process.
   - `HttpGatewayTransport` POSTs to `/api/gateway/execute`, so external runtimes in any language receive identical
     enforcement (tested).
3. `export_tool_definitions()` exports the case-bound tools as JSON-schema tool definitions for future LLM tool-use
   adapters. `LLMToolUseAdapter` is an interface only; Phase 2 agents are deterministic scripts.

### Weak baseline isolation

`WeakRoleBaseline` is intentionally weak and test-only:
- It performs a role-only check.
- It keeps its own in-memory copy of the fixtures.
- It never touches WAKALA's database, gateway, services, mandates or audit trail (tested).
- It exists only to contrast with WAKALA on the same wrong-citizen request.

## Phase 3: mandate chains (signed, non-expanding delegation)

```
Residency Agent ──signed SignedActionRequest{tool: delegation.commission_task,
                                             params: {case, citizen, task, receiver, requested_operations}}──► Gateway.execute()
   checks 1–4: identity, agent, ROOT mandate signature/issuer authority, validity
   check 5   : task ∈ mandate.commissionable_tasks  (commission authority ≠ allowed_tools)
   check 6   : case binding (same case, citizen, request; root assigned to case; case not revoked; state VERIFYING)
   check 7   : task in trusted catalogue · receiver permitted for task · requested ops ⊆ task ops ·
               depth + 1 ≤ max · receiver not already in the chain (no cycles)
   check 8   : freshness, nonce
        │ ALLOW
        ▼
DelegationService.commission() — one SQLite transaction:
   re-load parent + case → build child = parent ∩ task catalogue ∩ receiving-entity authority →
   check_non_expansion(child, parent) → sign with ISS-WAKALA-DELEGATION key →
   insert mandate + trusted delegation record + case event + outcome audit event   (all or nothing)

Insurance Agent ──signed request{mandate_id: child}──► Gateway.execute()
   gateway resolves child → parent → root from the SERVER-SIDE mandate store (bounded, cycle-safe);
   check 3 runs verify_chain(): every ancestor authentic, trusted, unrevoked and unexpired; every link narrows;
   root issued by a government issuer; children only by the delegation-only issuer
   check 6: root mandate is the case's mandate for the delegating agent; child.case_id == request case
```

**Four separate authority layers**, all of which must agree:

| Layer | Where | Example |
|---|---|---|
| 1 · Direct execution | `allowed_tools` / `denied_tools` | The Residency Agent may *not* call `insurance.verify_case_eligibility` (explicitly denied) |
| 2 · Commission authority | `commissionable_tasks`, `max_delegation_depth` (granted only within the issuer's `IssuerAuthority`) | The Residency Agent *may* commission `insurance_eligibility_check`, depth 1 |
| 3 · Case authorization | `RenewalCase.authorized_operations`, `assigned_agents`, `mandate_refs`, `authority_revoked` | The case allows the insurance check and names the Residency root mandate |
| 4 · Receiving entity policy | `TASK_CATALOG[task].receiving_issuer` → that issuer's declared authority | `ISS-INSURANCE-REG` must itself authorize `AGT-INS-001` for the operation |

The child's effective authority is the **intersection** of all four. It is never what the receiving agent "normally"
holds. The delegation issuer's own `IssuerAuthority` is only an outer bound.

**Trusted task catalogue** (`app/core/delegation/tasks.py`, immutable): task → permitted operations, permitted
receivers, receiving entity, resource template (instantiated with the case's citizen or case ID), maximum lifetime and
whether the task is monetary.

**Revocation.**
- `revoke_mandate` (default: cascade through delegation records) and `revoke_case_authority` (case flag plus every root
  and descendant) are persistent in SQLite.
- The chain verifier also rejects any child whose ancestor is revoked, even without the cascade record.
- Agent-wide revocation is separate (`revoke_agent`, a persistent status override re-applied after the registry
  reseed).
- No denial ever triggers revocation automatically.

**Signature compatibility.** The Phase 3 mandate fields (`case_id`, `root_mandate_id`, `delegation_depth`,
`delegated_by_agent`, `delegated_task`, `commissionable_tasks`, `max_delegation_depth`) are signed when set and
omitted from the canonical bytes when they hold their defaults. Every earlier signature therefore stays byte-identical
(tested).

## Audit consistency (Phase 3 repair)

| Record | Written | Atomicity |
|---|---|---|
| Decision event (authorization) | Before execution, own transaction | If it fails → nothing runs (503 `AUDIT_UNAVAILABLE`) |
| Outcome event (execution) for protected services | **Inside the service's own transaction** via `ExecutionContext.record_outcome(conn, result)` → `SqliteAuditSink.append_in(conn, …)` | Service change and outcome commit together or roll back together |
| Outcome of refused / failed / no-handler calls | After the (rolled-back) attempt, own transaction | Nothing was committed, so nothing can be inconsistent |
| Reconciliation event | `reconcile_outcomes()` at startup and via CLI | Idempotent; one per uncovered decision |

The hash chain is unchanged: `append_in` computes `sequence` and `previous_event_hash` inside the caller's transaction.
The single database lock serialises it with every other append.

If the outcome write fails, the service transaction rolls back. The API returns 503
`OUTCOME_NOT_RECORDED_ROLLED_BACK` ("nothing changed"), which is true by construction. A best-effort
`rolled_back_outcome_not_recorded` event is attempted. If that also fails, reconciliation later records
`authorized_not_executed` after confirming no service effect carries the decision ID.

A handler that cannot share the transaction (none exist today) would get 503 `OUTCOME_NOT_RECORDED` ("committed").
Reconciliation would then record `committed_outcome_reconstructed` from the service-side evidence. A committed
operation is never reported as rolled back.

## Phase 4: continuous assurance, intervention and recovery

```
signed request ─▶ Gateway._decide ─▶ decision audited ─▶ observers (AssuranceService.observe)
                       │                                      │
                       │ approval_gate (contain case,         ├─ EventFacts from the audited event
                       │ active incident, sensitive op)       ├─ evaluate_rules (deterministic, windowed)
                       ▼                                      ├─ IncidentStore (dedupe rule|subject|case, CAS)
              ESCALATE_HUMAN_REVIEW + PendingApproval         └─ plan_response → _apply (policy: monitor|contain)
                       │                                              ├─ SuspensionStore (reversible)
           officer approve ─▶ Gateway.execute_approved                ├─ pause case (PAUSED_FOR_REVIEW)
                       │   CAS pending→executing                      └─ assurance.* audit events
                       ▼
              full re-authorization (all checks except freshness/replay) ─▶ dispatch or approved_denied
```

| Module | Role |
|---|---|
| `core/assurance/rules.py` | `DEFAULT_RULES` (explicit thresholds/windows/severities), `EventFacts`, `evaluate_rules` — pure |
| `core/assurance/response.py` | `plan_response(finding)` → ordered `ResponseRecord`s with `RESP_*` reason codes — pure, never agent-wide |
| `services/assurance.py` | Observer; incidents, suspensions, case pause, approval gate |
| `services/approvals.py` | `PendingApproval` store (signed request stored verbatim, 30 min TTL, CAS transitions, expiry at startup) |
| `services/officers.py` | Dev officer credentials (scrypt), sessions (SHA-256 token hashes, 15 min idle / 60 min absolute), lockout, roles |
| `services/interventions.py` | Every officer action: permission + entity scope check, state change, `officer.*` audit event |
| `api/officer.py` | `/api/officer/*`, bearer session, strict bodies (no identity fields accepted) |
| `workflow/recovery.py` | Scenario H setup and `continue_case` (advances only by signed agent requests) |
| `workflow/oversight.py` | Isolated A/B oversight comparison |

**Observers never decide.** They run after the decision is audited; their failures are logged and cannot alter
or block the decision already made. Containment applies only to later requests.

**Suspension vs revocation.** Suspension (`mandate_suspensions`) is reversible and is enforced in
`check_mandate_lifecycle` and `verify_chain` (`DENY_MANDATE_SUSPENDED`, `DENY_PARENT_MANDATE_SUSPENDED`). Revocation
remains permanent and cascades; a revoked mandate cannot be reinstated.

**Recovery is authority change, not state change.** Officers can reassign a catalogued task to another eligible
receiver (`case.task_assignments`), resume a paused case and decide approvals. The case only advances when an agent
sends a signed request the gateway allows. The engine denies a delegated mandate whose task was reassigned away from
its holder, and the commission receiver must match the current assignment.

**Standby agents** (`standby_agents` table, `AGT-INS-002`) are registered and provisioned with keys, but sit outside
the primary roster and are not default receivers; they act only after officer reassignment.

**Restart.** Incidents, suspensions, approvals, officer sessions and assignments are in SQLite. On startup pending
approvals past their TTL are expired; an approval never executes because the process came back.

## Why protected services must not trust agent instructions

An agent's output is shaped by everything it reads, including attacker-controlled documents (fixture
`DOC-C1001-INJECTED`). A manipulated agent will sincerely request harmful actions. Authority therefore comes only from
artefacts the agent cannot forge or widen:

- its own private-key signature, which proves who is asking, and
- an issuer-signed mandate, which proves what that agent may do.

The gateway evaluates both on every action.

**Enforcement boundary limit.** In this prototype the boundary is a software convention inside one process. It does
not stop an agent that has direct credentials or network access to a real backend. In production, each protected
service must itself either:

- require a gateway-issued, action-bound authorization (for example mutual TLS plus a short-lived signed token covering
  the request digest), or
- be network-isolated so that only the gateway can reach it.

Phase 2 services follow this rule:
- They are reached only as registry handlers via `Gateway.execute()`.
- There is no HTTP route to them (a test checks the route table).
- They re-validate the case inside their own transaction.

This is still an in-process software boundary. Code running inside the backend process could import
`ProtectedServices` directly. A real deployment must put each service behind its own network boundary and have it
verify a gateway-issued, action-bound authorization itself.

## Data stores (SQLite)

| Table | Content |
|---|---|
| `agents`, `citizens`, `services`, `documents`, `scenarios`, `issuers` | Synthetic registry, reseeded at server start |
| `public_keys` | Ed25519 **public** keys and fingerprints for agents and issuers |
| `mandates` | Signed mandate JSON plus server-side revocation state |
| `request_nonces` | `(agent_id, nonce)` with expiry for replay protection |
| `renewal_cases` | Case JSON with `version` for compare-and-swap updates |
| `payment_ledger` | Synthetic transactions (`case_id` and `idempotency_key` UNIQUE) |
| `residency_renewals` | Completed synthetic renewals |
| `delegations` | Trusted parent → child records (case, agents, task, depth, decision event) |
| `agent_status_overrides` | Persistent agent-wide revocations, re-applied after reseed |
| `audit_events` | Append-only, hash-chained decision, execution, revocation and reconciliation log |
| `standby_agents` | Registered standby agents (officer reassignment only) |
| `mandate_suspensions` | Reversible suspensions (who, why, incident, lifted) |
| `incidents` | Rule findings with dedupe key, severity, status, responses, officer notes, `version` for CAS |
| `pending_approvals` | Held signed requests, status, TTL, decision and re-authorization result |
| `officers`, `officer_credentials`, `officer_sessions`, `officer_login_failures` | Dev officer identity, scrypt hashes, hashed session tokens, lockout |

The default database is `backend/var/wakala.db`, which is git-ignored and shared by the server and the CLI. Tests use
`:memory:`.

## Startup provisioning (development)

1. Load and validate the synthetic dataset. Startup fails on duplicates, dangling references, or issuer authority that
   points at unknown agents, services or tools.
2. For each agent and issuer key ID, load or generate an Ed25519 key in `backend/.dev_keys/` (git-ignored, file mode
   0600), and register only the public key.
3. Issue a fresh signed mandate for any agent that lacks a currently valid one.

`WAKALA_ENV=production` refuses to start. The prototype has no production key management.
