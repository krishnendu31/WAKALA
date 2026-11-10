"""DEVELOPMENT-ONLY command-line utilities (never exposed over HTTP).

Run from backend/:  python -m app.devtools.cli <command>

    keys                         list registered public keys (fingerprints only)
    mandates list                list mandates with live verification status
    mandates verify <ID>         verify one mandate
    mandates issue               issue a fresh signed mandate for every agent
    mandates revoke <ID> [reason]
    mandates tamper-demo <ID>    show that modifying a signed mandate breaks verification
    agents set-status <AGENT_ID> <active|suspended|revoked|pending_review>
    cases list                   list renewal cases
    cases revoke-authority <CASE_ID> [reason]   revoke a case's mandates and all delegated children
    delegations list             list trusted delegation records
    agents revoke <AGENT_ID> [reason]           agent-wide revocation (persistent)
    audit reconcile              record outcomes for authorized-but-unrecorded executions
    bench delegation [N]         measure real authorization latency, direct vs delegated
    cases resume <CASE_ID>       officer resumes a case paused for review (audited)
    audit verify                 verify the audit hash chain
    audit tail [N]               show the last N audit events

Operates on WAKALA_DB_PATH (default backend/var/wakala.db), the same file the
running server uses, so revocations take effect immediately.
"""

from __future__ import annotations

import sys
from datetime import timedelta

from app.core.config import Settings
from app.core.mandates import verify_mandate
from app.devtools.issuance import ensure_dev_mandates
from app.schemas import Money
from app.services.bootstrap import WakalaEnvironment, bootstrap


def _env() -> WakalaEnvironment:
    settings = Settings.from_env()
    if settings.db_path == ":memory:":
        print("warning: WAKALA_DB_PATH is :memory: — changes will not reach a running server", file=sys.stderr)
    return bootstrap(settings, reseed=False, issue_mandates=False)


def _verify_line(env: WakalaEnvironment, mandate) -> str:  # type: ignore[no-untyped-def]
    now = env.clock()
    snap = env.gateway.policy_snapshot(now)
    v = verify_mandate(mandate, snap["issuers"], snap["issuer_public_keys"], now, snap["revoked_mandate_ids"])
    codes = ", ".join(c.value for c in v.integrity_codes + v.lifecycle_codes) or "-"
    return f"{'VALID  ' if v.valid else 'INVALID'} {v.effective_status:<13} {codes}"


def main(argv: list[str]) -> int:
    if not argv:
        print(__doc__)
        return 2
    env = _env()
    try:
        cmd, *rest = argv
        if cmd == "keys":
            for k in env.repo.list_keys():
                print(f"{k['key_id']:<28} {k['owner_type']:<7} {k['owner_id']:<20} {k['status']:<8} {k['fingerprint']}")
        elif cmd == "mandates" and rest[:1] == ["list"]:
            for s in env.mandates.list():
                m = s.mandate
                print(f"{m.mandate_id:<24} {m.agent_id:<12} exp {m.expires_at.isoformat()}  {_verify_line(env, m)}")
        elif cmd == "mandates" and rest[:1] == ["verify"] and len(rest) == 2:
            m = env.mandates.get(rest[1])
            if m is None:
                print("not found")
                return 1
            print(_verify_line(env, m))
        elif cmd == "mandates" and rest[:1] == ["issue"]:
            issued = ensure_dev_mandates(env.gateway, env.mandates, env.keystore, {i.issuer_id: i for i in env.repo.list_issuers()},
                                         env.clock(), timedelta(minutes=env.settings.dev_mandate_lifetime_minutes), force=True)
            for m in issued:
                print(f"issued {m.mandate_id} for {m.agent_id}, expires {m.expires_at.isoformat()}")
        elif cmd == "mandates" and rest[:1] == ["revoke"] and len(rest) >= 2:
            from app.services.revocation import revoke_mandate
            ids = revoke_mandate(env, rest[1], " ".join(rest[2:]) or "revoked via dev CLI")
            print(f"revoked {len(ids)} mandate(s) incl. delegated descendants: {', '.join(ids) or '-'}")
        elif cmd == "cases" and rest[:1] == ["revoke-authority"] and len(rest) >= 2:
            from app.services.revocation import revoke_case_authority
            ids = revoke_case_authority(env, rest[1], " ".join(rest[2:]) or "revoked via dev CLI")
            print(f"case {rest[1]} authority revoked; {len(ids)} mandate(s) revoked")
        elif cmd == "delegations" and rest[:1] == ["list"]:
            for d in env.mandates.delegations():
                print(f"{d['child_mandate_id']:<20} <- {d['parent_mandate_id']:<22} {d['from_agent']} -> {d['to_agent']} "
                      f"{d['task']:<30} depth {d['depth']} case {d['case_id']} revoked={env.mandates.is_revoked(str(d['child_mandate_id']))}")
        elif cmd == "agents" and rest[:1] == ["revoke"] and len(rest) >= 2:
            from app.services.revocation import revoke_agent
            revoke_agent(env, rest[1], " ".join(rest[2:]) or "revoked via dev CLI")
            print(f"{rest[1]} revoked (persistent across restarts)")
        elif cmd == "audit" and rest[:1] == ["reconcile"]:
            from app.services.reconciliation import reconcile_outcomes
            res = reconcile_outcomes(env)
            print(f"examined {res.examined} authorized decisions; recorded {len(res.recorded)}: {res.recorded}")
        elif cmd == "bench" and rest[:1] == ["delegation"]:
            from app.workflow.benchmark import run_delegation_benchmark
            print(run_delegation_benchmark(int(rest[1]) if len(rest) > 1 else 200))
        elif cmd == "mandates" and rest[:1] == ["tamper-demo"] and len(rest) == 2:
            m = env.mandates.get(rest[1])
            if m is None:
                print("not found")
                return 1
            print("original :", _verify_line(env, m))
            if m.amount_limit is not None:
                t = m.model_copy(update={"amount_limit": Money(amount="50000.00", currency="AED")})
                print("amount_limit 500.00 -> 50000.00 :", _verify_line(env, t))
            t2 = m.model_copy(update={"allowed_tools": [*m.allowed_tools, "payment.change_destination"]})
            print("extra allowed tool             :", _verify_line(env, t2))
            t3 = m.model_copy(update={"expires_at": m.expires_at + timedelta(hours=1)})
            print("expiry extended by 1h          :", _verify_line(env, t3))
            print("(in-memory only; the stored mandate is unchanged)")
        elif cmd == "agents" and rest[:1] == ["set-status"] and len(rest) == 3:
            a = env.repo.set_agent_status(rest[1], rest[2])  # type: ignore[arg-type]
            print(f"{a.agent_id} status = {a.status} (until next server restart reseeds the registry)")
        elif cmd == "cases" and rest[:1] == ["list"]:
            for c in env.cases.list():
                print(f"{c.case_id:<15} {c.citizen_ref:<7} {c.state.value:<18} {','.join(c.completed_prerequisites) or '-':<50} {c.recovery_status}")
        elif cmd == "cases" and rest[:1] == ["resume"] and len(rest) == 2:
            from app.workflow.officer import resume_case
            c = resume_case(env, rest[1], officer_id="OFF-0101")
            print(f"{c.case_id} resumed to {c.state.value} (recovery_status={c.recovery_status})")
        elif cmd == "audit" and rest[:1] == ["verify"]:
            r = env.audit.verify()
            print(f"valid={r.valid} events={r.event_count} head={r.head_hash} broken_at={r.first_broken_sequence} ({r.detail})")
        elif cmd == "audit" and rest[:1] == ["tail"]:
            n = int(rest[1]) if len(rest) > 1 else 10
            for e in env.audit.list(n):
                print(f"#{e.sequence} {e.timestamp.isoformat()} {e.actor:<16} {e.action:<30} {e.decision:<8} "
                      f"{','.join(c.value for c in e.reason_codes)}")
        else:
            print(__doc__)
            return 2
        return 0
    finally:
        env.close()


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
