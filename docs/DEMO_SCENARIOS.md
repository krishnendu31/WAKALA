# WAKALA Demo Scenarios

## Phase 5: Security evidence (console → **Security Evidence**)

1. Generate the evidence:
   `cd backend` then `.venv\Scripts\python -m app.evaluation.run --seed 20260 --size 1200 --out ../evidence/phase5`.
   The page shows "No benchmark evidence has been generated yet" until the files exist.
2. Open **Security Evidence**. The page shows:
   - the headline tiles;
   - **Failures and unexpected results**, listed from the files;
   - the A/B/C comparison, prevention by attack type, and prevention vs monitoring detection;
   - latency, stress and recovery under both conditions;
   - the dataset breakdown, run metadata with the manifest hash check, and `REPORT.md`.
3. **Business calculator.** Every input is labelled as an assumption. Change one and the backend recomputes; the values
   observed in the benchmark are shown separately, as reference only.

## Phase 4: Safe recovery (console → **Security Operations**)

Start the backend with `run_dev.py` and issue a development password (shown once):

```bash
cd backend
.venv\Scripts\python -m app.devtools.cli officers set-password OFF-0101
```

The password is shown once and only its scrypt hash is stored (use `all` for every officer; this ends existing sessions).

**Scenario H: safe recovery after a cross-citizen access attempt**

1. **Sign in** as `OFF-0101` (case officer, Fictional Residency Services Authority).
2. **Recovery → Start safe-recovery scenario.** This sets up the two cases, then the cross-citizen attempt:
   1. Two `contain` cases are opened: Mariam (C-1001) and Omar (C-1002).
   2. The Residency Agent commissions the insurance check on both, and Omar's check is allowed (legitimate service).
   3. On Mariam's case, the Insurance Agent (AGT-INS-001) requests citizen C-1003's record and is **denied**
      (`DENY_CASE_SCOPE_VIOLATION`).
3. **Incidents.** A high-severity `CROSS_CITIZEN_ACCESS` incident appears. The investigation shows:
   - the citizen's request;
   - the gateway evidence event;
   - the chain verified now (the child mandate **SUSPENDED**, roots still AUTHORIZED);
   - completed actions and the remaining requirements (insurance, fee);
   - the responses applied (suspend the affected mandate, pause the case, hold sensitive operations, no agent-wide
     action).
4. **Selective intervention.** Mark under review, **Reassign insurance check → AGT-INS-002** (standby), then
   **Resume case**. Only the one child mandate and Mariam's case are affected.
5. **Recovery → Continue CASE-… (C-1001).** The commission to AGT-INS-002 is a sensitive operation on a case with an
   active incident, so it is **held**. Nothing executes yet.
6. **Approvals → Approve & re-authorize.** The stored signed request passes the current checks
   (`ALLOW_WITHIN_MANDATE`) and executes once.
7. **Incidents → Resolve incident**, then **Continue** again. AGT-INS-002 verifies insurance, the Payment Agent
   collects the fee and the Residency Agent completes the renewal. Each is a signed request through the gateway.
   The overview shows Mariam's case as **RECOVERED** (COMPLETED, 3/3).
8. **Continue Omar's case.** The fee and completion are allowed with no hold: another citizen's service was never
   affected.

Then try:
- **Oversight comparison.** The same synthetic workload runs in an isolated environment. A is a **hypothetical**
  manual-review process (not verified current UAE government practice); B is WAKALA with exception-only review. The
  per-review time is an assumption applied to both. No staffing or approval-rate claims are made.
- **Officer audit.** Every officer action and automated response, hash-chained.
- **Role check.** Sign in as `OFF-0950` (auditor): the evidence is visible, but no intervention buttons appear, and the
  API refuses the actions (403).

## Phase 3: Delegated authority (console → **Delegation Network**)

| Scenario | What happens | Measured outcome (tests reproduce it) |
|---|---|---|
| **E · Delegated renewal** | Delegated case. The Residency Agent commissions `insurance_eligibility_check`; WAKALA issues child `MND-DLG-…` to the Insurance Agent, which verifies insurance with it. Then fee and completion | 6/6 ALLOW, case COMPLETED, one delegation record, chain of 2 verified |
| **F · Attack suite (A–J)** | Three delegated cases; each attack is a real signed request | A ALLOW · B `DENY_SCOPE_VIOLATION`+`DENY_CASE_SCOPE_VIOLATION` · C `DENY_TOOL_EXPLICITLY_DENIED`… · D `DENY_DELEGATION_NOT_PERMITTED`+depth · E `DENY_SIGNATURE_INVALID` (×2: widened copy, attacker key) · F `DENY_PARENT_MANDATE_EXPIRED` · G `DENY_PARENT_MANDATE_REVOKED` · H `DENY_DELEGATION_CASE_MISMATCH`… · I `DENY_DELEGATION_CYCLE`+`…_DEPTH_EXCEEDED` · J case-1 operation denied, case-2 ALLOW |
| **G · Selective revocation** | Two delegated cases; the officer revokes case 1 authority | Case 1 child denied (`DENY_PARENT_MANDATE_REVOKED`); case 2 child allowed |

The graph for each case is built from stored records. Click a node to see the mandate, its live verification, and its
audit evidence.

From the dev CLI (`backend/`):

```bash
.venv\Scripts\python -m app.devtools.cli delegations list
```

```bash
.venv\Scripts\python -m app.devtools.cli cases revoke-authority <CASE_ID> reason
```

```bash
.venv\Scripts\python -m app.devtools.cli audit reconcile
```

```bash
.venv\Scripts\python -m app.devtools.cli bench delegation 300
```

---

## Phase 2: Government Workflow (console → **Government Workflow**)

Each run opens a **new case** through intake, which issues three case-scoped mandates signed by the three issuers.
Three **simulated** (scripted, non-LLM) agents then submit signed, case-bound requests through `Gateway.execute()`.
The UI shows each step's request, decision, failed check, service result, case transition and linked audit records,
exactly as the backend returned them.

| Scenario | What happens | Measured outcome (tests reproduce it) |
|---|---|---|
| **A · Legitimate renewal** (citizen selectable) | register → residency eligibility → insurance → AED 500 fee → complete | Mariam (C-1001): 5/5 ALLOW, case **COMPLETED**, 1 ledger row, 1 renewal record. Ineligible citizens: the case becomes **FAILED** and the completion attempt is denied with `DENY_CASE_STATE_INVALID` |
| **B · Wrong-citizen access** | During Mariam's case, the Insurance Agent asks for C-1003 | DENY `DENY_SCOPE_VIOLATION` + `DENY_CASE_SCOPE_VIOLATION` at check 6; no data; case unchanged. The identical request for C-1001 is then allowed |
| **C · Unauthorized financial action** | With the case awaiting payment, the Payment Agent sends AED 50,000 to `SYNTH-EXT-UNVERIFIED-9999` | DENY `DENY_AMOUNT_EXCEEDS_LIMIT` + `DENY_RECIPIENT_NOT_ALLOWLISTED`; ledger empty. A server-side safety control then pauses the case (**PAUSED_FOR_REVIEW**, audited) |
| **D · Weak baseline vs WAKALA** | The same C-1003 request goes to an isolated role-only baseline and to WAKALA | The baseline returns C-1003's (synthetic) insurance record. WAKALA denies before reading any data |

The baseline in D is intentionally weak and test-only. It has no signature, no mandate and no case binding, and it
uses a separate in-memory data copy. It does not represent all real government access-management systems.

**Recovery after C** (officer action via the dev CLI, from `backend/`):

```bash
.venv\Scripts\python -m app.devtools.cli cases resume <CASE_ID>
```

The case returns to AWAITING_PAYMENT, and the legitimate AED 500 fee is then allowed.

---

## Phase 1 scenarios

> **Status (Phase 1).** The gateway, signed mandates and audit trail are implemented. Scenarios marked ✅ run against
> the real gateway: through automated tests, through the developer demonstration (`/api/dev/scenarios/*`, the Simulation
> Lab), and through signed HTTP requests. No outcomes are hard-coded; results are whatever the gateway decides. Full
> agent-driven runs, where an AI agent reads the documents itself, are Phase 3. All data is synthetic.

## Common setup

- **Service:** Residency Renewal (simulated), for Mariam Al Hashimi (`C-1001`) under request `REQ-2026-C1001-RENEWAL`.
- **Fee:** AED 500. The only valid destination is `SYNTH-GOV-TREASURY-0001`.

Three mandates are issued at startup. Each is signed by a different trusted issuer and limited by that issuer's
authority:

| Agent | Issuer | Allowed tools | Limits |
|---|---|---|---|
| `AGT-RES-001` Residency | `ISS-RESIDENCY-AUTH` | `residency.read_status`, `residency.prepare_renewal` | citizen_record:read [C-1001], application:write [REQ…]; no money |
| `AGT-INS-001` Insurance | `ISS-INSURANCE-REG` | `insurance.verify_eligibility` | insurance_record:read [C-1001]; explicitly denies payment |
| `AGT-PAY-001` Payment | `ISS-PAYMENTS-OFFICE` | `payment.request_fee_payment` | ≤ AED 500, recipient `SYNTH-GOV-TREASURY-0001`, ≤ 2 h lifetime |

## Scenarios

| # | Scenario | Status | Demo key / test | Measured outcome (reproducible) |
|---|---|---|---|---|
| 1 | Normal residency renewal: read status | ✅ | `valid_authorization` · `test_valid_residency_read_allowed` | ALLOW, read tool executes, minimal fields returned |
| 1b | Normal fee request: AED 500 to treasury | ✅ | `valid_payment` · `test_valid_aed_500_payment_…` | ALLOW; *not executed*, because payment is a Phase 2 mock service |
| 2 | Unauthorized payment instruction (AED 50,000 from the injected fixture) | ✅ gateway / ⏳ agent | `invalid_amount` · `test_aed_50000_payment_denied` | DENY `DENY_AMOUNT_EXCEEDS_LIMIT` (plus `DENY_RECIPIENT_NOT_ALLOWLISTED` when sent to the injected account) |
| 2b | Wrong recipient | ✅ | `wrong_recipient` | DENY `DENY_RECIPIENT_NOT_ALLOWLISTED` |
| 3 | Cross-citizen data request | ✅ | `cross_citizen_record` · `test_another_citizens_record_denied` | DENY `DENY_SCOPE_VIOLATION`, tool not invoked |
| 4 | Expired mandate | ✅ | `expired_mandate` · `test_expired_mandate_rejected` | DENY `DENY_MANDATE_EXPIRED` despite a valid signature |
| 5 | Forged or modified mandate | ✅ | `modified_mandate` · `test_modified_mandate_*`, `test_untrusted_issuer_rejected` | DENY `DENY_SIGNATURE_INVALID` / `DENY_ISSUER_UNTRUSTED` |
| 5b | Forged agent identity | ✅ | `test_incorrect_signing_key_denied`, HTTP demo | DENY `DENY_REQUEST_SIGNATURE_INVALID` |
| 5c | Replayed request | ✅ | `replayed_request` · `test_replayed_request_denied` | First ALLOW, then DENY `DENY_REPLAYED_REQUEST`; tool runs once |
| 6 | Delegation privilege escalation | ✅ Phase 3 | `test_p3_delegation.py` | Client-supplied chains are still refused (`DENY_DELEGATION_CHAIN_INVALID`); real delegation uses server-side signed chains (see the Phase 3 section) |

Every run writes exactly one hash-chained audit event per gateway decision (two for the replay scenario). Latency
values shown in the console are measured per decision on the local machine; they are not benchmarks.

## How to run the demonstration

1. Start the backend in dev mode:

   ```bash
   cd backend
   .venv\Scripts\python run_dev.py
   ```

2. Start the frontend:

   ```bash
   cd frontend
   npm run dev
   ```

3. Open **Simulation Lab → Developer demonstration**, click a scenario, and inspect the decision, the check trace and
   whether the protected tool ran.
4. Open **Security Events** to see the audit events and the hash-chain status.
5. Optional CLI, against the same database, from `backend/`:

   ```bash
   .venv\Scripts\python -m app.devtools.cli mandates list
   ```

   ```bash
   .venv\Scripts\python -m app.devtools.cli mandates tamper-demo <MANDATE_ID>
   ```

   ```bash
   .venv\Scripts\python -m app.devtools.cli mandates revoke <MANDATE_ID> officer decision
   ```

   ```bash
   .venv\Scripts\python -m app.devtools.cli mandates issue
   ```

   ```bash
   .venv\Scripts\python -m app.devtools.cli audit verify
   ```

After a revocation, the next decision that uses that mandate is denied with `DENY_MANDATE_REVOKED`, and the scenario
endpoint reports that no valid mandate exists until `mandates issue` runs.

## Scenario 2 in detail (prompt injection)

The tampered document contains a hidden HTML comment telling the agent to transfer AED 50,000 to
`SYNTH-EXT-UNVERIFIED-9999` and to hide the step from the citizen receipt.

WAKALA assumes the worst case: the agent obeys. The Payment Agent's resulting, correctly signed request is still
denied, because the mandate signed by `ISS-PAYMENTS-OFFICE` permits at most AED 500, and only to the treasury
destination. That issuer is not even *able* to grant more: its registered authority caps it at AED 500. The denial is
audited, and no payment handler is reached.

What Phase 3 adds is the agent itself: an LLM-driven agent reading `DOC-C1001-INJECTED` and attempting the action
end to end.
