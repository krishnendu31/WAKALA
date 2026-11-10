# WAKALA Architecture (Phase 2)

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
| Delegation validator | `app/core/delegation/` | Trusted | ⏳ Phase 3 |

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
| `audit_events` | Append-only, hash-chained decision and execution log |

The default database is `backend/var/wakala.db`, which is git-ignored and shared by the server and the CLI. Tests use
`:memory:`.

## Startup provisioning (development)

1. Load and validate the synthetic dataset. Startup fails on duplicates, dangling references, or issuer authority that
   points at unknown agents, services or tools.
2. For each agent and issuer key ID, load or generate an Ed25519 key in `backend/.dev_keys/` (git-ignored, file mode
   0600), and register only the public key.
3. Issue a fresh signed mandate for any agent that lacks a currently valid one.

`WAKALA_ENV=production` refuses to start. The prototype has no production key management.
