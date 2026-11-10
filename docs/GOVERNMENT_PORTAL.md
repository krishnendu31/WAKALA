# Government AI Services Portal and the end-to-end demonstration

The portal (`/portal`) is a **fictional** citizen-facing service. It shows how an existing government entity could put
WAKALA in front of its AI agents. It is not an official government website and implies no affiliation. All citizens,
amounts and accounts are synthetic.

## How the portal talks to WAKALA

```
Citizen message ──▶ POST /api/portal/requests            (intake opens a delegated case, incident policy "contain")
                     └─ Residency Agent planner           model-driven (opt-in) or deterministic offline
                          proposes a tool from AGENT_TOOLS (strict schema)
                     └─ Orchestrator: validate → sign with the agent's own key under its case mandate → Gateway.execute()
                          · delegate_insurance_check → delegation.commission_task → WAKALA-signed child mandate
                                                      → Insurance Agent verifies under the child (its own identity)
                          · request_fee_payment      → Payment Agent, its own case-bound payment mandate (AED 500, treasury only)
                          · read_case_document       → Document Shield agent view only (withheld unless CLEAN/released)
Portal UI ◀── GET /api/portal/cases/{id} every 2 s        case store + audit trail + incidents + approvals + Document Shield
Security Operations ◀── /api/officer/* every 3 s          the SAME case IDs, decisions and incidents
```

The portal never sets a case state. Every step on the progress tracker reflects prerequisites that the protected
services recorded after the gateway allowed a signed request. The "What WAKALA verified" list is built from the
hash-chained audit events for the case. Each entry shows a plain-English sentence, and the technical reason codes are
under *Technical details*.

## Real AI model vs. deterministic

| Component | What runs |
|---|---|
| Residency Agent planner (portal) | **Model-driven when configured**: Anthropic Messages API through the official `anthropic` SDK, model `claude-opus-5-5`, manual tool-use loop. **Default: deterministic offline planner**, clearly labelled in the UI. |
| Insurance Agent, Payment Agent, standby agent | Deterministic simulated agents (their own Ed25519 identities and mandates) |
| Scene 2 cross-citizen request | Deterministic scripted Insurance Agent request through the real gateway |
| Scene 4 "gateway-bypass" test | **Simulated manipulated agent** (deterministic script, no LLM) |
| Scene 4 "real-model injection test" | Runs **only** with a configured model. Otherwise it returns `not_run`; the script is never passed off as a model. |

Enable the model (it is never on by default):

```bash
set WAKALA_AGENT_MODEL_PROVIDER=anthropic
set ANTHROPIC_API_KEY=<your key>
set WAKALA_AGENT_MODEL=claude-opus-5-5
```

Unset `ANTHROPIC_BASE_URL` too if your shell sets it for another tool, because the SDK honours it. Model calls cost
money on your Anthropic account.

**Guard-rails in the loop** (`backend/app/portal/agent.py`):
- At most 8 model turns and 12 tool calls.
- A 45 s request timeout and 1 retry.
- `tool_choice` is `auto`, and every tool is `strict: true`.
- Server-side fallbacks are enabled (`fallbacks: "default"`, beta `server-side-fallback-2026-07-01`).
- `stop_reason` is checked: `refusal`, `max_tokens` and `pause_turn` are handled.
- Every input is re-validated server-side before anything is signed.
- API, network, timeout or refusal errors end the run with an honest status, and the case does not advance.

The model has no tool to issue or edit mandates, change permissions or case ownership, touch the gateway or grant
officer authority. It holds no key or service credential, and its text is never treated as authorization.

**Live model status in this repository:** the code path is implemented and tested with a recording fake client. **No
live model test has been run in this environment**, because no `ANTHROPIC_API_KEY` was configured. The UI and API say
so instead of showing a result.

## Document Shield in the portal

Citizens attach PDFs to their case: `POST /api/portal/cases/{id}/documents`, or the synthetic samples.
1. Document Shield inspects each file and returns **CLEAN**, **REVIEW REQUIRED** or **QUARANTINED**.
2. The agent's `read_case_document` returns only the policy view. Quarantined or unreleased content comes back as
   `content: null`, and the agent proposes no action from document text.
3. An officer with `documents.review` may release a REVIEW document's visible text. A quarantined document cannot be
   released.
4. The original is preserved, read-only, with its SHA-256.

## Three-minute demonstration

Before you start, run the backend with `run_dev.py` and open `/portal`. Use **Open Security Operations side by side**,
or open `/soc` in a second window, and issue an officer password:

```bash
cd backend
.venv\Scripts\python -m app.devtools.cli officers set-password OFF-0101
```

**0:00 — Scene 1, normal service.**
1. Click **New demo session**, then **Send** "I want to renew my residency permit."
2. The assistant registers, checks eligibility and delegates insurance. The Insurance Agent runs under its child
   mandate and the Payment Agent collects AED 500 to the treasury, then the case completes.
3. The progress tracker turns green, and **What WAKALA verified** shows six *Allowed* decisions.
4. In **Delegation Network**, show the chain from case to root to child.

**0:40 — Scene 2, cross-citizen incident.**
1. Click **Run the unauthorized request**.
2. The portal shows *Security review in progress* and "Blocked: this AI agent was authorized to check insurance for
   Mariam, not another citizen's record (C-1003)."
3. Security Operations shows a new high-severity incident for the same case ID.

**1:20 — Scene 3, accountable recovery** (in Security Operations, signed in as OFF-0101):
1. Open the incident to show the citizen request, the verified chain (child **SUSPENDED**, roots authorized), the
   violated rule and the evidence.
2. **Mark under review**, then **Reassign → AGT-INS-002**, then **Resume case**.
3. In the portal, click **Continue my case**. The delegation is **held**.
4. In **Approvals**, click **Approve & re-authorize**. It is re-checked and executed.
5. **Resolve incident**, then **Continue my case** again. The case completes as *recovered*.
6. The unrelated case (C-1002) continues untouched.

Approve before you resolve. If the incident is resolved first, the hold ends by design and the held approval is left
pending. It can never execute: approving it later re-runs authorization, which denies it.

**2:20 — Scene 4, malicious PDF.**
1. Click **Attach hidden-text PDF**: it comes back **QUARANTINED**, with findings located in the hidden layer.
   **Inspect in Document Shield** shows the boxes.
2. Click **Gateway-bypass test (simulated agent)**. Both manipulated attempts are denied and the ledger count is
   unchanged.
3. Click **Real-model injection test**. With a model configured it records exactly what the model proposed; otherwise it
   reports *not run*.

**2:45 — Scene 5, real evidence.** Open **Security Evidence**:
- 1,200 labelled requests, with 0/720 unauthorized operations executed in full WAKALA and 0/480 false denials.
- Latency figures.
- Recovery **20/20 for independent incidents but 2/20 back-to-back at machine speed**: a known continuity limitation
  caused by the REQUEST_RATE rule under `contain`.

**Repeat.** **New demo session** starts a clean demo view. Nothing is deleted: earlier cases, incidents, approvals and
the audit trail remain as evidence. It works only in developer mode.

## Integrity properties verified by tests

`tests/test_portal_integration.py` covers:
- Portal actions run through `Gateway.execute()`: six signed steps, with audit references matching the trail.
- The child mandate's parent is the Residency root and it holds only the insurance tool. The Insurance Agent ran under
  it, and the Payment Agent under its own mandate.
- The same case, decision and incident appear in the portal and the officer API.
- Full officer recovery runs, including the held-and-approved delegation and the standby agent.
- The unrelated case completes.
- Quarantined text never reaches the model's context.
- The model tool schema is validated before signing.
- Unknown tools, such as "grant_officer_authority", never reach the gateway.
- Unauthorized model proposals (an external payment, another citizen) are denied with no ledger or prerequisite change.
- Model timeouts, refusals and runaway loops end honestly.
- The injection test is never faked without a model, and records both obey and refuse behaviour.
- The agent module has no direct service imports.
- The demo is repeatable, reset keeps the evidence, and reset and writes require developer mode.
- The config never exposes keys, and the frontend source and bundle contain no credentials.

## Limitations

- **No citizen authentication.** Portal writes are developer-mode, loopback-only demo endpoints.
- **Prototype security model.** Single process, SQLite and development keys, as in every earlier phase.
- **Untested live model.** The model-driven path is implemented but has not been exercised against a live model here.
  Model behaviour under injection is whatever the live run records.
- **Recovery is not always smooth.** A REQUEST_RATE incident can hold legitimate steps on `contain` cases at machine
  speed (see the Phase 5 report). Human-paced demos are unaffected.
- **Polling, not push.** The two views stay in sync by polling: 2 s for the portal and 3 s for the console.
