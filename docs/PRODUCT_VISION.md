# WAKALA Product Vision

**WAKALA | وكالة — Autonomous AI. Accountable Authority.**

## The problem

Government entities are deploying AI agents that read records, call tools, delegate to other agents and initiate
sensitive operations such as payments. Today, an agent's authority usually comes from *where it runs*: a service account
inside a trusted network with broad API access. That model breaks down for agentic AI:

- An agent can be steered by the content it reads (prompt injection), so its intentions cannot be trusted.
- When an agent acts, it is often unclear **who owns it**, **who is accountable** and **what it was permitted to do**.
- When tasks pass between agents, authority tends to spread rather than shrink.
- Citizens have no visibility into which automated systems acted on their behalf.

## The idea

*Wakala* (وكالة) means agency or delegated authority. WAKALA applies the familiar logic of a narrowly scoped power of
attorney to software agents. This is a conceptual analogy, not a legal instrument.

1. **Verifiable agent identity.** Each agent has a passport: an owning entity, a named accountable officer, a risk
   level and a cryptographic key.
2. **Digitally signed, task-limited mandates.** Authority is granted for one citizen, one request, specific tools,
   explicit limits and a short lifetime.
3. **Independent authorization checkpoints.** A deterministic gateway checks every sensitive action. The default answer
   is no.
4. **Non-expanding delegation.** An agent can hand on only a subset of what it holds.
5. **Audit and human intervention.** Every decision is recorded with its evidence. Officers can escalate, approve or
   revoke in real time.
6. **Citizen transparency.** A plain-language receipt shows who acted, under which mandate, and what was refused.

## Positioning

WAKALA is a **security and authorization layer**. It is not:

- **An AI chatbot or agent framework.** WAKALA sits in front of protected services and works with any agent runtime.
- **A prompt-injection classifier.** Classifiers are probabilistic and can be evaded. WAKALA assumes injections will
  sometimes succeed and makes them unable to cause unauthorized actions.
- **An LLM-based judge.** No external model takes part in a security decision.

## Who it serves

| Stakeholder | Value |
|---|---|
| Government service owners | Deploy agents with bounded, provable authority |
| Cybersecurity teams | Clear trust boundaries, typed denial reasons and tamper-evident audit |
| Accountable officers | Named ownership, escalation and instant revocation |
| Citizens | Transparency into automated actions taken on their behalf |
| Auditors and regulators | A complete, verifiable record of who authorized what |

## Demonstration story

Mariam (synthetic citizen `C-1001`) renews her residency. Three agents cooperate, and each step is allowed only
because a signed mandate covers it. A tampered copy of her document hides an instruction to transfer AED 50,000. Even
if the agent is fooled, the gateway refuses, the refusal is audited, and Mariam's receipt shows it.

## Roadmap

| Phase | Outcome |
|---|---|
| 0 | Engineering foundation: contracts, synthetic environment, console shell *(complete)* |
| 1 | Ed25519 identity, signed mandates, default-deny gateway, protected execution, hash-chained audit *(complete — development prototype)* |
| 2 | Protected synthetic government services, case-specific authority, simulated agent adapters *(complete — development prototype)* |
| 3 | Signed delegation, officer console, LLM adapters, adversarial runs, citizen receipts |
| 4 | Measured benchmarks from real runs |

## Principles

Working code over elaborate descriptions. Real enforcement over simulated security claims. Clear architecture over
unnecessary complexity. Measured results over invented numbers.
