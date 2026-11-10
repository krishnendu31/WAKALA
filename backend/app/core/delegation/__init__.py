"""Non-expanding delegation (implemented in Phase 2).

Rule: a child mandate may only *narrow* its parent. For child C of parent P:

* C.allowed_tools is a subset of P.allowed_tools
* C.denied_tools is a superset of P.denied_tools
* C.citizen_or_request_scope == P.citizen_or_request_scope
* C.amount_limit <= P.amount_limit, C.recipient_allowlist subset of P's
* C.expires_at <= P.expires_at, and P is itself valid at time of use
"""

from .interfaces import DelegationValidator

__all__ = ["DelegationValidator"]
