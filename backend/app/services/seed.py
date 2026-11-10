"""Load, validate and seed the synthetic environment.

Every record passes through its Pydantic contract before it reaches the
database. Startup fails loudly on any invalid record or duplicate identifier
rather than serving partial or inconsistent data.
"""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from app.models.database import SEED_TABLES, Database
from app.schemas import AgentPassport, Citizen, DocumentFixture, GovernmentService, Scenario, TrustedIssuer
from app.schemas.assurance import Officer

DATA_DIR = Path(__file__).resolve().parent.parent / "data"


class SeedError(RuntimeError):
    """Raised when synthetic data is invalid or internally inconsistent."""


@dataclass(frozen=True)
class SyntheticDataset:
    agents: list[AgentPassport]
    citizens: list[Citizen]
    services: list[GovernmentService]
    documents: list[DocumentFixture]
    scenarios: list[Scenario]
    issuers: list[TrustedIssuer]
    standby_agents: list[AgentPassport] = None  # type: ignore[assignment]
    officers: list[Officer] = None  # type: ignore[assignment]


def _read_json(path: Path) -> dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise SeedError(f"missing data file: {path.name}") from exc
    except json.JSONDecodeError as exc:
        raise SeedError(f"invalid JSON in {path.name}: {exc}") from exc


def _assert_unique(items: list[BaseModel], key: str, label: str) -> None:
    counts = Counter(getattr(item, key) for item in items)
    dupes = sorted(k for k, n in counts.items() if n > 1)
    if dupes:
        raise SeedError(f"duplicate {label} identifiers: {dupes}")


def load_dataset(data_dir: Path = DATA_DIR) -> SyntheticDataset:
    try:
        agents = [AgentPassport.model_validate(a) for a in _read_json(data_dir / "agents.json")["agents"]]
        citizens = [Citizen.model_validate(c) for c in _read_json(data_dir / "citizens.json")["citizens"]]
        services = [GovernmentService.model_validate(s) for s in _read_json(data_dir / "services.json")["services"]]
        scenario_file = _read_json(data_dir / "scenarios.json")
        documents = []
        for raw in scenario_file["documents"]:
            content = (data_dir / "documents" / raw["filename"]).read_text(encoding="utf-8")
            documents.append(
                DocumentFixture.model_validate(
                    {**raw, "content": content, "sha256": hashlib.sha256(content.encode("utf-8")).hexdigest()}
                )
            )
        scenarios = [Scenario.model_validate(s) for s in scenario_file["scenarios"]]
        issuers = [TrustedIssuer.model_validate(i) for i in _read_json(data_dir / "issuers.json")["issuers"]]
        standby = [AgentPassport.model_validate(a) for a in _read_json(data_dir / "standby_agents.json")["agents"]] \
            if (data_dir / "standby_agents.json").exists() else []
        officers = [Officer.model_validate(o) for o in _read_json(data_dir / "officers.json")["officers"]] \
            if (data_dir / "officers.json").exists() else []
    except SeedError:
        raise
    except (KeyError, FileNotFoundError, ValueError) as exc:
        raise SeedError(f"invalid synthetic dataset: {exc}") from exc

    _assert_unique(agents, "agent_id", "agent")
    _assert_unique(citizens, "citizen_ref", "citizen")
    _assert_unique(services, "service_id", "service")
    _assert_unique(documents, "document_id", "document")
    _assert_unique(scenarios, "scenario_id", "scenario")
    _assert_unique(issuers, "issuer_id", "issuer")
    _assert_unique([*agents, *standby], "agent_id", "agent")
    _assert_unique(officers, "officer_id", "officer")

    # Referential integrity between fixtures.
    citizen_refs = {c.citizen_ref for c in citizens}
    service_ids = {s.service_id for s in services}
    document_ids = {d.document_id for d in documents}
    for doc in documents:
        if doc.citizen_ref not in citizen_refs:
            raise SeedError(f"document {doc.document_id} references unknown citizen {doc.citizen_ref}")
    for sc in scenarios:
        if sc.citizen_ref not in citizen_refs:
            raise SeedError(f"scenario {sc.scenario_id} references unknown citizen {sc.citizen_ref}")
        if sc.service_id not in service_ids:
            raise SeedError(f"scenario {sc.scenario_id} references unknown service {sc.service_id}")
        if sc.document_id not in document_ids:
            raise SeedError(f"scenario {sc.scenario_id} references unknown document {sc.document_id}")

    agent_ids = {a.agent_id for a in [*agents, *standby]}
    service_tools = {t for s in services for t in s.tools}
    for iss in issuers:
        auth = iss.authority
        if not set(auth.agents) <= agent_ids:
            raise SeedError(f"issuer {iss.issuer_id} references unknown agents")
        if not set(auth.services) <= service_ids:
            raise SeedError(f"issuer {iss.issuer_id} references unknown services")
        if not set(auth.tools) <= service_tools:
            raise SeedError(f"issuer {iss.issuer_id} references tools outside its services")
    key_ids = [a.identity_key_reference.key_id for a in [*agents, *standby]] + [i.key_id for i in issuers]
    if len(set(key_ids)) != len(key_ids):
        raise SeedError("key identifiers must be unique across agents and issuers")

    return SyntheticDataset(agents, citizens, services, documents, scenarios, issuers, standby, officers)


def seed_database(db: Database, dataset: SyntheticDataset) -> None:
    rows: dict[str, list[tuple[str, str]]] = {
        "agents": [(a.agent_id, a.model_dump_json()) for a in dataset.agents],
        "citizens": [(c.citizen_ref, c.model_dump_json()) for c in dataset.citizens],
        "services": [(s.service_id, s.model_dump_json()) for s in dataset.services],
        "documents": [(d.document_id, d.model_dump_json()) for d in dataset.documents],
        "scenarios": [(s.scenario_id, s.model_dump_json()) for s in dataset.scenarios],
        "issuers": [(i.issuer_id, i.model_dump_json()) for i in dataset.issuers],
        "standby_agents": [(a.agent_id, a.model_dump_json()) for a in (dataset.standby_agents or [])],
        "officers": [(o.officer_id, o.model_dump_json()) for o in (dataset.officers or [])],
    }
    with db.transaction() as conn:
        for table in SEED_TABLES:
            conn.execute(f"DELETE FROM {table}")  # table names come from a fixed tuple
            conn.executemany(f"INSERT INTO {table} VALUES (?, ?)", rows[table])
