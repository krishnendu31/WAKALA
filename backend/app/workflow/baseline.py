"""INTENTIONALLY WEAK, TEST-ONLY BASELINE — for comparison, never for use.

Models a simplistic role-based access check: "an agent with the insurance
role may read insurance records". There is no request signature, no mandate,
no case binding and no citizen scope.

It is deliberately weaker than WAKALA and does NOT represent all real
government access-management systems. It is fully isolated: it holds its own
in-memory copy of the synthetic citizen fixtures, never touches WAKALA's
database, gateway, services, mandates or audit trail, and keeps its own log.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from app.services.seed import load_dataset

BASELINE_ROLES: dict[str, set[str]] = {
    "AGT-RES-001": {"residency.read"},
    "AGT-INS-001": {"insurance.read"},
    "AGT-PAY-001": {"payment.create"},
}


@dataclass
class WeakRoleBaseline:
    log: list[dict[str, Any]] = field(default_factory=list)

    def __post_init__(self) -> None:
        # Separate copy loaded straight from the fixture files.
        self._citizens = {c.citizen_ref: c for c in load_dataset().citizens}

    def read_insurance(self, claimed_agent_id: str, citizen_ref: str, at: datetime) -> dict[str, Any]:
        allowed = "insurance.read" in BASELINE_ROLES.get(claimed_agent_id, set())
        record = self._citizens.get(citizen_ref)
        entry = {"at": at.isoformat(), "claimed_agent_id": claimed_agent_id, "operation": "insurance.read",
                 "citizen_ref": citizen_ref, "allowed": allowed and record is not None,
                 "checks_performed": ["role has insurance.read"]}
        self.log.append(entry)
        if not entry["allowed"] or record is None:
            return {**entry, "returned_data": None}
        ins = record.insurance
        return {**entry, "returned_data": {
            "citizen_ref": record.citizen_ref, "full_name": record.full_name, "policy_ref": ins.policy_ref,
            "provider": ins.provider, "status": ins.status,
            "valid_until": ins.valid_until.isoformat() if ins.valid_until else None,
        }}
