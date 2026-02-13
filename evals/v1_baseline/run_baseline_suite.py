"""Matrix runner for v1 baseline configs."""

from __future__ import annotations

import argparse
import subprocess
from pathlib import Path


CONFIG_MATRIX = [
    ("phb", "retrieval_lab/experiments/hybrid/phb_hybrid.yaml"),
    ("phb", "retrieval_lab/experiments/hybrid/phb_hybrid_dual_list_fusion.yaml"),
    ("starfinder", "retrieval_lab/experiments/hybrid/starfinder_hybrid.yaml"),
    ("starfinder", "retrieval_lab/experiments/hybrid/starfinder_hybrid_dual_list_fusion.yaml"),
    ("swords_wizardry", "retrieval_lab/experiments/hybrid/swords_wizardry_hybrid.yaml"),
    ("swords_wizardry", "retrieval_lab/experiments/hybrid/swords_wizardry_hybrid_dual_list_fusion.yaml"),
]


def _run(command: list[str], cwd: Path) -> None:
    completed = subprocess.run(command, cwd=str(cwd), check=False)
    if completed.returncode != 0:
        raise SystemExit(completed.returncode)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run all v1 baseline experiments.")
    parser.add_argument("--out-dir", required=True, help="Output directory for run artifacts.")
    parser.add_argument("--version", default="v1", help="Substrate version, defaults to v1.")
    args = parser.parse_args()

    repo_root = Path(__file__).resolve().parents[2]
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    for _, config in CONFIG_MATRIX:
        print(f"--- Running: {config} ---", flush=True)
        _run(
            [
                "uv",
                "run",
                "python",
                "-m",
                "retrieval_lab.run_experiment",
                "--config",
                config,
                "--output",
                str(out_dir),
                "--substrate-version",
                args.version,
            ],
            repo_root,
        )


if __name__ == "__main__":
    main()
