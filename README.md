# WAKALA | وكالة

**WAKALA 2.0 — Verifiable authority, secure delegation and real-time control for government AI agents.**
*Autonomous AI. Accountable Actions.*

WAKALA is a security and authorization layer for government AI agents. It gives every agent a verifiable identity, grants
authority only through digitally signed, task-limited mandates, checks every sensitive action at an independent
checkpoint, keeps delegation from expanding authority, and records each decision in an audit trail that humans can review
and act on.

> An AI agent must never gain authority merely because it is operating inside a trusted government system.
> Every sensitive action must be independently authorized.

WAKALA is **not** a chatbot and **not** a prompt-injection classifier. It assumes agents can be manipulated, so it
enforces authority outside the agent, at the boundary of every protected tool.

| | |
|---|---|
| Competition | UAE Hackathon 2026 — Challenge #27, *Secure Agentic AI for Government Services* (UAE Cyber Security Council) |
| Status | **Phase 3: secure mandate chains.** Signed, non-expanding agent-to-agent delegation on top of Phase 2's protected services and Phase 1's security engine. Selective, persistent revocation. Transactional outcome audit. **Development prototype — not production-ready or certified. Agents are simulated; keys are development keys; single process.** |
| Data | **100% synthetic.** No real people, entities, accounts or government systems. |

The "digital power of attorney" framing is a conceptual analogy. WAKALA mandates are technical authorization artefacts and
are **not** legally recognised powers of attorney.

---

## Current capabilities (Phase 3)

`GET /api/system/capabilities` is the source of truth for this list, and the console renders it directly.

| Capability | Status |
|---|---|
| Synthetic government environment: 3 agents, 5 citizens, residency renewal service, 3 trusted issuers, 2 document fixtures | ✅ Phase 0 |
| Strict security contracts: `AgentPassport`, `DigitalMandate`, `TrustedIssuer`, `SignedActionRequest`, `AuthorizationDecision`, `AuditEvent` | ✅ Phase 0/1 |
| **Ed25519 agent identity.** Every request is signed over canonical bytes; an `agent_id` alone proves nothing | ✅ Phase 1 |
| **Freshness and replay protection.** ±60 s timestamp window and single-use nonces | ✅ Phase 1 |
| **Signed digital mandates.** Issuer-signed and verified on every use; tampering breaks the signature | ✅ Phase 1 |
| **Issuer trust and authority limits.** Only registered issuers, and only within their declared services, agents, tools, amount, recipients and lifetime | ✅ Phase 1 |
| **Default-deny policy engine.** A pure function with 8 checks, no LLM, and a denial on any error | ✅ Phase 1 |
| **Protected execution boundary.** `Gateway.execute()` dispatches only through a fixed server-side tool registry, bound to the authorized request digest | ✅ Phase 1 |
| **Hash-chained audit trail.** One event per decision and an integrity endpoint; an audit failure blocks execution | ✅ Phase 1 |
| Developer demonstration: 8 fixed server-side scenarios, off by default and loopback-only | ✅ Phase 1 |
| **Protected synthetic services**: Residency (register, eligibility, complete), Insurance (case-scoped eligibility), Payment (AED 500, treasury only, idempotent ledger). Reachable only through `Gateway.execute()` | ✅ Phase 2 |
| **Case-specific authority**: every protected call must match its signed case (citizen, request, assigned agent and mandate, operation, purpose, state, expiry) | ✅ Phase 2 |
| **Case lifecycle**: CREATED → VERIFYING → AWAITING_PAYMENT → READY_TO_COMPLETE → COMPLETED, plus PAUSED_FOR_REVIEW and FAILED, with prerequisite guards | ✅ Phase 2 |
| **Agent adapter interface**: signing adapter with in-process and HTTP transports; **simulated, deterministic** agents | ✅ Phase 2 |
| Scenarios A–D in the Government Workflow view, including an **isolated, intentionally weak baseline** comparison | ✅ Phase 2 |
| Automatic pause after a denied high-risk payment; officer resume via the dev CLI | ✅ Phase 2 (prototype) |
| **Signed mandate chains**: commission via the gateway → WAKALA-signed child mandate → chain re-verified on every use | ✅ Phase 3 |
| **Non-expansion**: child = parent grant ∩ task catalogue ∩ receiving-entity authority ∩ case; depth and cycle limits | ✅ Phase 3 |
| **Commission authority separate from execution authority** | ✅ Phase 3 |
| **Selective, cascading, persistent revocation** (mandate, case, agent-wide) | ✅ Phase 3 |
| **Transactional outcome audit** + idempotent reconciliation (repairs the Phase 2 gap) | ✅ Phase 3 |
| **Live authority-chain graph** (Delegation Network) | ✅ Phase 3 |
| Authenticated officer console, LLM tool-use adapters, agent-driven attacks, citizen receipts | ⏳ Phase 4 |
| Benchmarks | ⏳ Phase 4 |

The console shows only real backend state:
- registry counts, with key and mandate verification computed live
- security activity counted from `audit_events`
- an audit-chain integrity check
- developer scenario results returned by the real gateway

The delegation and receipt views remain labelled as illustrative.

### What Phase 3 does not do

- **Delegation is limited to catalogued tasks.** Today that means the insurance check, with a single delegation
  authority.
- **Officer actions are CLI-only.** Revoke and resume are run from the dev CLI; there is no authenticated officer UI.
- **Agents are simulated.** They are deterministic Python scripts, not model-driven autonomous AI.
- **The service boundary is in-process.** Services are only reachable via the trusted tool registry and have no HTTP
  routes, but production needs network-isolated services that verify gateway authorization themselves. See
  [docs/SECURITY_MODEL.md](docs/SECURITY_MODEL.md) §10.
- **No real systems.** Nothing touches a real government API, bank or payment provider. Keys are local development keys.

## Technology stack

| Layer | Choice |
|---|---|
| Backend | Python 3.11+ (tested on 3.13), FastAPI 0.115, Pydantic 2.11, Uvicorn, `cryptography` 44 (Ed25519), SQLite (stdlib) |
| Tests | Pytest 8 and FastAPI TestClient, using deterministic test keys and a frozen clock. All tests run offline. |
| Frontend | React 18, TypeScript 5.8, Vite 6, Tailwind CSS 4, Lucide icons, React Flow 12, Recharts 2, React Router 6 |
| Fonts | Inter, IBM Plex Sans Arabic and JetBrains Mono, bundled locally through Fontsource so the UI works offline |

No paid API keys are needed. No external LLM is involved in any security decision.

## Repository layout

```
backend/
  app/
    main.py              FastAPI app factory: CORS, security headers, error envelope
    api/                 routes.py (read APIs) · gateway.py (authorize/execute) · dev.py (dev-mode demo)
    core/
      config.py          Centralised settings; loopback-only CORS; production refused
      crypto.py          Canonical JSON, Ed25519 sign/verify, domain-separation tags
      identity/          Request authentication (proof of possession)
      mandates/          Canonical bytes; signature, issuer, authority and lifecycle verification
      authorization/     Pure default-deny policy engine (8 checks) and safe explanations
      execution/         Gateway (enforcement boundary) and trusted tool registry
      replay.py          Nonce store
      audit/             Hash-chained, append-only audit sink and verifier
      delegation/        DelegationValidator contract (Phase 2)
    agents/              Agent adapter interface, transports, simulated agents, LLM adapter interface
    workflow/            Case intake, scenarios A–D, weak baseline (test-only), officer CLI actions
    devtools/            DEV ONLY: keystore, mandate issuance, agent signer, demo scenarios, CLI
    models/database.py   SQLite tables (public keys, issuers, mandates, nonces, audit events, …)
    schemas/             Pydantic contracts, the single source of truth for data shapes
    services/            Bootstrap, repository, mandate store, case store, protected government services, capabilities
    data/                Synthetic JSON fixtures (including issuers.json) and documents
  run_dev.py             Starts the API in dev mode on 127.0.0.1:8000
  tests/                 304 offline tests (Phases 0–3, including delegation and audit failure injection)
frontend/src/            layouts/ pages/ components/ hooks/ lib/ types/ styles/
docs/                    ARCHITECTURE, SECURITY_MODEL, PRODUCT_VISION, DEMO_SCENARIOS
scripts/                 bootstrap.ps1 / bootstrap.sh
```

## Setup

Prerequisites: **Python 3.11+**, **Node.js 20+** (tested with 22.17) and npm.

### One-command bootstrap

This creates the venv, installs everything, runs the backend tests and builds the frontend.

Windows (PowerShell), from the repository root:

```bash
powershell -ExecutionPolicy Bypass -File scripts\bootstrap.ps1
```

macOS / Linux / Git Bash:

```bash
bash scripts/bootstrap.sh
```

### Manual setup

**Backend**

```bash
cd backend
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
```

(On macOS/Linux use `.venv/bin/python` instead of `.venv\Scripts\python`.)

**Frontend**

```bash
cd frontend
npm install
```

## Running locally

Use two terminals. Both servers bind to `127.0.0.1` only.

**Backend: http://127.0.0.1:8000** (interactive API docs at `/docs`)

Development mode, with the predefined demo scenarios enabled:

```bash
cd backend
.venv\Scripts\python run_dev.py
```

Without dev endpoints (the default for anything else):

```bash
cd backend
.venv\Scripts\python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

On first start the backend:
- generates development Ed25519 keys in `backend/.dev_keys/` (git-ignored, file mode 0600),
- registers their public keys, and
- issues three signed mandates into `backend/var/wakala.db` (git-ignored).

Mandates last 2 hours. Re-issue them with `.venvScriptspython -m app.devtools.cli mandates issue`, or restart the server. Delete
both folders to reset everything.

**Frontend: http://localhost:5173**

```bash
cd frontend
npm run dev
```

Then open **Government Workflow** and run scenarios A–D, or open **Simulation Lab → Developer demonstration** for the
Phase 1 gateway scenarios. Results appear in **Security Events** and on the **Command Center**. See
[docs/DEMO_SCENARIOS.md](docs/DEMO_SCENARIOS.md).

## Tests and build

```bash
cd backend
.venv\Scripts\python -m pytest
```

```bash
cd frontend
npm run build
```

`npm run build` type-checks with `tsc -b`, then produces `frontend/dist/`.

## API

| Method | Path | Purpose |
|---|---|---|
| POST | `/api/gateway/authorize` | Policy query for a **signed** action request. Returns ALLOW/DENY, reason codes, explanation, policy version, mandate ID, measured latency and audit reference. Never executes. |
| POST | `/api/gateway/execute` | Authorizes and, only if allowed, runs the tool from the trusted registry. Denied → **403**, tool not invoked. Audit failure → 503. |
| GET | `/api/mandates`, `/api/mandates/{id}` | Stored mandates with live signature, issuer, authority and lifecycle verification |
| GET | `/api/issuers` | Trusted issuer registry and authority limits, with public key fingerprints |
| GET | `/api/identity/keys` | Registered **public** keys only |
| GET | `/api/audit/events`, `/api/audit/integrity` | Real decisions; hash-chain verification |
| GET | `/api/agents`, `/api/agents/{id}`, `/api/citizens`, `/api/services`, `/api/scenarios` | Synthetic registry |
| GET | `/api/system/capabilities`, `/api/schemas/{name}`, `/health` | System information and contracts |
| GET / POST | `/api/dev/scenarios`, `/api/dev/scenarios/{key}/run` | **Dev mode only**, loopback clients, fixed scenarios |
| POST | `/api/workflow/scenarios/{key}/run` | Runs workflow scenario A–D (body `{"citizen_ref"}` for A). **Dev mode, loopback client, same-site origin** |
| GET | `/api/workflow/scenarios`, `/cases`, `/cases/{id}`, `/ledger`, `/tools` | Case state, history, linked audit events, synthetic ledger, exported tool definitions. **Loopback clients only** |
| GET | `/api/workflow/cases/{id}/authority-graph`, `/api/workflow/delegations` | Live authority chain (verified now) and trusted delegation records. **Loopback clients only** |

The `/api/gateway/*` body is a `SignedActionRequest`:
- `request` is the action, including `agent_id`, `mandate_id`, `tool_name`, `parameters`, `target_resource`,
  `timestamp` and `nonce`.
- `signature` is `{algorithm: "Ed25519", key_id, value}`, computed over `b"WAKALA-ACTION-REQUEST-v1\n"` + canonical
  JSON of `request`.

See `backend/app/devtools/agent_client.py` for a reference signer. Errors use a consistent envelope:
`{"error": {"code", "message", "details"}}`.

There are intentionally **no** HTTP endpoints for key generation, signing, issuing or revoking. Those are CLI-only,
run from `backend/`:

```bash
.venv\Scripts\python -m app.devtools.cli mandates list
```

The other commands are:
- `keys`
- `mandates verify|issue|revoke|tamper-demo` (`revoke` cascades to delegated children)
- `agents set-status|revoke`
- `cases list|resume|revoke-authority`
- `delegations list`
- `audit verify|tail|reconcile`
- `bench delegation`

## Configuration

See [.env.example](.env.example). Every value has a safe default:
- `WAKALA_CORS_ORIGINS` accepts loopback origins only.
- `WAKALA_DEV_MODE` defaults to off.
- `WAKALA_MAX_REQUEST_SKEW_SECONDS` defaults to 60.
- `WAKALA_ENV=production` is refused, because this prototype has no production key management.

## Synthetic data disclaimer

Every person, entity, officer, issuer, permit, policy, account and document in this repository is **fictional** and
exists only to demonstrate WAKALA.

- Financial references follow the `SYNTH-…` pattern. The schema rejects anything resembling a real account number or
  IBAN.
- The renewal fee (AED 500) and the official destination (`SYNTH-GOV-TREASURY-0001`) are synthetic.
- No payment is ever executed, and nothing connects to any payment or banking system.
- Development keys protect only synthetic identities and must never be reused.

## Next development phases

1. ~~Phase 2 — protected services and case-bound authority~~ ✅
2. ~~Phase 3 — signed, non-expanding mandate chains; selective revocation; transactional audit~~ ✅
3. **Phase 4 — humans and adversarial runs:**
   - an authenticated officer console
   - LLM tool-use adapters through the same signing interface
   - agent-driven prompt-injection runs
   - citizen receipts generated from audit data
3. **Phase 4 — Measurement:** decision latency and scenario outcomes measured from real runs only.

See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) and [docs/SECURITY_MODEL.md](docs/SECURITY_MODEL.md).
