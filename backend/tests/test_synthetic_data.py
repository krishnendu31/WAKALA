"""Synthetic dataset completeness, safety and duplicate detection."""

from __future__ import annotations

import json
import re
import shutil
from decimal import Decimal
from pathlib import Path

import pytest

from app.services.seed import DATA_DIR, SeedError, load_dataset

# Patterns that would indicate a realistic financial identifier slipped in.
IBAN_LIKE = re.compile(r"\bAE\d{2}\s?\d{3}")
LONG_DIGIT_RUN = re.compile(r"\d{10,}")


def test_five_citizens_including_mariam(dataset):
    assert len(dataset.citizens) == 5
    mariam = next(c for c in dataset.citizens if c.citizen_ref == "C-1001")
    assert mariam.full_name == "Mariam Al Hashimi"
    assert mariam.full_name_ar


def test_every_citizen_has_residency_insurance_and_attributes(dataset):
    for c in dataset.citizens:
        assert c.residency.permit_ref.startswith("SYNTH-RP-")
        assert c.insurance.policy_ref.startswith("SYNTH-INS-")
        assert c.service_attributes.outstanding_fines.currency == "AED"
        assert c.synthetic is True


def test_agent_inventory(dataset):
    ids = [a.agent_id for a in dataset.agents]
    assert ids == ["AGT-RES-001", "AGT-INS-001", "AGT-PAY-001"]
    for agent in dataset.agents:
        assert agent.accountable_officer.name
        assert agent.owner_entity
        assert agent.synthetic is True
        # Phase 0 honesty: no key material is claimed to exist yet.
        assert agent.identity_key_reference.provisioning_status == "not_provisioned"


def test_insurance_agent_cannot_pay(dataset):
    ins = next(a for a in dataset.agents if a.agent_id == "AGT-INS-001")
    assert not any(t.startswith("payment.") for t in ins.declared_tools)


def test_renewal_fee_is_synthetic_aed_500(dataset):
    (svc,) = dataset.services
    assert svc.fee.amount == Decimal("500.00")
    assert svc.fee.currency == "AED"
    assert svc.official_payment_destination == "SYNTH-GOV-TREASURY-0001"


def test_financial_references_are_unmistakably_fictional(dataset):
    refs = [c.account_ref for c in dataset.citizens] + [s.official_payment_destination for s in dataset.services]
    for ref in refs:
        assert ref.startswith("SYNTH-")
        assert not IBAN_LIKE.search(ref)
        assert not LONG_DIGIT_RUN.search(ref)
    for path in DATA_DIR.rglob("*"):
        if path.is_file():
            text = path.read_text(encoding="utf-8")
            assert not IBAN_LIKE.search(text), path.name
            assert not LONG_DIGIT_RUN.search(text), path.name


def test_two_document_fixtures_for_mariam(dataset):
    docs = {d.document_id: d for d in dataset.documents}
    assert set(docs) == {"DOC-C1001-RENEWAL", "DOC-C1001-INJECTED"}
    normal, injected = docs["DOC-C1001-RENEWAL"], docs["DOC-C1001-INJECTED"]
    assert normal.citizen_ref == injected.citizen_ref == "C-1001"
    assert not normal.contains_injected_instruction
    assert "50,000" not in normal.content
    assert injected.contains_injected_instruction
    assert "AED 50,000" in injected.content
    for doc in (normal, injected):
        assert doc.content.startswith("[SYNTHETIC DOCUMENT")
        assert doc.trust_classification == "untrusted_input"


def test_scenarios_load_and_are_not_executable(dataset):
    assert [s.scenario_id for s in dataset.scenarios] == ["SCN-001", "SCN-002"]
    assert all(s.execution_enabled is False for s in dataset.scenarios)


def test_every_data_file_carries_synthetic_notice():
    for name in ("agents.json", "citizens.json", "services.json", "scenarios.json"):
        notice = json.loads((DATA_DIR / name).read_text(encoding="utf-8"))["_notice"]
        assert "SYNTHETIC" in notice


@pytest.fixture()
def data_copy(tmp_path: Path) -> Path:
    target = tmp_path / "data"
    shutil.copytree(DATA_DIR, target)
    return target


def _mutate(path: Path, key: str, fn) -> None:
    data = json.loads(path.read_text(encoding="utf-8"))
    fn(data[key])
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")


def test_duplicate_agent_ids_rejected(data_copy):
    _mutate(data_copy / "agents.json", "agents", lambda items: items.append(dict(items[0])))
    with pytest.raises(SeedError, match="duplicate agent identifiers"):
        load_dataset(data_copy)


def test_duplicate_citizen_refs_rejected(data_copy):
    _mutate(data_copy / "citizens.json", "citizens", lambda items: items.append(dict(items[0])))
    with pytest.raises(SeedError, match="duplicate citizen identifiers"):
        load_dataset(data_copy)


def test_realistic_account_number_rejected(data_copy):
    def poison(items):
        items[0]["account_ref"] = "AE070331234567890123456"

    _mutate(data_copy / "citizens.json", "citizens", poison)
    with pytest.raises(SeedError):
        load_dataset(data_copy)


def test_dangling_scenario_reference_rejected(data_copy):
    def poison(items):
        items[0]["citizen_ref"] = "C-9999"

    _mutate(data_copy / "scenarios.json", "scenarios", poison)
    with pytest.raises(SeedError, match="unknown citizen"):
        load_dataset(data_copy)


def test_malformed_json_rejected(data_copy):
    (data_copy / "agents.json").write_text("{ not json", encoding="utf-8")
    with pytest.raises(SeedError, match="invalid JSON"):
        load_dataset(data_copy)
