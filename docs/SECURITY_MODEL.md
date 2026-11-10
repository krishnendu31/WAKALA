# WAKALA Security Model (Phase 2)

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
| ⏳ Non-expanding delegation | Requests with a `delegation_chain` are denied until Phase 3 | — |
| ⏳ Authenticated officer console | Phase 3; officer actions are CLI-only today | — |

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

## 9a. Phase 2 audit semantics

For each protected service call there are two hash-chained events:

1. **Decision event**, written *before* execution. If it cannot be written, nothing runs.
2. **Execution event**, written *after* execution. It records the execution status, the case state afterwards, and a
   SHA-256 digest of the result; never the result itself.

If writing the execution event fails, the service change has already committed and the API returns 503. The decision
event still proves the action was authorized, but the outcome record is missing. Closing this gap needs a
transactional outbox in the same database transaction as the service write; it is not implemented.

## 10. Known limitations

- Local development prototype; `WAKALA_ENV=production` is refused.
- The gateway boundary is in-process; see §8 for production bypass prevention.
- The audit chain is not externally anchored (§7).
- **Phase 2 boundary is in-process.** Services are only reachable via the tool registry and have no HTTP routes, but
  code inside the backend process could import them directly. Production needs network-isolated services that verify
  a gateway-issued, action-bound token themselves.
- **Simulated agents.** The agents are deterministic scripts, not autonomous AI. No LLM adapter exists yet.
- **No officer authentication.** Officer actions (resume, revoke) are CLI-only. Console read endpoints for
  `/api/workflow/*` are restricted to loopback clients but have no user login.
- **Case intake is unauthenticated** apart from dev-mode, loopback and origin checks. It stands in for a front office
  and signs case mandates with development issuer keys.
- **Execution events are best-effort** after commit (see §9a).
- **No delegation.** Cross-agent delegation is not implemented; the three agents act under independent, case-scoped
  mandates issued by three issuers. This is **not** signed delegation.
- **Phase 1 placeholders remain.** The Phase 1 authorization-only tools (`payment.request_fee_payment`,
  `residency.prepare_renewal`) are still registered for the Phase 1 demo.
- There is one active key per agent and no rotation workflow. Re-running with a deleted `.dev_keys/` rotates all keys
  and re-issues mandates.
- There is no rate limiting. A flood of signed requests would grow the audit log.
- Agent status changes made via the CLI last until the next server start, which reseeds the synthetic registry.
- WAKALA limits what an agent *can do*. It does not make the agent's reasoning correct, and it does not prevent misuse of
  data an agent was legitimately allowed to read.
- Mandates are technical authorization artefacts, not legally recognised powers of attorney.
