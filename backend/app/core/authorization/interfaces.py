from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

from app.schemas import ActionRequest, DigitalMandate

if TYPE_CHECKING:
    from app.core.identity import AuthenticatedPrincipal

    from .engine import PolicyContext, PolicyEvaluation


class PolicyDecisionPoint(Protocol):
    def __call__(
        self,
        request: ActionRequest,
        principal: "AuthenticatedPrincipal | None",
        mandate: DigitalMandate | None,
        ctx: "PolicyContext",
    ) -> "PolicyEvaluation":
        """Must return allowed=False unless every check positively passes."""
        ...
