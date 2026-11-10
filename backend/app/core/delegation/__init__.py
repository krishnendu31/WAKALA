"""Mandate chains: verifiable, non-expanding agent-to-agent delegation.

* ``tasks``  — trusted catalogue of delegable tasks → permitted receiving operations
* ``chain``  — pure verification of a resolved chain (signatures, issuer trust,
               ancestor validity, non-expansion, depth, cycles, case binding)

Child mandates are issued only by the delegation service after the gateway
has authorized a signed ``delegation.commission_task`` request.
"""

from .chain import check_non_expansion, task_resources, verify_chain
from .interfaces import DelegationValidator
from .tasks import COMMISSION_TOOL, GLOBAL_MAX_DELEGATION_DEPTH, TASK_CATALOG, DelegableTask

__all__ = [
    "COMMISSION_TOOL",
    "GLOBAL_MAX_DELEGATION_DEPTH",
    "TASK_CATALOG",
    "DelegableTask",
    "DelegationValidator",
    "check_non_expansion",
    "task_resources",
    "verify_chain",
]
