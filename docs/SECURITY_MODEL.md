# WAKALA Security Model (Phase 4)

> **Status.** Phase 1 enforces identity, mandate and authorization checks. Phase 2 adds case-bound authority in front of
> protected synthetic government services. Both run in a local development prototype on synthetic data. It is **not production-ready and not government-certified**. Each control below is marked ✅ when it
> is implemented and tested, or ⏳ with the phase that will deliver it.

## 1. Security objective

An AI agent must never gain authority merely because it operates inside a trusted government system. Every sensitive
action is independently authorized against an issuer-signed, task-limited mandate. Anything not positively authorized
is denied.

## 2. What Phase 1 genuinely enforces

| Control | Mechanism | Tests |
|---|---|---|
| ✅ Agent identity by proof of possession | Ed25519 signature over `WAKALA-ACTION-REQUEST-v1\n` + canonical request JSON, verified against the public key the registry binds to that agent | `test_p1_identity.py` |
| ✅ Freshness | Signed `timestamp` must be within ±60 s of server time (configurable 5–600 s) | stale, future-dated and boundary cases |
| ✅ Replay protection | `(agent_id, nonce)` accepted once; retained for 2× the skew window, so expired nonces are already stale | replay, nonce reuse, cross-agent |
| ✅ Signed mandates | Ed25519 over `WAKALA-MANDATE-v1\n` + canonical mandate JSON (excluding `signature_metadata`) | `test_p1_mandates.py` |
| ✅ Issuer trust | The issuer must be registered and active, the signing `key_id` must be that issuer's key, and the key must be registered to it | untrusted, impersonated, cross-issuer, revoked issuer |
| ✅ Issuer authority | The mandate's service, agent, tools, amount, recipients and lifetime must all fall within the issuer's declared authority | 8 excess-authority cases |
| ✅ Mandate lifecycle | Signed status must be `active`; not revoked server-side; `issued_at ≤ now < expires_at` | expired, boundary, not-yet-valid, revoked |
| ✅ Default-deny policy | 8 ordered checks, no LLM; `allowed` only if all 8 return `passed`; any exception returns `DENY_POLICY_EVALUATION_ERROR` | `test_p1_authorization.py` |
| ✅ Protected execution | Tools dispatched only from a fixed registry, only after ALLOW, with the digest bound to the authorized request | `test_p1_enforcement.py` |
| ✅ Audit | One hash-chained event per decision; audit failure blocks execution | `test_p1_audit.py` |
| ✅ Case-specific authority (Phase 2) | Check 6 also requires the signed `case_id` to name an existing, unexpired case. The case must have the same citizen and request as the mandate, list this agent with this mandate, authorize this operation and serve the same purpose (service), and its state must permit the tool | `test_p2_workflow.py` |
| ✅ Protected services (Phase 2) | Handlers re-validate the case in one transaction with compare-and-swap; any refusal rolls back. The payment service independently accepts only the official fee and treasury, and is idempotent per case | `test_p2_workflow.py` |
| ✅ Case lifecycle (Phase 2) | Pure transition table with prerequisite guards; impossible transitions raise | state-machine tests |
| ✅ Safety pause (Phase 2, prototype) | After a denied payment in scenario C, a server-side control pauses the case (audited). Resume via the officer CLI only | scenario C test |
| ✅ Signed mandate chains (Phase 3) | Children are issued only after a gateway-authorized commission, signed by the delegation-only issuer, and stored with a trusted delegation record. At use, the gateway resolves the chain server-side and verifies every ancestor and link | `test_p3_delegation.py` |
| ✅ Non-expansion (Phase 3) | child ⊆ parent's commission grant ∩ task catalogue ∩ receiving-entity authority ∩ parent case/citizen/request/service/money/time; depth ≤ min(grant, 3); no cycles | pure + gateway tests |
| ✅ Client chains ignored (Phase 3) | A `delegation_chain` in the request is never trusted; non-empty → `DENY_DELEGATION_CHAIN_INVALID` | test |
| ✅ Selective, persistent revocation (Phase 3) | Mandate-level (cascade), case-level, agent-wide (separate); survives restart; ancestor revocation also enforced at verification | revocation tests |
| ✅ Transactional outcome audit (Phase 3) | Service writes and outcome event share one transaction; idempotent reconciliation | `test_p3_audit_consistency.py` |
| ⏳ Authenticated officer console | Phase 4; officer actions are CLI-only today | — |

## 2a. The Phase 2 problem: authorized for the service, not for this case

The Insurance Agent is authenticated, active and holds a valid, issuer-signed mandate to call
`insurance.verify_case_eligibility`. If it asks about citizen C-1003 while handling Mariam's (C-1001) case, it is
still denied:
- `DENY_SCOPE_VIOLATION`: the mandate is scoped to C-1001.
- `DENY_CASE_SCOPE_VIOLATION`: the case's citizen is C-1001.

The decision is made before the service runs, so no data is read and no state changes. The denial message and the
audit event contain no attribute of C-1003 (tested).

The isolated weak baseline, which checks only "has the insurance role", returns that record. This is the difference
WAKALA addresses.

**What a denial guarantees in Phase 2** (tested with whole-table snapshots of cases, ledger, renewals, citizens and
mandates):
- no protected data is returned
- no citizen record or case is modified
- no payment is created
- no success event is recorded; only a `denied` decision event is written

## 2b. Phase 3: delegated authority

**Threats addressed**

| Threat | Control | Tested outcome |
|---|---|---|
| Child reads another citizen | Child resources = task template instantiated with the case citizen; case binding | `DENY_SCOPE_VIOLATION`, `DENY_CASE_SCOPE_VIOLATION` |
| Child performs an unrelated operation (payment) | `allowed_tools` ⊆ task operations; parent's denials are inherited | `DENY_TOOL_EXPLICITLY_DENIED` |
| Child creates a broader child | Children carry no commission grant; depth limit; catalogue receivers | `DENY_DELEGATION_NOT_PERMITTED` + depth |
| Forged / modified delegation | Ed25519 over canonical child bytes, delegation-only issuer key | `DENY_SIGNATURE_INVALID` |
| Correctly signed but expanding child | `check_non_expansion` at every use | `DENY_DELEGATION_EXPANDS_AUTHORITY` |
| Delegation authority used to mint a root | `delegation_only` issuers may sign children only | `DENY_ISSUER_AUTHORITY_EXCEEDED` |
| Expired / revoked ancestor | `verify_chain` checks every ancestor's lifecycle | `DENY_PARENT_MANDATE_EXPIRED` / `…_REVOKED` |
| Child reused on another case | `child.case_id` signed; root must be the case's mandate | `DENY_DELEGATION_CASE_MISMATCH` |
| Cycles, excessive depth | Agent and mandate uniqueness along the chain; depth ≤ min(grant, 3); bounded resolution | `DENY_DELEGATION_CYCLE`, `…_DEPTH_EXCEEDED` |
| Replayed commission or delegated call | Nonce store | `DENY_REPLAYED_REQUEST`; child issued once |
| Receiving entity no longer authorizes its agent | Task's receiving issuer authority checked at every use | `DENY_DELEGATION_NOT_PERMITTED` |

**Measured verification cost.** The figures below come from `python -m app.devtools.cli bench delegation 300`, run
on this machine with in-memory SQLite in a single process. They are a measurement, not a performance claim.

| Measurement | Median | p95 |
|---|---|---|
| Direct-mandate authorization | 2.77 ms | 4.19 ms |
| Delegated-mandate authorization (2-link chain) | 3.50 ms | 5.46 ms |
| Chain verification alone (2 Ed25519 verifies + narrowing) | 0.47 ms | 0.65 ms |

## 2c. Phase 4: assurance, human intervention and recovery

**Detection.** Six deterministic rules over audited decisions (not machine learning):

| Rule | Threshold / window | Severity (escalated) | Classification |
|---|---|---|---|
| `REPEATED_DENIALS` | 5 in 10 min | medium (high at 10) | policy violation |
| `REQUEST_RATE` | 30 in 60 s | medium (high at 60) | policy violation |
| `CROSS_CITIZEN_ACCESS` | 1 in 30 min | high (critical at 3) | policy violation |
| `UNAUTHORIZED_DELEGATION` | 1 in 30 min | medium (high at 3) | policy violation |
| `ACTION_AFTER_REVOCATION` | 1 in 30 min | medium (high at 3) | policy violation |
| `CREDENTIAL_FAILURES` | 3 in 10 min | high (critical at 6) | possible credential misuse |

Each incident carries an interpretation that a violation is not by itself evidence of a malicious agent. Only rules
the latest event contributes to can fire, so allowed traffic does not re-raise old findings; repeats update the same
incident (deduplicated per rule, subject and case) and can raise its severity.

**Information to agents.** An agent receives the gateway reason code only. Incident IDs, rule thresholds and
responses are served only to authenticated officers.

**Graduated response.** `ALLOW`, `DENY`, `REQUIRE_HUMAN_APPROVAL`, `SUSPEND_MANDATE`, `REVOKE_MANDATE`,
`ESCALATE_INCIDENT`, each recorded with a `RESP_*` reason code. Automatic responses are limited to the affected
mandate and case. A single ordinary denial is recorded only. No automatic response is agent-wide; `REVOKE_MANDATE`
and agent-wide action are officer decisions.

**Approval semantics.**
1. A held request returns `ESCALATE_HUMAN_REVIEW` (HTTP 202) and nothing executes.
2. Approval claims the record by compare-and-swap (`pending → executing`), so it executes at most once.
3. The stored signed request is re-authorized against the *current* state: signature, mandate signature and lifecycle
   (revoked, expired, suspended), chain, case binding, scope, parameters. Only the freshness window and the nonce are
   waived, because the request was already checked for those when first received.
4. If anything fails, the approval becomes `approved_denied` and the tool is never called. Expired approvals and rejected
   approvals never execute. Approval cannot override revoked, expired or suspended authority.

**Officer authentication (development only).**
- Only a salted scrypt hash is stored (SQLite). `cli officers set-password <ID|all>` generates a random password,
  shows it once on the terminal and ends that officer's sessions. *Phase 5 change:* Phase 4 kept the plaintext dev
  passwords in `backend/.dev_keys/officer_credentials.json`. At startup that file is now migrated to hashes, for any
  officer without one, then overwritten and deleted.
- Refused actions by an authenticated officer (`officer.action_refused`, with the code) and rejected session tokens
  (`officer.session_rejected`) are audited. Before Phase 5 only successful actions were.
- Session tokens are random, returned once and stored as SHA-256. Sessions expire after 15 min idle or 60 min absolute.
  Five failures lock the account temporarily.
- Identity comes **only** from the session token. Request bodies are strict, so an `officer_id` field is rejected (422).
- Permissions per role (auditor read-only; case officer; security supervisor with revoke and all entities) and the
  officer's entity are checked server-side on every action.
- The frontend holds no credentials beyond the user's own session token (sessionStorage).
- Production would replace this with the government identity provider (SSO with MFA), short-lived signed tokens,
  and officer actions signed by officer keys.

**Fail closed.** A gateway or audit failure during approval leaves the approval unexecuted. An HTTP transport that
cannot reach the gateway reports failure and does not queue. Revocation during execution is refused by the service
inside the transaction (`AUTHORITY_WITHDRAWN`). An expired session is rejected. On restart, approvals past their TTL
are expired, and nothing re-runs automatically.

## 2d. Phase 5: evaluation and what it changed

The benchmark (`backend/app/evaluation`, evidence in `evidence/phase5`) runs the real gateway and officer code in
isolated environments:
- temporary keys;
- in-memory or temporary-file SQLite;
- random officer passwords that exist only in memory.

It never opens the server database or `backend/.dev_keys`. Authorization logic was **not** changed to improve scores.
The changes it prompted are in monitoring and audit:
1. **Bounded observer lookback.** Rules read at most 120 recent decisions plus 120 recent denials, through composite
   `(subject, seq)` indexes. Rule firing is exact while a subject has at most 120 denials in the 30-minute window.
   Beyond that, counts saturate at the cap, which is still twice the largest threshold.
2. **Incident updates serialised in-process with bounded retry.** Concurrent decisions previously lost monitoring
   updates.
3. **Refused officer actions audited** (above).

Measured weaknesses that were deliberately *not* tuned away (see `REPORT.md`):
- **REQUEST_RATE pins to whichever case was last.** It is an agent-wide volume rule, but it attaches its incident to
  the agent's latest case. Under the `contain` policy, the approval gate then holds that case's sensitive steps, so
  machine-speed traffic stalls legitimate cases.
- **Direct-model mandates block entity-scoped officers.** They carry no signed `case_id`, so only a supervisor with
  all-entity scope can act on them.

## 3. Identity authentication

1. The agent builds an `ActionRequest`. It contains the agent, mandate ID, tool, parameters, target, request ID,
   timestamp and a fresh nonce.
2. The agent signs `ACTION_REQUEST_TAG + canonical_json(request)`. Canonical JSON means sorted keys, no extra
   whitespace, UTF-8, and NaN disallowed, produced from the validated model.
3. The gateway looks up the key the **registry** binds to the claimed `agent_id` (the passport's `key_id`, owner type
   `agent`, status `active`). It requires `signature.key_id` to match, then verifies the signature.
4. Only then does an `AuthenticatedPrincipal` exist. Without one, the policy stops at check 1, and no mandate or
   passport data is evaluated or revealed.

An `agent_id` string alone never establishes identity. A browser or attacker that posts `{"agent_id": "AGT-PAY-001"}`
without the private key gets `DENY_REQUEST_SIGNATURE_INVALID` (tested). The domain tag stops a signature made for one
message type from verifying as another.

## 4. Mandate signing and verification

- **Signing.** The issuer computes `MANDATE_TAG + canonical_mandate_bytes(m)` with `signature_metadata` excluded, signs
  it with its Ed25519 key, and attaches `{algorithm, key_id, signature (base64url, 64 bytes), signed_at}`. `signed_at`
  is informational and not covered by the signature.
- **Verification order.** The gateway runs these steps in sequence:
  1. Reject if unsigned.
  2. Reject if the issuer is unknown or inactive.
  3. Reject if the signing key is not that issuer's key.
  4. Reject if the signature does not verify.
  5. Reject if the mandate exceeds the issuer's authority.
  6. Reject if the mandate is issued to a different agent.
  7. Reject if the mandate is outside its lifecycle (revoked, not yet valid or expired).

  `issuer_id` is only used to choose which key must have signed. A field such as "signed by Government Officer" confers
  nothing (tested).
- **Storage.** Agents reference mandates by ID and never submit mandate bodies. The store is still re-verified on every
  use, so a modified row fails with `DENY_SIGNATURE_INVALID` and an unparseable row fails with
  `DENY_MANDATE_MALFORMED`.
- **Revocation.** Revocation is recorded server-side (`mandates.revoked`) and takes effect on the next decision, even in
  a running server, because the CLI shares the same database.

## 5. Authorization checks

| # | Check | Examples of reason codes |
|---|---|---|
| 1 | Identity authenticated and matches claim | `DENY_UNKNOWN_AGENT`, `DENY_REQUEST_SIGNATURE_INVALID`, `DENY_IDENTITY_UNVERIFIED` |
| 2 | Passport exists and is active; key is the registered one | `DENY_AGENT_NOT_ACTIVE` |
| 3 | Mandate exists, signed, trusted issuer, within authority, bound to agent | `DENY_SIGNATURE_INVALID`, `DENY_ISSUER_UNTRUSTED`, `DENY_ISSUER_AUTHORITY_EXCEEDED`, `DENY_MANDATE_AGENT_MISMATCH` |
| 4 | Active, not revoked, inside validity window | `DENY_MANDATE_EXPIRED`, `DENY_MANDATE_REVOKED` |
| 5 | Tool registered, not denied, explicitly allowed, same service | `DENY_UNKNOWN_TOOL`, `DENY_TOOL_EXPLICITLY_DENIED`, `DENY_TOOL_NOT_PERMITTED` |
| 6 | Citizen, request and target resource inside the mandate | `DENY_SCOPE_VIOLATION` |
| 7 | Strict tool parameters; amount ≤ limit; recipient allow-listed | `DENY_INVALID_PARAMETERS`, `DENY_AMOUNT_EXCEEDS_LIMIT`, `DENY_RECIPIENT_NOT_ALLOWLISTED`, `DENY_CONSTRAINT_MISSING` |
| 8 | Fresh timestamp, unused nonce, no delegation chain | `DENY_REQUEST_STALE`, `DENY_REPLAYED_REQUEST`, `DENY_DELEGATION_CHAIN_INVALID` |

- **Short-circuiting.** Checks 1–4 short-circuit. Checks 5–8 are all evaluated, so a denial lists every violated
  constraint.
- **Consistency guard.** The gateway independently requires `allowed` to equal `(reason_codes == [ALLOW_WITHIN_MANDATE])`.
  A buggy policy that returns "allowed" with deny codes is treated as a denial (tested).
- **Explanations.** These are generic sentences with no keys, signatures or mandate internals beyond the reason.

## 6. Threats and controls

| Threat | Control | Status |
|---|---|---|
| Prompt injection ("transfer AED 50,000 to SYNTH-EXT-UNVERIFIED-9999") | The injected text cannot create, widen or sign a mandate. The resulting call is denied with `DENY_AMOUNT_EXCEEDS_LIMIT` and `DENY_RECIPIENT_NOT_ALLOWLISTED`. WAKALA does not try to detect the injection. | ✅ gateway level; ⏳ agent-driven run in Phase 3 |
| Excessive permissions | Task-limited mandates: one citizen, one request, explicit tools and resources, ≤ issuer lifetime (≤ 24 h) | ✅ |
| Forged agent identity | Signature verification against the registered key; key ID binding | ✅ |
| Mandate tampering | Canonical bytes plus Ed25519; re-verified on every use | ✅ |
| Issuer over-reach | Issuer authority limits | ✅ |
| Unauthorized delegation | Delegated requests denied | ✅ (deny); ⏳ verification in Phase 2 |
| Replay | Nonce store plus freshness window | ✅ |
| Parameter swap after authorization (TOCTOU) | Single-call execute, immutable request, digest-bound dispatch, no reusable decision tokens | ✅ |
| Arbitrary code or tool execution | Fixed registry; names are dictionary keys only; no `eval`, `exec` or dynamic import | ✅ |
| Gateway bypass | Software boundary only in the prototype (see §8) | ⚠️ limitation |
| Audit tampering | Hash chain detects modification, reordering and mid-log deletion | ✅ partial (see §7) |
| Dev endpoints abused | Off by default; loopback clients only; cross-site `Origin` rejected; fixed scenarios only; no key, sign, issue or revoke over HTTP | ✅ |

## 7. Audit trail

**Recorded per decision:**
- event ID, sequence and UTC timestamp
- actor: the authenticated agent, or `UNAUTHENTICATED` together with the claimed ID
- tool, request ID, mandate ID and version
- `allowed`/`denied`, reason codes, policy version and latency
- evidence: request digest, action ID, nonce, parameter *names*, target and origin
- `previous_event_hash` and `event_hash`

**Never recorded:** keys, signatures, parameter values, personal records or document text. A test checks this.

**Integrity.** `event_hash = SHA-256(canonical event without event_hash)`, and each event includes its predecessor's
hash. `GET /api/audit/integrity` and `python -m app.devtools.cli audit verify` recompute the chain.

**Honest limit.** Whoever controls the storage can truncate the tail or rewrite the whole chain consistently; a test
documents tail truncation. Production needs:
- the head hash checkpointed periodically to an independent write-once system or transparency log, signed by the
  gateway, and
- logging infrastructure the gateway operator cannot rewrite.

**Fail closed.** If an event cannot be written, the request returns 503 and nothing executes.

## 8. Development keys vs production

**Demo (Phase 1):**
- Agent and issuer private keys live as PKCS#8 PEM files in `backend/.dev_keys/`, which is git-ignored, has its own
  `.gitignore *`, and uses file mode 0600.
- The keys are generated on first start. Only public keys and fingerprints enter the database or any API response.
- Server-side "agents" in the demo, CLI and tests sign with these keys. The browser never receives a key and cannot
  choose the identity, tool or parameters of a demo scenario.

**Production alternative (not implemented):**
- **Agent identity:** workload identity, such as SPIFFE/SPIRE SVIDs or cloud workload identity federation, with
  short-lived, workload-bound credentials, or signing through an HSM or cloud KMS so private keys never leave the
  signing boundary.
- **Issuer keys:** HSM-backed, with officer approval workflows, rotation, and published key status.
- **Enforcement:** protected services enforce gateway authorization themselves (mutual TLS plus action-bound tokens) and
  are unreachable directly by agents.

## 9. Failure modes

| Situation | Behaviour |
|---|---|
| Policy or engine exception, or storage error during evaluation | `DENY_POLICY_EVALUATION_ERROR`, audited, not executed |
| Audit write fails | HTTP 503, not executed |
| Malformed HTTP body | HTTP 422 (validation envelope). No decision and no audit event, because no action was evaluated |
| Stored mandate corrupted | `DENY_MANDATE_MALFORMED` |
| Tool handler raises after ALLOW | `execution_failed`; the decision stays audited |
| Clock skew > window | `DENY_REQUEST_STALE` |

## 9a. Audit semantics (repaired in Phase 3)

For each protected service call there are two hash-chained events: a **decision** event (authorization) and an
**outcome** event (execution). They are never merged.

- **Phase 2 gap, now closed.** Previously the outcome event was written after the service committed, so a failed
  write left a committed change with no outcome record.
- **Now** the outcome event is written with `append_in(conn, …)` inside the service's own SQLite transaction, so the
  change and its outcome commit or roll back together.
- **Failure injection is tested.** The API then reports `OUTCOME_NOT_RECORDED_ROLLED_BACK`, the ledger, case and
  delegation tables are unchanged, and reconciliation later records `authorized_not_executed`. It is idempotent.
- **Non-transactional effects** (for example a future external bank API) cannot share the transaction. They would be
  reported as `OUTCOME_NOT_RECORDED` (committed) and reconstructed by reconciliation from service-side records keyed
  by `decision_id`. Production would add a transactional outbox plus an idempotency key towards the external system.

## 10. Known limitations

- Local development prototype; `WAKALA_ENV=production` is refused.
- The gateway boundary is in-process; see §8 for production bypass prevention.
- The audit chain is not externally anchored (§7).
- **Phase 2 boundary is in-process.** Services are only reachable via the tool registry and have no HTTP routes, but
  code inside the backend process could import them directly. Production needs network-isolated services that verify
  a gateway-issued, action-bound token themselves.
- **Simulated agents.** The agents are deterministic scripts, not autonomous AI. No LLM adapter exists yet.
- **Development-only officer authentication** (§2c). Its credentials file in `.dev_keys/` is as sensitive as the
  keys there. The `/api/workflow/*` read endpoints are still loopback-restricted without user login.
- **Deterministic rules only.** Static thresholds, a single process, no per-agent baselining. An attacker who stays
  under thresholds is still constrained by the gateway, but is not flagged.
- **Observer coupling.** Rules query the audit log after each decision; this adds latency (roughly 90 s for the full
  test suite versus earlier phases) and would need a stream processor at scale.
- **Case intake is unauthenticated** apart from dev-mode, loopback and origin checks. It stands in for a front office
  and signs case mandates with development issuer keys.
- **Execution events are best-effort** after commit (see §9a).
- **Delegation scope.** Delegation exists for the catalogued tasks only (insurance check; fee collection is catalogued
  but no issuer grants it). There is a single delegation authority, the global maximum depth is 3, and the demo grant
  allows depth 1.
- **Development-only cryptographic keys.** The government issuers, the delegation authority and the agents all sign
  with unencrypted PEM keys in `backend/.dev_keys/` (git-ignored). The delegation authority key sits in the same
  process as the gateway. Anyone with filesystem access to that directory can mint mandates. Production requires
  HSM/KMS-backed issuer and delegation signing, with officer approval for roots.
- **Single-process trust.** Gateway, policy engine, delegation service, protected services and audit store share one
  Python process and one SQLite file. A compromise of that process or file defeats every control above. There is no
  separation between policy decision and enforcement points, and no mTLS between services.
- **Revocation latency.** Revocation is immediate within this process (one DB). Distributed deployments would need
  status propagation (short-lived mandates, status lists or push invalidation).
- **Phase 1 placeholders remain.** The Phase 1 authorization-only tools (`payment.request_fee_payment`,
  `residency.prepare_renewal`) are still registered for the Phase 1 demo.
- There is one active key per agent and no rotation workflow. Re-running with a deleted `.dev_keys/` rotates all keys
  and re-issues mandates.
- There is no rate limiting. A flood of signed requests would grow the audit log.
- Agent status changes made via the CLI last until the next server start, which reseeds the synthetic registry.
- WAKALA limits what an agent *can do*. It does not make the agent's reasoning correct, and it does not prevent misuse of
  data an agent was legitimately allowed to read.
- Mandates are technical authorization artefacts, not legally recognised powers of attorney.
