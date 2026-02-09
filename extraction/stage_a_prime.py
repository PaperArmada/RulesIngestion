"""
Stage A' — LLM Representational Enrichment (Retrieval-only).

Consumes EvidenceUnits from Stage B and produces non-evidence enrichment payloads
for retrieval indexing. All outputs are authority=none, never_cite.

Uses the OpenAI Responses API with Structured Outputs (Pydantic schema) so that
responses adhere to APrimeEnrichment and refusals are programmatically detectable.
See Docs/Design/stage_a_prime_contract.md and Docs/architecture/OpenAI_Responses_API.md.
"""

from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import blake3

from extraction.schemas import EvidenceUnit, GateDiagnostic
from extraction.schemas_a_prime import (
    APrimeEnrichment,
    compute_input_fingerprint,
)

logger = logging.getLogger(__name__)

_PROMPT_PATH = Path(__file__).resolve().parent / "prompts" / "A_PRIME_PROMPT_V1.md"
PROMPT_ID = "A_PRIME_PROMPT_V1"


def _load_prompt_template() -> str:
    """Load the template block from A_PRIME_PROMPT_V1.md (between Template and ---)."""
    text = _PROMPT_PATH.read_text(encoding="utf-8")
    start = text.find("You are annotating a single evidence unit")
    if start == -1:
        raise ValueError("Template section not found in A_PRIME_PROMPT_V1.md")
    end_marker = "\n---\n"
    end = text.find(end_marker, start)
    if end == -1:
        end = len(text)
    block = text[start:end]
    lines = block.split("\n")
    out = []
    for line in lines:
        if line.startswith("    "):
            out.append(line[4:])
        else:
            out.append(line)
    return "\n".join(out)


def _prompt_hash() -> str:
    """Hash of the frozen prompt for run manifest."""
    template = _load_prompt_template()
    return blake3.blake3(template.encode("utf-8")).hexdigest()


def _cache_key(input_fingerprint: str, prompt_id: str, model_id: str) -> str:
    """Deterministic cache key for enrichment lookup."""
    payload = f"{input_fingerprint}|{prompt_id}|{model_id}"
    return blake3.blake3(payload.encode("utf-8")).hexdigest()


def _render_prompt(
    book_id: str,
    unit_type: str,
    structural_path: list[str],
    verbatim_text: str,
    table_schema: str | None = None,
) -> str:
    """Fill the prompt template with unit data."""
    template = _load_prompt_template()
    path_str = json.dumps(structural_path)
    if table_schema:
        table_block = f"table_schema:\n```\n{table_schema}\n```"
    else:
        table_block = ""
    return (
        template.replace("{{BOOK_ID}}", book_id)
        .replace("{{UNIT_TYPE}}", unit_type)
        .replace("{{STRUCTURAL_PATH}}", path_str)
        .replace("{{VERBATIM_TEXT}}", verbatim_text)
        .replace("{{TABLE_SCHEMA_BLOCK}}", table_block)
    )


def _validate_surface_forms_substrings(enrichment: APrimeEnrichment, verbatim_text: str) -> None:
    """Raise ValueError if any surface_form is not a substring of verbatim_text."""
    for atom in enrichment.mechanic_atoms:
        for sf in atom.surface_forms:
            if sf not in verbatim_text:
                raise ValueError(
                    f"surface_form {sf!r} is not a substring of verbatim_text"
                )


def _responses_parse_sync(
    client: Any,
    model: str,
    prompt: str,
    book_id: str,
) -> APrimeEnrichment | None:
    """Call Responses API with Structured Outputs (sync). Returns parsed enrichment or None on refusal."""
    input_messages = [
        {"role": "developer", "content": "You are annotating evidence units for retrieval indexing. Output only valid JSON matching the schema. Do not add facts or use outside knowledge."},
        {"role": "user", "content": prompt},
    ]
    response = client.responses.parse(
        model=model,
        input=input_messages,
        text_format=APrimeEnrichment,
        temperature=0,
    )
    if not response.output:
        return None
    for item in response.output:
        if getattr(item, "content", None):
            for block in item.content:
                if getattr(block, "type", None) == "refusal":
                    logger.warning("Stage A' refusal: %s", getattr(block, "refusal", ""))
                    return None
    if hasattr(response, "output_parsed") and response.output_parsed is not None:
        return response.output_parsed
    return None


async def enrich_unit(
    unit: EvidenceUnit,
    *,
    client: Any,
    model: str,
    prompt_template: str,
    book_id: str,
    cache_dir: Path,
    input_fingerprint: str | None = None,
) -> APrimeEnrichment:
    """Enrich a single EvidenceUnit. Uses cache when key exists. Uses Responses API + Structured Outputs."""
    fp = input_fingerprint or compute_input_fingerprint(unit)
    key = _cache_key(fp, PROMPT_ID, model)
    cache_path = cache_dir / f"{key}.json"

    if cache_path.exists():
        data = json.loads(cache_path.read_text(encoding="utf-8"))
        return APrimeEnrichment.model_validate(data)

    prompt = _render_prompt(
        book_id=book_id,
        unit_type=unit.unit_type,
        structural_path=unit.structural_path,
        verbatim_text=unit.text,
        table_schema=None,
    )

    loop = asyncio.get_event_loop()
    enrichment = await loop.run_in_executor(
        None,
        lambda: _responses_parse_sync(client, model, prompt, book_id),
    )
    if enrichment is None:
        raise ValueError("Model refused or returned no parseable output for unit")
    _validate_surface_forms_substrings(enrichment, unit.text)

    enrichment.input_fingerprint = fp
    enrichment.model_id = model
    enrichment.prompt_id = PROMPT_ID
    enrichment.created_at = datetime.now(timezone.utc).isoformat()
    enrichment.authority = "none"
    enrichment.source = "llm_annotation"
    enrichment.admissibility = "non_evidence"
    enrichment.stage_c_visibility = "hidden"
    enrichment.citation_policy = "never_cite"

    cache_dir.mkdir(parents=True, exist_ok=True)
    cache_path.write_text(
        enrichment.model_dump_json(indent=2),
        encoding="utf-8",
    )
    return enrichment


async def enrich_units_batch(
    units: list[EvidenceUnit],
    *,
    client: Any | None = None,
    model: str = "gpt-4o-mini",
    book_id: str,
    cache_dir: Path,
    concurrency: int = 10,
) -> list[APrimeEnrichment]:
    """Enrich multiple units concurrently with semaphore limit. Uses Responses API + Structured Outputs."""
    sem = asyncio.Semaphore(concurrency)

    async def one(unit: EvidenceUnit) -> APrimeEnrichment:
        async with sem:
            return await enrich_unit(
                unit,
                client=client,
                model=model,
                prompt_template=_load_prompt_template(),
                book_id=book_id,
                cache_dir=cache_dir,
            )

    if not units:
        return []

    if client is None:
        from openai import OpenAI
        client = OpenAI()

    return list(await asyncio.gather(*[one(u) for u in units]))


@dataclass
class StageAPrimeResult:
    """Output of a Stage A' run."""

    enrichments: list[tuple[str, APrimeEnrichment]]  # (unit_id, enrichment)
    gate_diagnostics: list[GateDiagnostic] = field(default_factory=list)
    run_manifest: dict[str, Any] = field(default_factory=dict)

    @property
    def gates_passed(self) -> bool:
        return all(g.passed for g in self.gate_diagnostics)


def run_stage_a_prime(
    units: list[EvidenceUnit],
    out_dir: Path,
    *,
    book_id: str,
    model: str = "gpt-5-mini",
    openai_client: Any | None = None,
    concurrency: int = 10,
) -> StageAPrimeResult:
    """Run Stage A' enrichment on EvidenceUnits. Sync entry point."""
    from extraction.gates_a_prime import run_stage_a_prime_gates

    out_dir = Path(out_dir).resolve()
    cache_dir = out_dir / "a_prime_cache"

    enrichments_list = asyncio.run(
        enrich_units_batch(
            units,
            client=openai_client,
            model=model,
            book_id=book_id,
            cache_dir=cache_dir,
            concurrency=concurrency,
        )
    )

    enrichments = [(units[i].unit_id, enrichments_list[i]) for i in range(len(units))]
    unit_by_id = {u.unit_id: u for u in units}

    diagnostics = run_stage_a_prime_gates(enrichments, unit_by_id)
    prompt_hash = _prompt_hash()

    run_manifest = {
        "model_id": model,
        "prompt_id": PROMPT_ID,
        "prompt_hash": prompt_hash,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "unit_count": len(units),
        "cache_dir": str(cache_dir),
    }

    return StageAPrimeResult(
        enrichments=enrichments,
        gate_diagnostics=diagnostics,
        run_manifest=run_manifest,
    )
