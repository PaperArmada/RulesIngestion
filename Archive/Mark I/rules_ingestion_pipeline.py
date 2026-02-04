"""
Rules Ingestion Pipeline - Marker + TTRPG Enrichment

This pipeline:
1. Uses Marker for PDF extraction (better spell metadata preservation)
2. Enriches chunks with TTRPG-specific metadata
3. Builds a simplified graph for RAG queries
4. Outputs enriched chunks JSON + graph JSON

Usage:
    uv run python rules_ingestion_pipeline.py input.pdf --output-dir outputs/
    uv run python rules_ingestion_pipeline.py --enrich-only outputs/marker_chunks/
    uv run python rules_ingestion_pipeline.py --enrich-only chunks.json --markdown-source doc.md
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

from enrichment import (
    EnrichedChunk,
    Graph,
    build_chunk_graph,
    build_metrics_report,
    coalesce_chunks,
    enrich_chunk,
    merge_spell_chunks,
)
from config_generator import RulesetConfiguration, generate_ruleset_config_with_diagnostics
from config_profile import (
    RulesetProfile,
    build_ruleset_profile,
    detect_structure_drift,
    resolve_mongo_uri,
)
from config_store import (
    fetch_latest_ruleset_config,
    fetch_latest_ruleset_profile,
    save_ruleset_config,
    save_ruleset_profile,
)
from llm_enrichment import (
    extract_paragraph_targets,
    generate_evaluation_queries,
    run_paragraph_enrichment,
    run_review_enrichment,
)
from llm_config_generator import (
    build_config_prompt,
    generate_ruleset_config_payload,
    normalize_llm_payload,
    validate_config_payload,
)
from diagnostics_store import (
    DiagnosticsRetentionPolicy,
    GenerationDiagnostics,
    save_generation_diagnostics,
)
from enrichment_planner import EnrichmentPlan
from pipeline_outputs import write_enrichment_outputs
from pipeline_runs import finish_run_record, start_run_record

# Output layout constants
CONFIGS_DIRNAME = "configs"
RUNS_DIRNAME = "runs"
RUN_INPUTS_DIRNAME = "inputs"
RUN_OUTPUTS_DIRNAME = "outputs"
EXPERIMENTS_DIRNAME = "experiments"

# =============================================================================
# MARKER INTEGRATION
# =============================================================================

def run_marker(
    pdf_path: str,
    output_dir: str,
    output_format: str = "json",
    use_llm: bool = False,
) -> Path:
    """Run Marker to extract PDF content."""
    pdf_path = Path(pdf_path).resolve()
    output_dir = Path(output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # Build marker command
    cmd = [
        "marker_single",
        str(pdf_path),
        "--output_dir", str(output_dir),
        "--output_format", output_format,
    ]
    
    if use_llm:
        cmd.append("--use_llm")
    
    print(f"🚀 Running Marker: {' '.join(cmd)}")
    
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        print("✅ Marker extraction complete")
        if result.stdout:
            print(result.stdout)
    except subprocess.CalledProcessError as e:
        print(f"❌ Marker failed: {e.stderr}")
        raise
    
    # Find the output directory (Marker creates a subdirectory)
    pdf_name = pdf_path.stem
    marker_output = output_dir / pdf_name
    if not marker_output.exists():
        # Try to find it
        for subdir in output_dir.iterdir():
            if subdir.is_dir() and pdf_name in subdir.name:
                marker_output = subdir
                break
    
    return marker_output


def load_marker_chunks(chunks_path: Path) -> List[Dict[str, Any]]:
    """Load Marker chunks JSON output."""
    with open(chunks_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    
    # Handle both direct list and wrapped format
    if isinstance(data, list):
        return data
    if isinstance(data, dict) and "blocks" in data:
        return data["blocks"]
    if isinstance(data, dict) and "children" in data:
        # Flatten nested structure
        return flatten_marker_tree(data)
    
    return []


def flatten_marker_tree(node: Dict[str, Any], blocks: Optional[List[Dict[str, Any]]] = None) -> List[Dict[str, Any]]:
    """Flatten Marker's nested JSON tree into a list of blocks."""
    if blocks is None:
        blocks = []
    
    # Add this node if it has content
    if node.get("block_type") and node.get("html"):
        blocks.append(node)
    
    # Recurse into children
    children = node.get("children")
    if children:
        for child in children:
            flatten_marker_tree(child, blocks)
    
    return blocks


# =============================================================================
# RULESET CONFIG RESOLUTION
# =============================================================================

def resolve_ruleset_config(
    ruleset_id: str,
    raw_blocks: List[Dict[str, Any]],
    mongo_uri: str,
    sample_size: int = 5,
    config_output_dir: Optional[str] = None,
    source_fingerprint: Optional[str] = None,
    force_regenerate: bool = False,
    allow_config_failure: bool = False,
    fetch_latest_profile: Callable[[str, str], Optional[RulesetProfile]] = fetch_latest_ruleset_profile,
    fetch_latest_config: Callable[[str, str], Optional[RulesetConfiguration]] = fetch_latest_ruleset_config,
    save_profile: Callable[[RulesetProfile, str], str] = save_ruleset_profile,
    save_config: Callable[[RulesetConfiguration, str], str] = save_ruleset_config,
    profile_builder: Callable[[List[Dict[str, Any]], str, int], RulesetProfile] = build_ruleset_profile,
    drift_detector: Optional[
        Callable[[RulesetProfile, RulesetProfile], bool]
    ] = detect_structure_drift,
    generator: Optional[Callable[[RulesetProfile], RulesetConfiguration]] = None,
) -> RulesetConfiguration:
    if generator is None:
        raise ValueError("A config generator function is required.")
    if drift_detector is None:
        drift_detector = detect_structure_drift

    profile = profile_builder(raw_blocks, ruleset_id, sample_size)
    if source_fingerprint is None:
        source_fingerprint = compute_source_fingerprint(None, raw_blocks)
    latest_profile = fetch_latest_profile(ruleset_id, mongo_uri)
    latest_config = fetch_latest_config(ruleset_id, mongo_uri)

    should_reuse = (
        latest_profile
        and latest_config
        and not drift_detector(latest_profile, profile)
    )
    if force_regenerate:
        should_reuse = False
    if latest_config and source_fingerprint and latest_config.source_fingerprint:
        if latest_config.source_fingerprint != source_fingerprint:
            should_reuse = False

    if should_reuse:
        profile_id = save_profile(profile, mongo_uri)
        print(
            "📦 Reusing latest ruleset config "
            f"(ruleset={ruleset_id}, profile_id={profile_id})"
        )
        config = latest_config
    else:
        if latest_profile and latest_config:
            print(
                "🧩 Structure drift detected; regenerating ruleset config "
                f"(ruleset={ruleset_id})"
            )
        profile_id = save_profile(profile, mongo_uri)
        print(f"🧾 Saved ruleset profile (ruleset={ruleset_id}, profile_id={profile_id})")
        try:
            config = generator(profile)
        except ValueError as exc:
            if allow_config_failure:
                print(
                    "⚠️  Ruleset config generation failed; continuing without config "
                    f"(ruleset={ruleset_id}, reason={exc})"
                )
                return None
            raise
        if config is None:
            if allow_config_failure:
                print(
                    "⚠️  Ruleset config generation returned empty config; "
                    f"continuing without config (ruleset={ruleset_id})"
                )
                return None
            raise ValueError("Ruleset config generation returned no config.")
        config.version = _next_config_version(latest_config.version if latest_config else None)
        config.source_fingerprint = source_fingerprint
        config_id = save_config(config, mongo_uri)
        print(f"✅ Saved ruleset config (ruleset={ruleset_id}, config_id={config_id})")

    if config_output_dir and config:
        version_label = _format_version_label(config.version)
        output_path = Path(config_output_dir) / ruleset_id / f"{version_label}.config.json"
        output_path.parent.mkdir(parents=True, exist_ok=True)
        if hasattr(config, "model_dump"):
            config_payload = config.model_dump(mode="json")
        else:
            config_payload = config.dict()
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(config_payload, f, indent=2, default=str)
        print(f"🧾 Config snapshot: {output_path}")

    return config


def compute_source_fingerprint(
    source_path: Optional[Path], raw_blocks: List[Dict[str, Any]]
) -> str:
    hasher = hashlib.sha256()
    if source_path and source_path.exists():
        with open(source_path, "rb") as handle:
            for chunk in iter(lambda: handle.read(8192), b""):
                hasher.update(chunk)
        return hasher.hexdigest()
    normalized = json.dumps(raw_blocks, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    hasher.update(normalized.encode("utf-8"))
    return hasher.hexdigest()


def _next_config_version(current_version: Optional[str]) -> str:
    if not current_version:
        return "v1"
    match = re.search(r"(\d+)$", current_version)
    if not match:
        return "v1"
    return f"v{int(match.group(1)) + 1}"


def _format_version_label(version: str) -> str:
    return version if version.startswith("v") else f"v{version}"


def generate_config_with_llm(
    profile: RulesetProfile,
    mongo_uri: str,
    llm_model: str,
    api_key: Optional[str],
    max_retries: int = 3,
) -> RulesetConfiguration:
    prompt = build_config_prompt(profile)
    call_durations: List[float] = []

    def timed_generator(profile_input: RulesetProfile, attempt: int) -> Dict[str, Any]:
        start = time.perf_counter()
        payload = generate_ruleset_config_payload(
            profile_input,
            model=llm_model,
            api_key=api_key,
            prompt=prompt,
        )
        call_durations.append(time.perf_counter() - start)
        return payload

    def validator(payload: Dict[str, Any]) -> RulesetConfiguration:
        normalized = normalize_llm_payload(profile, payload)
        validated = validate_config_payload(profile, normalized)
        return RulesetConfiguration(**validated)

    config, diagnostics = run_config_generation_with_diagnostics(
        profile=profile,
        generator=timed_generator,
        validator=validator,
        mongo_uri=mongo_uri,
        prompt_payload={"prompt": prompt, "model": llm_model},
        max_retries=max_retries,
    )

    if call_durations:
        total = sum(call_durations)
        avg = total / len(call_durations)
        print(
            "⏱️ LLM config generation calls: "
            f"{len(call_durations)} total, "
            f"avg={avg:.2f}s, total={total:.2f}s"
        )

    if config is None:
        raise ValueError("LLM config generation failed; diagnostics stored.")
    return config


def execute_enrichment_plan(
    blocks: List[Dict[str, Any]],
    plan: EnrichmentPlan,
    llm_enabled: bool,
    deterministic_enricher: Callable[[Dict[str, Any]], Dict[str, Any]],
    llm_enricher: Callable[[Dict[str, Any]], Dict[str, Any]],
) -> Dict[str, Any]:
    deterministic_results = [deterministic_enricher(block) for block in blocks]
    llm_results: List[Dict[str, Any]] = []

    if llm_enabled:
        for target in plan.nondeterministic_targets:
            llm_results.append(llm_enricher(target))

    return {"deterministic_results": deterministic_results, "llm_results": llm_results}


def run_config_generation_with_diagnostics(
    profile: RulesetProfile,
    generator: Callable[[RulesetProfile, int], Dict[str, Any]],
    validator: Callable[[Dict[str, Any]], RulesetConfiguration],
    mongo_uri: str,
    prompt_payload: Optional[dict],
    diagnostics_saver: Callable[
        [GenerationDiagnostics, str, Optional[DiagnosticsRetentionPolicy]], str
    ] = save_generation_diagnostics,
    retention_policy: Optional[DiagnosticsRetentionPolicy] = None,
    max_retries: int = 3,
) -> Tuple[Optional[RulesetConfiguration], Optional[GenerationDiagnostics]]:
    config, diagnostics = generate_ruleset_config_with_diagnostics(
        profile=profile,
        generator=generator,
        validator=validator,
        prompt_payload=prompt_payload,
        max_retries=max_retries,
    )

    if diagnostics:
        diagnostics_saver(diagnostics, mongo_uri, retention_policy)
        print(
            "❌ Config generation failed; diagnostics stored for "
            f"ruleset={diagnostics.ruleset_id} signature={diagnostics.doc_signature}"
        )
    return config, diagnostics


# =============================================================================
# PIPELINE FUNCTIONS
# =============================================================================

def process_pdf(
    pdf_path: str,
    output_dir: str,
    use_llm: bool = False,
    doc_id: Optional[str] = None,
    markdown_source: Optional[str] = None,
    auto_config: bool = False,
    mongo_uri: Optional[str] = None,
    ruleset_id: Optional[str] = None,
    llm_model: Optional[str] = None,
    llm_api_key: Optional[str] = None,
    llm_pre_enrich: bool = False,
    llm_review: bool = False,
    llm_review_limit: Optional[int] = None,
    force_regenerate_config: bool = False,
    allow_config_failure: bool = False,
) -> Tuple[List[EnrichedChunk], Graph]:
    """Full pipeline: PDF → Marker → Enrich → Graph."""
    pdf_path = Path(pdf_path)
    output_dir = Path(output_dir)
    
    if doc_id is None:
        doc_id = pdf_path.stem

    resolved_ruleset_id = ruleset_id or doc_id
    resolved_mongo_uri = (
        resolve_mongo_uri(mongo_uri) if (auto_config or llm_pre_enrich or llm_review) else None
    )
    
    # Step 1: Run Marker
    print(f"\n📄 Processing: {pdf_path.name}")
    marker_output = run_marker(str(pdf_path), str(output_dir / "marker_raw"), output_format="json")
    
    # Step 2: Load chunks
    chunks_file = None
    for f in marker_output.iterdir():
        if f.suffix == ".json" and "_meta" not in f.name:
            chunks_file = f
            break
    
    if not chunks_file:
        raise FileNotFoundError(f"No JSON output found in {marker_output}")
    
    print(f"📦 Loading chunks from: {chunks_file.name}")
    raw_chunks = load_marker_chunks(chunks_file)
    print(f"   Found {len(raw_chunks)} raw blocks")
    source_fingerprint = compute_source_fingerprint(pdf_path, raw_chunks)

    resolved_config: Optional[RulesetConfiguration] = None
    if auto_config:
        resolved_llm_model = llm_model or os.getenv("OPENAI_MODEL", "gpt-5.2-codex")
        resolved_api_key = llm_api_key or os.getenv("OPENAI_API_KEY")
        print(f"🤖 Generating ruleset config via LLM for {resolved_ruleset_id}...")
        resolved_config = resolve_ruleset_config(
            ruleset_id=resolved_ruleset_id,
            raw_blocks=raw_chunks,
            mongo_uri=resolved_mongo_uri or resolve_mongo_uri(mongo_uri),
            config_output_dir=str(output_dir / CONFIGS_DIRNAME),
            source_fingerprint=source_fingerprint,
            force_regenerate=force_regenerate_config,
            allow_config_failure=allow_config_failure,
            generator=lambda profile: generate_config_with_llm(
                profile,
                mongo_uri=resolved_mongo_uri or resolve_mongo_uri(mongo_uri),
                llm_model=resolved_llm_model,
                api_key=resolved_api_key,
            ),
        )
    elif llm_pre_enrich or llm_review:
        resolved_config = fetch_latest_ruleset_config(
            resolved_ruleset_id, resolved_mongo_uri or resolve_mongo_uri(mongo_uri)
        )
        if not resolved_config:
            raise ValueError("No ruleset config found for LLM enrichment.")

    run_id, run_record = start_run_record(
        resolved_config=resolved_config,
        source_fingerprint=source_fingerprint,
        raw_blocks=raw_chunks,
        mongo_uri=resolved_mongo_uri,
    )
    
    # Step 3: Enrich chunks
    print("🏷️  Enriching with TTRPG metadata...")
    enriched_chunks = [enrich_chunk(chunk) for chunk in raw_chunks]
    
    # Filter out empty chunks
    enriched_chunks = [c for c in enriched_chunks if c.text.strip()]
    print(f"   {len(enriched_chunks)} non-empty chunks")
    
    # Merge spell chunks
    pre_merge_spells = sum(1 for c in enriched_chunks if c.content_kind == "spell")
    enriched_chunks = merge_spell_chunks(enriched_chunks)
    post_merge_spells = sum(1 for c in enriched_chunks if c.content_kind == "spell")
    print(f"   Merged spell blocks: {pre_merge_spells} → {post_merge_spells}")
    
    # Count by content kind
    kind_counts: Dict[str, int] = {}
    for chunk in enriched_chunks:
        kind_counts[chunk.content_kind] = kind_counts.get(chunk.content_kind, 0) + 1
    print(f"   Content types: {kind_counts}")
    
    # Step 4: Build graph
    print("🔗 Building graph...")
    graph = build_chunk_graph(
        doc_id,
        enriched_chunks,
        ruleset_id=resolved_ruleset_id,
        resolved_config=resolved_config,
    )
    print(f"   {len(graph.nodes)} nodes, {len(graph.edges)} edges")
    
    # Step 5: Save outputs
    enriched_dir = output_dir / "enriched"
    enriched_dir.mkdir(parents=True, exist_ok=True)
    coalesced_chunks = coalesce_chunks(enriched_chunks, min_chars=400, max_chars=800)

    if llm_pre_enrich and not resolved_config:
        print("⚠️  LLM pre-enrichment skipped (no ruleset config available).")
    if llm_pre_enrich and resolved_config:
        targets = extract_paragraph_targets(enriched_chunks, resolved_config)
        if targets:
            print(f"🤖 LLM paragraph targets: {len(targets)}")
            start = time.perf_counter()
            annotations = run_paragraph_enrichment(
                targets,
                model=llm_model,
                api_key=llm_api_key,
            )
            duration = time.perf_counter() - start
            annotations_output = enriched_dir / f"{doc_id}.llm_paragraphs.json"
            with open(annotations_output, "w", encoding="utf-8") as f:
                json.dump({"document": doc_id, "annotations": annotations}, f, indent=2)
            print(
                "✅ LLM paragraph annotations: "
                f"{annotations_output} ({len(annotations)} calls, {duration:.2f}s)"
            )
        else:
            print("🤖 LLM paragraph targets: 0 (skipping)")

    review_payload: Optional[dict] = None
    if llm_review:
        start = time.perf_counter()
        review_targets = [c.to_dict() for c in coalesced_chunks]
        print(
            "🤖 LLM review queued "
            f"({len(review_targets)} coalesced chunks, limit={llm_review_limit})"
        )
        reviews = run_review_enrichment(
            review_targets,
            model=llm_model,
            api_key=llm_api_key,
            limit=llm_review_limit,
        )
        duration = time.perf_counter() - start
        review_payload = {"document": doc_id, "reviews": reviews}
        print(
            "✅ LLM review annotations: "
            f"({len(reviews)} calls, {duration:.2f}s)"
        )

    evaluation_queries = generate_evaluation_queries(enriched_chunks, config=resolved_config)
    metrics = None
    if markdown_source:
        metrics = build_metrics_report(
            markdown_source,
            raw_chunks,
            enriched_chunks,
            doc_id,
        )

    output_payloads = write_enrichment_outputs(
        enriched_dir=enriched_dir,
        doc_id=doc_id,
        enriched_chunks=enriched_chunks,
        coalesced_chunks=coalesced_chunks,
        graph=graph,
        review_payload=review_payload,
        evaluation_queries=evaluation_queries,
        metrics=metrics,
    )
    finish_run_record(run_id, run_record, resolved_mongo_uri, output_payloads)

    return enriched_chunks, graph


def enrich_existing_chunks(
    chunks_path: str,
    output_dir: str,
    doc_id: Optional[str] = None,
    markdown_source: Optional[str] = None,
    auto_config: bool = False,
    mongo_uri: Optional[str] = None,
    ruleset_id: Optional[str] = None,
    llm_model: Optional[str] = None,
    llm_api_key: Optional[str] = None,
    llm_pre_enrich: bool = False,
    llm_review: bool = False,
    llm_review_limit: Optional[int] = None,
    force_regenerate_config: bool = False,
    allow_config_failure: bool = False,
) -> Tuple[List[EnrichedChunk], Graph]:
    """Enrich existing Marker chunks without re-running extraction."""
    chunks_path = Path(chunks_path)
    output_dir = Path(output_dir)
    
    if doc_id is None:
        doc_id = chunks_path.stem.replace(".json", "").replace("_chunks", "")

    resolved_ruleset_id = ruleset_id or doc_id
    resolved_mongo_uri = (
        resolve_mongo_uri(mongo_uri) if (auto_config or llm_pre_enrich or llm_review) else None
    )
    
    print(f"\n📦 Loading existing chunks: {chunks_path.name}")
    raw_chunks = load_marker_chunks(chunks_path)
    print(f"   Found {len(raw_chunks)} raw blocks")
    source_fingerprint = compute_source_fingerprint(None, raw_chunks)

    resolved_config: Optional[RulesetConfiguration] = None
    if auto_config:
        resolved_llm_model = llm_model or os.getenv("OPENAI_MODEL", "gpt-5.2-codex")
        resolved_api_key = llm_api_key or os.getenv("OPENAI_API_KEY")
        print(f"🤖 Generating ruleset config via LLM for {resolved_ruleset_id}...")
        resolved_config = resolve_ruleset_config(
            ruleset_id=resolved_ruleset_id,
            raw_blocks=raw_chunks,
            mongo_uri=resolved_mongo_uri or resolve_mongo_uri(mongo_uri),
            config_output_dir=str(output_dir / CONFIGS_DIRNAME),
            source_fingerprint=source_fingerprint,
            force_regenerate=force_regenerate_config,
            allow_config_failure=allow_config_failure,
            generator=lambda profile: generate_config_with_llm(
                profile,
                mongo_uri=resolved_mongo_uri or resolve_mongo_uri(mongo_uri),
                llm_model=resolved_llm_model,
                api_key=resolved_api_key,
            ),
        )
    elif llm_pre_enrich or llm_review:
        resolved_config = fetch_latest_ruleset_config(
            resolved_ruleset_id, resolved_mongo_uri or resolve_mongo_uri(mongo_uri)
        )
        if not resolved_config:
            raise ValueError("No ruleset config found for LLM enrichment.")
    
    # Enrich
    print("🏷️  Enriching with TTRPG metadata...")
    enriched_chunks = [enrich_chunk(chunk) for chunk in raw_chunks]
    enriched_chunks = [c for c in enriched_chunks if c.text.strip()]
    print(f"   {len(enriched_chunks)} non-empty chunks")
    
    # Merge spell chunks
    pre_merge_spells = sum(1 for c in enriched_chunks if c.content_kind == "spell")
    enriched_chunks = merge_spell_chunks(enriched_chunks)
    post_merge_spells = sum(1 for c in enriched_chunks if c.content_kind == "spell")
    print(f"   Merged spell blocks: {pre_merge_spells} → {post_merge_spells}")
    
    # Count by content kind
    kind_counts: Dict[str, int] = {}
    for chunk in enriched_chunks:
        kind_counts[chunk.content_kind] = kind_counts.get(chunk.content_kind, 0) + 1
    print(f"   Content types: {kind_counts}")
    
    # Build graph
    print("🔗 Building graph...")
    graph = build_chunk_graph(
        doc_id,
        enriched_chunks,
        ruleset_id=resolved_ruleset_id,
        resolved_config=resolved_config,
    )
    print(f"   {len(graph.nodes)} nodes, {len(graph.edges)} edges")
    
    # Save outputs
    enriched_dir = output_dir / "enriched"
    coalesced_chunks = coalesce_chunks(enriched_chunks, min_chars=400, max_chars=800)

    if llm_pre_enrich and not resolved_config:
        print("⚠️  LLM pre-enrichment skipped (no ruleset config available).")
    if llm_pre_enrich and resolved_config:
        targets = extract_paragraph_targets(enriched_chunks, resolved_config)
        if targets:
            print(f"🤖 LLM paragraph targets: {len(targets)}")
            start = time.perf_counter()
            annotations = run_paragraph_enrichment(
                targets,
                model=llm_model,
                api_key=llm_api_key,
            )
            duration = time.perf_counter() - start
            annotations_output = enriched_dir / f"{doc_id}.llm_paragraphs.json"
            with open(annotations_output, "w", encoding="utf-8") as f:
                json.dump({"document": doc_id, "annotations": annotations}, f, indent=2)
            print(
                "✅ LLM paragraph annotations: "
                f"{annotations_output} ({len(annotations)} calls, {duration:.2f}s)"
            )
        else:
            print("🤖 LLM paragraph targets: 0 (skipping)")

    review_payload: Optional[dict] = None
    if llm_review:
        start = time.perf_counter()
        review_targets = [c.to_dict() for c in coalesced_chunks]
        print(
            "🤖 LLM review queued "
            f"({len(review_targets)} coalesced chunks, limit={llm_review_limit})"
        )
        reviews = run_review_enrichment(
            review_targets,
            model=llm_model,
            api_key=llm_api_key,
            limit=llm_review_limit,
        )
        duration = time.perf_counter() - start
        review_payload = {"document": doc_id, "reviews": reviews}
        print(
            "✅ LLM review annotations: "
            f"({len(reviews)} calls, {duration:.2f}s)"
        )

    evaluation_queries = generate_evaluation_queries(enriched_chunks, config=resolved_config)
    metrics = None
    if markdown_source:
        metrics = build_metrics_report(
            markdown_source,
            raw_chunks,
            enriched_chunks,
            doc_id,
        )

    _output_payloads = write_enrichment_outputs(
        enriched_dir=enriched_dir,
        doc_id=doc_id,
        enriched_chunks=enriched_chunks,
        coalesced_chunks=coalesced_chunks,
        graph=graph,
        review_payload=review_payload,
        evaluation_queries=evaluation_queries,
        metrics=metrics,
    )

    return enriched_chunks, graph


# =============================================================================
# CLI
# =============================================================================

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Rules Ingestion Pipeline - Marker + TTRPG Enrichment",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Process a PDF end-to-end
  uv run python rules_ingestion_pipeline.py input.pdf --output-dir outputs/
  
  # Enrich existing Marker chunks
  uv run python rules_ingestion_pipeline.py --enrich-only chunks.json --output-dir outputs/
  
  # Use LLM for better table extraction
  uv run python rules_ingestion_pipeline.py input.pdf --output-dir outputs/ --use-llm
        """
    )
    
    parser.add_argument(
        "source",
        help="PDF file path or existing Marker chunks JSON (with --enrich-only)"
    )
    parser.add_argument(
        "--output-dir",
        default="outputs",
        help="Output directory (default: outputs/)"
    )
    parser.add_argument(
        "--doc-id",
        default=None,
        help="Document ID for output files (default: derived from filename)"
    )
    parser.add_argument(
        "--enrich-only",
        action="store_true",
        help="Skip Marker extraction, enrich existing chunks JSON"
    )
    parser.add_argument(
        "--use-llm",
        action="store_true",
        help="Use LLM for better table extraction (requires API key)"
    )
    parser.add_argument(
        "--auto-config",
        action="store_true",
        help="Generate ruleset config via LLM and store in MongoDB"
    )
    parser.add_argument(
        "--llm-pre-enrich",
        action="store_true",
        help="Run LLM paragraph enrichment based on config flags"
    )
    parser.add_argument(
        "--llm-review",
        action="store_true",
        help="Run LLM review pass on coalesced chunks"
    )
    parser.add_argument(
        "--llm-review-limit",
        type=int,
        default=None,
        help="Limit number of coalesced chunks for LLM review"
    )
    parser.add_argument(
        "--mongo-uri",
        default=None,
        help="MongoDB connection string (defaults to MONGODB_URI env)"
    )
    parser.add_argument(
        "--ruleset-id",
        default=None,
        help="Ruleset ID for config generation (defaults to doc id)"
    )
    parser.add_argument(
        "--llm-model",
        default=None,
        help="LLM model for config generation (defaults to OPENAI_MODEL env)"
    )
    parser.add_argument(
        "--markdown-source",
        default=None,
        help="Marker markdown output for regex review metrics"
    )
    parser.add_argument(
        "--force-regenerate-config",
        action="store_true",
        help="Force ruleset config regeneration even if existing config is valid"
    )
    parser.add_argument(
        "--allow-config-failure",
        action="store_true",
        help="Continue if config generation fails (useful for low-signal PDFs)"
    )
    
    args = parser.parse_args()
    
    if args.enrich_only:
        enrich_existing_chunks(
            args.source,
            args.output_dir,
            args.doc_id,
            args.markdown_source,
            auto_config=args.auto_config,
            mongo_uri=args.mongo_uri,
            ruleset_id=args.ruleset_id,
            llm_model=args.llm_model,
            llm_pre_enrich=args.llm_pre_enrich,
            llm_review=args.llm_review,
            llm_review_limit=args.llm_review_limit,
            force_regenerate_config=args.force_regenerate_config,
            allow_config_failure=args.allow_config_failure,
        )
    else:
        process_pdf(
            args.source,
            args.output_dir,
            args.use_llm,
            args.doc_id,
            args.markdown_source,
            auto_config=args.auto_config,
            mongo_uri=args.mongo_uri,
            ruleset_id=args.ruleset_id,
            llm_model=args.llm_model,
            llm_pre_enrich=args.llm_pre_enrich,
            llm_review=args.llm_review,
            llm_review_limit=args.llm_review_limit,
            force_regenerate_config=args.force_regenerate_config,
            allow_config_failure=args.allow_config_failure,
        )
    
    print("\n✨ Done!")


if __name__ == "__main__":
    main()
