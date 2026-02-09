"""
Stage A' quality gates. See stage_a_prime_contract.md acceptance tests.

A'-01: Output schema validity
A'-02: Substring enforcement (surface_forms in verbatim_text)
A'-05: Fragment flagging (delta_only => requires_parent)
"""

from __future__ import annotations

from extraction.schemas import EvidenceUnit, GateDiagnostic
from extraction.schemas_a_prime import APrimeEnrichment


def _gate_schema_validity(
    enrichments: list[tuple[str, APrimeEnrichment]],
) -> GateDiagnostic:
    """A'-01: Every enriched unit validates against schema."""
    failed: list[str] = []
    for unit_id, enr in enrichments:
        try:
            APrimeEnrichment.model_validate(enr.model_dump())
        except Exception as e:
            failed.append(f"{unit_id}: {e!s}")
    return GateDiagnostic(
        gate_name="a_prime_schema_validity",
        passed=len(failed) == 0,
        detail={"failed_count": len(failed), "failures": failed[:10]},
    )


def _gate_substring_enforcement(
    enrichments: list[tuple[str, APrimeEnrichment]],
    unit_by_id: dict[str, EvidenceUnit],
) -> GateDiagnostic:
    """A'-02: Every mechanic_atoms[*].surface_forms[] is a substring of verbatim_text."""
    violations: list[str] = []
    for unit_id, enr in enrichments:
        unit = unit_by_id.get(unit_id)
        if not unit:
            continue
        text = unit.text
        for i, atom in enumerate(enr.mechanic_atoms):
            for j, sf in enumerate(atom.surface_forms):
                if sf not in text:
                    violations.append(f"{unit_id} atom[{i}].surface_forms[{j}]={sf!r}")
    return GateDiagnostic(
        gate_name="a_prime_substring_enforcement",
        passed=len(violations) == 0,
        detail={"violation_count": len(violations), "violations": violations[:10]},
    )


def _gate_fragment_flagging(
    enrichments: list[tuple[str, APrimeEnrichment]],
) -> GateDiagnostic:
    """A'-05: Deltas without base rules produce requires_parent=true and include delta_only."""
    violations: list[str] = []
    for unit_id, enr in enrichments:
        for i, atom in enumerate(enr.mechanic_atoms):
            if "delta_only" in atom.risk_flags and not atom.requires_parent:
                violations.append(
                    f"{unit_id} atom[{i}] has risk_flags delta_only but requires_parent=false"
                )
    return GateDiagnostic(
        gate_name="a_prime_fragment_flagging",
        passed=len(violations) == 0,
        detail={"violation_count": len(violations), "violations": violations[:10]},
    )


def run_stage_a_prime_gates(
    enrichments: list[tuple[str, APrimeEnrichment]],
    unit_by_id: dict[str, EvidenceUnit],
) -> list[GateDiagnostic]:
    """Run all Stage A' gates. Returns list of GateDiagnostic."""
    return [
        _gate_schema_validity(enrichments),
        _gate_substring_enforcement(enrichments, unit_by_id),
        _gate_fragment_flagging(enrichments),
    ]
