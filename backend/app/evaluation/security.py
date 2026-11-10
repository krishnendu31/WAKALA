"""Run the labeled dataset through configurations A, B and C (each in its own isolated state)."""

from __future__ import annotations

import time
from dataclasses import asdict
from typing import Any

from .baseline import RoleOnlyBaseline
from .dataset import DatasetConfig, DatasetItem, generate
from .environment import isolated_env
from .harness import WakalaHarness
from .metrics import summarize

CONFIG_DESCRIPTIONS = {
    "A": "Intentionally weak role-only baseline: trusts the claimed identity; checks only that the role includes the "
         "operation. Own in-memory state; never touches WAKALA. Not representative of all real IAM systems.",
    "B": "WAKALA case-bound authorization with direct case mandates (no delegated operations). Real gateway, isolated "
         "in-memory state. Delegation-only categories are not applicable.",
    "C": "Full WAKALA: delegated authority via WAKALA-signed child mandates, verified chains, revocation/suspension, "
         "replay protection, assurance monitoring (policy 'monitor'). Real gateway, isolated in-memory state.",
}


def _row(item: DatasetItem, config: str, res: dict[str, Any]) -> dict[str, Any]:
    return {"item_id": item.item_id, "config": config, "category": item.category, "variant": item.variant,
            "label": item.label, "family": item.family, **res}


def run_security(config: DatasetConfig, configs: tuple[str, ...] = ("A", "B", "C"),
                 progress: Any = None) -> dict[str, Any]:
    items = generate(config)
    outcomes: dict[str, list[dict[str, Any]]] = {}
    meta: dict[str, Any] = {}
    for name in configs:
        t0 = time.perf_counter()
        if name == "A":
            base = RoleOnlyBaseline()
            outcomes[name] = [_row(i, name, base.evaluate(i)) for i in items]
            meta[name] = {"setup_requests": 0, "cases_created": 0, "baseline_state": base.state}
        else:
            with isolated_env("memory") as (env, clock, keys):
                h = WakalaHarness(env, clock, keys, name)
                rows = []
                for n, i in enumerate(items, 1):
                    rows.append(_row(i, name, h.evaluate(i)))
                    if progress and n % 100 == 0:
                        progress(f"{name}: {n}/{len(items)}")
                outcomes[name] = rows
                chain = env.audit.verify()
                meta[name] = {"setup_requests": h.setup_requests, "cases_created": h.cases_created,
                              "audit_events": chain.event_count, "audit_chain_valid": chain.valid,
                              "incidents_opened": len(env.assurance.incidents.list(limit=100000))}
        meta[name]["wall_seconds"] = round(time.perf_counter() - t0, 2)
        meta[name]["description"] = CONFIG_DESCRIPTIONS[name]
    return {
        "dataset_config": asdict(config),
        "items": items,
        "outcomes": outcomes,
        "summaries": {k: {**summarize(k, v), "run": meta[k]} for k, v in outcomes.items()},
    }
