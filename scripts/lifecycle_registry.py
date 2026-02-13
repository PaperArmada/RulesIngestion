"""Lifecycle grouping for scripts to reduce discovery overhead."""

ACTIVE_SCRIPTS = [
    "evals/v1_baseline/run_baseline_suite.sh",
    "evals/v1_baseline/run_baseline_suite.py",
    "scripts/run_stage_a_prime.py",
    "scripts/rerun_stage_b.py",
    "scripts/evaluate_mark3_pipeline.py",
]

ONE_OFF_SCRIPTS = [
    "scripts/analyze_deepseek_brutal_results.py",
    "scripts/build_brutal_canonical_md.py",
    "scripts/map_starfinder_gold_to_mark3_units.py",
    "scripts/build_nominated_gold_sw.py",
    "scripts/apply_nominated_gold_sw.py",
]
