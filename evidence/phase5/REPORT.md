# WAKALA Phase 5 — Security, performance and efficiency evaluation

> **Synthetic prototype benchmark — not production government statistics.** Every figure below is generated from `summary.json`; nothing is typed by hand.

Run: seed `20260`, 1200 labeled requests, dataset SHA-256 `3fdb6a2824238a3c…`, commit `f96d7aac3b`, started 2026-11-10T09:00:01.257526+00:00.

## 1. What was evaluated

- **1200 authorization requests** (480 legitimate, 720 unauthorized; 1107 agent tool calls, 93 officer actions). These are individual protected requests, **not** 1200 government applications.
- Each request was evaluated on its own freshly prepared synthetic case. Preparing those cases took 2787 (B) and 4205 (C) additional legitimate setup requests, which are not part of the labeled dataset.
- Labels come from the request category (what the request *is*), never from any configuration's decision.

| Category | Label | Count |
|---|---|---|
| normal_renewal_completion | legitimate | 94 |
| valid_delegated_task | legitimate | 94 |
| valid_task_commission (delegation only) | legitimate | 63 |
| legitimate_fee_payment | legitimate | 94 |
| legitimate_eligibility_check | legitimate | 94 |
| legitimate_officer_action | legitimate | 41 |
| wrong_citizen_access | unauthorized | 58 |
| wrong_case_mandate | unauthorized | 52 |
| unauthorized_tool | unauthorized | 58 |
| excessive_payment | unauthorized | 53 |
| unauthorized_payment_recipient | unauthorized | 52 |
| tampered_signature | unauthorized | 52 |
| forged_agent_identity | unauthorized | 53 |
| expired_mandate | unauthorized | 46 |
| revoked_mandate | unauthorized | 46 |
| replayed_request | unauthorized | 53 |
| delegation_privilege_escalation (delegation only) | unauthorized | 53 |
| forged_child_mandate (delegation only) | unauthorized | 46 |
| revoked_ancestor_mandate (delegation only) | unauthorized | 46 |
| unauthorized_officer_action | unauthorized | 52 |

## 2. Configurations

- **A** — Intentionally weak role-only baseline: trusts the claimed identity; checks only that the role includes the operation. Own in-memory state; never touches WAKALA. Not representative of all real IAM systems.
- **B** — WAKALA case-bound authorization with direct case mandates (no delegated operations). Real gateway, isolated in-memory state. Delegation-only categories are not applicable.
- **C** — Full WAKALA: delegated authority via WAKALA-signed child mandates, verified chains, revocation/suspension, replay protection, assurance monitoring (policy 'monitor'). Real gateway, isolated in-memory state.

Baseline bias: A is intentionally weak (a lower bound). Many real IAM deployments add attribute checks, signed tokens or sessions, so A's numbers must not be read as representative of existing government systems. B is the fairest comparison for case binding; C adds delegation.

## 3. Security outcomes (ground truth × outcome)

| Measure | A · role-only | B · case-bound | C · full WAKALA |
|---|---|---|---|
| Requests evaluated (applicable) | 1200 | 992 | 1200 |
| Unauthorized operations executed | 624/720 (86.7%) | 0/575 (0.0%) | 0/720 (0.0%) |
| Unauthorized operations prevented | 96/720 (13.3%) | 575/575 (100.0%) | 720/720 (100.0%) |
| Unauthorized incorrectly permitted | 624/720 (86.7%) | 0/575 (0.0%) | 0/720 (0.0%) |
| Legitimate operations allowed | 480/480 (100.0%) | 376/417 (90.2%) | 480/480 (100.0%) |
| Legitimate incorrectly denied | 0/480 (0.0%) | 41/417 (9.8%) | 0/480 (0.0%) |
| Delegation escalation prevented | 27/99 (27.3%) | n/a (0 applicable) | 99/99 (100.0%) |
| Revocation effectiveness | 0/92 (0.0%) | 46/46 (100.0%) | 92/92 (100.0%) |
| Unauthorized state mutations | 624/720 (86.7%) | 0/575 (0.0%) | 0/720 (0.0%) |
| Audit evidence complete | 0/1200 (0.0%) | 992/992 (100.0%) | 1200/1200 (100.0%) |

Not applicable in B (delegation-only categories): 208 requests. Harness errors: A 0, B 0, C 0.

### By category (prevention for unauthorized; completion for legitimate)

| Category | A | B | C | C monitoring detection (specific rule) |
|---|---|---|---|---|
| normal_renewal_completion | 94/94 (100.0%) | 94/94 (100.0%) | 94/94 (100.0%) | 0/94 (0.0%) |
| valid_delegated_task | 94/94 (100.0%) | 94/94 (100.0%) | 94/94 (100.0%) | 0/94 (0.0%) |
| valid_task_commission | 63/63 (100.0%) | n/a (0 applicable) | 63/63 (100.0%) | 0/63 (0.0%) |
| legitimate_fee_payment | 94/94 (100.0%) | 94/94 (100.0%) | 94/94 (100.0%) | 0/94 (0.0%) |
| legitimate_eligibility_check | 94/94 (100.0%) | 94/94 (100.0%) | 94/94 (100.0%) | 0/94 (0.0%) |
| legitimate_officer_action | 41/41 (100.0%) | 0/41 (0.0%) | 41/41 (100.0%) | 0/41 (0.0%) |
| wrong_citizen_access | 0/58 (0.0%) | 58/58 (100.0%) | 58/58 (100.0%) | 58/58 (100.0%) |
| wrong_case_mandate | 0/52 (0.0%) | 52/52 (100.0%) | 52/52 (100.0%) | 51/52 (98.1%) |
| unauthorized_tool | 58/58 (100.0%) | 58/58 (100.0%) | 58/58 (100.0%) | 56/58 (96.6%) |
| excessive_payment | 0/53 (0.0%) | 53/53 (100.0%) | 53/53 (100.0%) | 52/53 (98.1%) |
| unauthorized_payment_recipient | 0/52 (0.0%) | 52/52 (100.0%) | 52/52 (100.0%) | 51/52 (98.1%) |
| tampered_signature | 0/52 (0.0%) | 52/52 (100.0%) | 52/52 (100.0%) | 52/52 (100.0%) |
| forged_agent_identity | 0/53 (0.0%) | 53/53 (100.0%) | 53/53 (100.0%) | 51/53 (96.2%) |
| expired_mandate | 0/46 (0.0%) | 46/46 (100.0%) | 46/46 (100.0%) | 42/46 (91.3%) |
| revoked_mandate | 0/46 (0.0%) | 46/46 (100.0%) | 46/46 (100.0%) | 46/46 (100.0%) |
| replayed_request | 0/53 (0.0%) | 53/53 (100.0%) | 53/53 (100.0%) | 53/53 (100.0%) |
| delegation_privilege_escalation | 27/53 (50.9%) | n/a (0 applicable) | 53/53 (100.0%) | 53/53 (100.0%) |
| forged_child_mandate | 0/46 (0.0%) | n/a (0 applicable) | 46/46 (100.0%) | 46/46 (100.0%) |
| revoked_ancestor_mandate | 0/46 (0.0%) | n/a (0 applicable) | 46/46 (100.0%) | 46/46 (100.0%) |
| unauthorized_officer_action | 11/52 (21.2%) | 52/52 (100.0%) | 52/52 (100.0%) | 0/52 (0.0%) |

### False denials and their reasons

- **B**: 41 × `legitimate_officer_action: OUT_OF_ENTITY_SCOPE`
- **C**: none.
- In B, direct case mandates carry no signed `case_id`, so an entity-scoped case officer cannot be authorized against them (`OUT_OF_ENTITY_SCOPE`); only a supervisor with all-entity scope could act. This is a measured design consequence, not a bug in the benchmark.

## 4. Prevention vs. monitoring detection (configuration C)

Prevention = the request was not executed. Detection = a deterministic monitoring rule fired on the audited decision. They are separate:
- Unauthorized requests with a specific rule alert: 657/720 (91.2%); escalated to the officer queue: 657/720 (91.2%).
- Legitimate requests with a specific rule alert (false alarms): 0/480 (0.0%).
- Any rule including REQUEST_RATE: unauthorized 659/720 (91.5%), legitimate 434/480 (90.4%). REQUEST_RATE fires on machine-speed benchmark traffic, which is why it is reported separately.
- Rule hits: ACTION_AFTER_REVOCATION 92, CREDENTIAL_FAILURES 154, CROSS_CITIZEN_ACCESS 58, REPEATED_DENIALS 652, REQUEST_RATE 1029, UNAUTHORIZED_DELEGATION 79.
- Categories with no dedicated rule (e.g. expired mandates) are prevented by authorization but not detected by monitoring.

## 5. Latency (median / p95 / p99 ms)

**Microbenchmarks (in-memory, pure functions):**
- Authentication + Ed25519 request signature verification: 0.70 / 0.86 / 0.95 (mean 0.66, n=500)
- Delegation chain verification (2 links): 0.81 / 1.02 / 1.12 (mean 0.80, n=500)

| Integration (single thread) | SQLite :memory: | SQLite file (persisted) |
|---|---|---|
| Direct-mandate decision only | 3.42 / 4.84 / 5.30 (mean 3.57, n=500) | 17.44 / 23.02 / 26.15 (mean 18.11, n=500) |
| Direct-mandate full gateway authorization | 18.68 / 27.00 / 29.55 (mean 18.90, n=500) | 54.80 / 73.29 / 91.50 (mean 56.29, n=500) |
| Delegated-mandate decision only | 4.01 / 5.85 / 6.46 (mean 4.30, n=500) | 18.50 / 24.72 / 28.34 (mean 19.20, n=500) |
| Delegated-mandate full gateway authorization | 19.16 / 27.50 / 31.00 (mean 19.74, n=500) | 55.77 / 74.30 / 89.95 (mean 57.11, n=500) |
| Protected tool execution (execute) | 35.86 / 46.46 / 52.39 (mean 36.99, n=40) | 182.83 / 208.81 / 215.76 (mean 184.46, n=40) |
| End-to-end case (intake → COMPLETED) | 202.67 / 258.20 / 292.35 (mean 206.99, n=40) | 890.56 / 1044.42 / 1455.38 (mean 889.29, n=40) |

Definitions: *decision_only*: Gateway-measured time for authentication + policy + approval gate (excludes audit write and monitoring). *gateway_wall*: Full Gateway.authorize call: decision + hash-chained audit write + monitoring observer. *gateway_execute_wall*: Gateway.execute: authorization + protected service dispatch + transactional outcome audit. *end_to_end_case*: Machine time from intake to COMPLETED with simulated agents; no human time, no network.

## 6. Scalability stress

Probe: direct-mandate residency.check_eligibility via Gateway.authorize (decision + audit + monitoring), file SQLite.

- **active cases**: 1 → median 45.3 ms, p95 63.1 ms, errors 0; 501 → median 56.3 ms, p95 67.4 ms, errors 0; 2001 → median 97.8 ms, p95 129.6 ms, errors 0
- **registered agents**: 3 → median 41.2 ms, p95 50.3 ms, errors 0; 1003 → median 49.7 ms, p95 60.0 ms, errors 0; 5003 → median 52.9 ms, p95 66.1 ms, errors 0
- **audit records**: 0 → median 46.0 ms, p95 69.3 ms, errors 0, full chain verify 0 ms; 10000 → median 48.6 ms, p95 58.2 ms, errors 0, full chain verify 873 ms; 40000 → median 51.1 ms, p95 62.2 ms, errors 0, full chain verify 3354 ms
- **agent history**: 1 → median 42.5 ms, p95 50.0 ms, errors 0; 500 → median 57.5 ms, p95 71.7 ms, errors 0; 2000 → median 111.3 ms, p95 173.2 ms, errors 0
- **concurrency** (threads → throughput, median latency, errors, observer failures): 1 → 19.8 req/s, 49 ms, 0, 0; 2 → 16.2 req/s, 123 ms, 0, 0; 4 → 14.8 req/s, 263 ms, 0, 0; 8 → 13.8 req/s, 571 ms, 0, 0
- **delegation depth**: global max 3, current grant permits 1; depth 1 median 49.3 ms; depth-2 attempt allowed=False (DENY_DELEGATION_NOT_PERMITTED, DENY_SCOPE_VIOLATION, DENY_DELEGATION_DEPTH_EXCEEDED).

**Bottlenecks identified:**
1. *Single SQLite connection behind one process lock*: throughput does not rise with threads; latency rises roughly linearly with concurrency.
2. *Durable commits*: the file database uses SQLite defaults (rollback journal, synchronous=FULL); each audited decision commits, so persisted latency is several times the in-memory latency. Not tuned for this benchmark.
3. *Monitoring observer lookback* (found and fixed in Phase 5): it used to parse every event of the agent in the 30-minute window on every decision, so latency grew linearly with an agent's recent history (development probe on this machine: mean 11.8 ms after 200 decisions → 82.4 ms after 1,200). It now reads at most 120 recent decisions + 120 recent denials via composite indexes; see `agent_history` above.
4. *Concurrent incident updates* (found and fixed): incident compare-and-swap conflicts dropped monitoring updates under 8 threads; updates are now serialised in-process with bounded retry (`monitoring_observer_failures` above).
5. *Full audit-chain verification is O(n)* (see audit records series).

## 7. Service continuity (recovery benchmark)

**independent incidents** — Each incident in its own fresh isolated environment (no cross-incident history).
- Recovery success: 20/20 (100.0%); containment actions {'suspended': 20, 'revoked': 0, 'none': 0}; denial → completion 94.00 / 104.39 / 107.18 (mean 92.69, n=20); REQUEST_RATE incidents during run: 0; audit chain valid: True.
- Per step: 1 20/20 (100.0%), 2 20/20 (100.0%), 3 20/20 (100.0%), 4 20/20 (100.0%), 5 20/20 (100.0%), 6 20/20 (100.0%), 7 20/20 (100.0%), 8 20/20 (100.0%), 9 20/20 (100.0%)

**back to back shared** — All incidents back-to-back at machine speed in ONE environment: same agents, rules see the accumulated history (stress condition).
- Recovery success: 2/20 (10.0%); containment actions {'suspended': 2, 'revoked': 1, 'none': 0}; denial → completion 100.72 / 121.13 / 121.13 (mean 102.68, n=3); REQUEST_RATE incidents during run: 35; audit chain valid: True.
- Per step: 1 3/20 (15.0%), 2 3/20 (15.0%), 3 3/20 (15.0%), 4 3/20 (15.0%), 5 3/20 (15.0%), 6 3/20 (15.0%), 7 3/20 (15.0%), 8 3/20 (15.0%), 9 2/20 (10.0%)
- Failures: 1 × 9_unrelated_case_unaffected: None; 6 × 1_valid_case_initiated: legitimate setup request held for approval: REQUEST_RATE; 11 × 1_valid_case_initiated: setup request denied

Interpretation of the back-to-back failures: at machine speed the REQUEST_RATE rule opens incidents on the agent's latest case; under the `contain` policy the approval gate then holds sensitive steps on that case, so legitimate cases stall awaiting approval. This is a real weakness of attaching an agent-wide volume rule to a single case; it is reported, not tuned away. Repeated cross-citizen attempts by the same agent escalate to *critical*, which revokes (rather than suspends) the affected child mandate.

## 8. Efficiency model (hypothetical)

HYPOTHETICAL MODEL — every input is an assumption, not an observed government statistic. Default inputs are illustrative placeholders for the calculator, not facts: annual_agent_operations=100000, manual_review_pct=20.0, manual_review_minutes=6.0, staff_cost_per_fte_year=300000.0, productive_hours_per_fte_year=1700.0, wakala_exception_review_pct=2.0, exception_review_minutes=6.0, legally_required_review_pct=0.0, annual_platform_and_integration_cost=250000.0, currency=AED.
With these assumptions: routine manual reviews avoided 18000.0, review hours avoided 1800.0, hypothetical annual cost difference 67647.06 AED, break-even at 78704.0 operations/year. WAKALA does not decide visa eligibility and does not change approval rates. Human review required by law or policy is kept in both scenarios (legally_required_review_pct). Exception rates observed in the synthetic benchmark depend on its attack mix and are not a forecast.

## 9. Environment

- platform: Windows-11-10.0.26300-SP0
- os: Windows
- machine: AMD64
- cpu: AMD Ryzen 7 5700U with Radeon Graphics
- logical_cpus: 16
- memory_total_gb: 21.8
- python: 3.13.14
- python_implementation: CPython
- sqlite: 3.50.4
- process_model: single Python process; SQLite access serialized by one lock
- execution_environment: local developer machine (not a server, not a cloud benchmark host)
- phase timings (s): {'security_seconds': 714.9, 'latency_seconds': 125.7, 'stress_seconds': 911.0, 'recovery_seconds': 34.6}

## 10. Limitations and threats to validity

- Synthetic data, simulated deterministic agents and a single-process prototype; no real government system, network or HSM.
- Attack categories are those we designed; the dataset over-represents attacks (~60%) to measure prevention, so rates are per category, not a traffic forecast.
- Construct validity: 'prevented' means the gateway did not execute the request; it says nothing about attacks outside the modelled categories (e.g. insider abuse of legitimately granted data).
- Baseline A is a deliberately weak strawman lower bound; B isolates the contribution of case binding; neither represents any specific production IAM.
- Each request runs on a fresh case, which removes interactions between requests (except monitoring history, which is shared and measured).
- Monitoring uses the 'monitor' policy in the request benchmark; containment is measured only in the recovery benchmark.
- Clock offsets are used to present expired mandates and idle sessions; everything else uses real time.
- Latency is wall-clock on one developer laptop, single process, Python; it must not be extrapolated to national capacity.
- Recovery timings use automated officer calls and exclude human review time, which dominates real recoveries.
- Business figures are a calculator over user assumptions; they are not observed savings.

## 11. Reproduce

```bash
cd backend
.venv\Scripts\python -m app.evaluation.run --seed 20260 --size 1200 --out ../evidence/phase5
```

Same seed and size → identical `dataset.json` (SHA-256 above). Decisions are deterministic for a given code version; latency varies by machine.
