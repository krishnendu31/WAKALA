# Behaviour Watch 2.0 — recovery regression (before / after)

Generated 2026-11-10T15:11:33.448507+00:00 · commit `4440f91bd9` (phase-6-intelligent-assurance, dirty=False) · 20 incidents per condition, identical traffic.

| Policy | Condition | Recovered | Legit. denied | Legit. held unexpectedly | REQUEST_RATE incidents | Containment |
|---|---|---|---|---|---|---|
| phase5-original | independent_incidents | 20/20 | 0 | 0 | 0 | {'suspended': 20, 'revoked': 0, 'none': 0} |
| phase5-original | back_to_back_shared | 2/20 | 24 | 10 | 35 | {'suspended': 2, 'revoked': 1, 'none': 0} |
| watch-2.0 | independent_incidents | 20/20 | 0 | 0 | 0 | {'suspended': 20, 'revoked': 0, 'none': 0} |
| watch-2.0 | back_to_back_shared | 20/20 | 0 | 0 | 0 | {'suspended': 2, 'revoked': 18, 'none': 0} |

## What changed
- REQUEST_RATE counts one agent's requests within ONE case (threshold unchanged: 30 per 60 s). Agent-wide volume is a separate AGENT_REQUEST_VOLUME signal (60 per 60 s) that never contains a case; spread over >=5 cases with <=10% denials it is recorded as OBSERVE (legitimate batch).
- REPEATED_DENIALS spread over several cases becomes an agent-level ALERT instead of being attached to the latest case; inside one case the Phase 5 behaviour is unchanged.
- ALERT-level incidents never require approval or contain anything; approval gating considers only incidents at REQUIRE_APPROVAL or above.

## Failures under the original policy (shared condition)
- incident 3: failed at `9_unrelated_case_unaffected` — None
- incident 4: failed at `1_valid_case_initiated` — legitimate setup request held for approval: REQUEST_RATE
- incident 5: failed at `1_valid_case_initiated` — legitimate setup request held for approval: REQUEST_RATE
- incident 6: failed at `1_valid_case_initiated` — legitimate setup request held for approval: REQUEST_RATE
- incident 7: failed at `1_valid_case_initiated` — legitimate setup request held for approval: REQUEST_RATE
- incident 8: failed at `1_valid_case_initiated` — legitimate setup request held for approval: REQUEST_RATE
- incident 9: failed at `1_valid_case_initiated` — legitimate setup request held for approval: REQUEST_RATE
- incident 10: failed at `1_valid_case_initiated` — setup request denied
- incident 11: failed at `1_valid_case_initiated` — setup request denied
- incident 12: failed at `1_valid_case_initiated` — setup request denied
- incident 13: failed at `1_valid_case_initiated` — setup request denied
- incident 14: failed at `1_valid_case_initiated` — setup request denied
- incident 15: failed at `1_valid_case_initiated` — setup request denied
- incident 16: failed at `1_valid_case_initiated` — setup request denied
- incident 17: failed at `1_valid_case_initiated` — setup request denied
- incident 18: failed at `1_valid_case_initiated` — setup request denied
- incident 19: failed at `1_valid_case_initiated` — setup request denied
- incident 20: failed at `1_valid_case_initiated` — setup request denied

Escalation note: under watch-2.0 the same attacking agent's third cross-citizen attempt within 30 min escalates to critical, so most affected child mandates are revoked rather than suspended. Recovery still completes through a replacement agent. Times are machine time with automated officer calls.
