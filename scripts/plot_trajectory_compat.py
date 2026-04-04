"""Unified UAV trajectory plotting for both legacy and experiment results.

Supports two input shapes:
1. discussion/<run_dir>/population_result_<gen>.json
2. discussion/experiment_results/<exp>/D1/run_seed_<seed>.json

Usage:
    uv run python scripts/plot_trajectory_compat.py
    uv run python scripts/plot_trajectory_compat.py --input discussion/20260402_231832
    uv run python scripts/plot_trajectory_compat.py --input discussion/experiment_results/20260403_192146/D1/run_seed_42.json
    uv run python scripts/plot_trajectory_compat.py --mode trajectory --save traj.png --no-show
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.plot_trajectory import (
    _apply_matlab_style,
    _collect_generation_files,
    _extract_assignments,
    _extract_trajectories,
    _load_generation,
    _parse_task_positions,
    _parse_uav_positions,
    _plot_assignment,
    _plot_trajectory,
    _resolve_run_dir,
    _select_individual,
)
from scripts.script_common import get_simulation_step


def _resolve_latest_d1(seed: int) -> Path:
    base = ROOT / "discussion" / "experiment_results"
    candidates = sorted(
        (p for p in base.glob(f"*/D1/run_seed_{seed}.json") if p.is_file()),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    if not candidates:
        raise FileNotFoundError(
            f"no D1/run_seed_{seed}.json found under {base}"
        )
    return candidates[0]


def _resolve_input(input_arg: str | None, seed: int) -> Path:
    if input_arg:
        path = Path(input_arg)
        if not path.is_absolute():
            path = ROOT / path
        return path
    return _resolve_latest_d1(seed)


def _extract_from_legacy_run(
    run_dir: Path,
    gen: int | None,
    individual_choice: str,
) -> dict:
    gen_files = _collect_generation_files(run_dir)
    if not gen_files:
        raise FileNotFoundError(f"no population_result_*.json found in {run_dir}")

    target_gen = gen if gen is not None else gen_files[-1][0]
    gen_path = next((p for g, p in gen_files if g == target_gen), None)
    if gen_path is None:
        available = [g for g, _ in gen_files]
        raise ValueError(f"generation {target_gen} not found. Available: {available}")

    population = _load_generation(gen_path)
    if population is None:
        raise ValueError(f"failed to load {gen_path}")

    individual = _select_individual(population, individual_choice)
    step0 = get_simulation_step(individual, "0")
    if not step0:
        raise ValueError("no simulation step 0 found in individual")
    if not step0.get("bcd_enabled", False):
        raise ValueError("BCD not enabled for this individual")

    snapshot = step0.get("bcd_meta", {}).get("optimal_snapshot", {})
    if not snapshot or "q" not in snapshot:
        raise ValueError("no optimal_snapshot.q found in bcd_meta")

    task_positions = _parse_task_positions(step0.get("task_info", ""))
    uav_starts, _uav_ends = _parse_uav_positions(step0.get("uav_info", ""))
    depot_pos = uav_starts.get(0, (250.0, 250.0))

    score = individual.get("evaluation_score", "N/A")
    if isinstance(score, float):
        score = f"{score:.4f}"

    return {
        "source_type": "legacy",
        "label": run_dir.name,
        "score": score,
        "snapshot": snapshot,
        "task_positions": task_positions,
        "depot_pos": depot_pos,
    }


def _extract_from_experiment_run(result_file: Path) -> dict:
    try:
        result = json.loads(result_file.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"failed to load {result_file}: {exc}") from exc
    if not isinstance(result, dict):
        raise ValueError(f"unexpected JSON type in {result_file}: {type(result)}")

    history = result.get("history", [])
    if not history:
        raise ValueError("'history' is empty or missing in result JSON")

    entry = history[0]
    snapshot = entry.get("bcd_meta", {}).get("optimal_snapshot", {})
    if not snapshot or "q" not in snapshot:
        raise ValueError("bcd_meta.optimal_snapshot.q not found")

    task_positions_raw = entry.get("task_positions", {})
    uav_positions_raw = entry.get("uav_positions", {})
    if not task_positions_raw or not uav_positions_raw:
        raise ValueError("task_positions or uav_positions missing in result JSON")

    task_positions = {
        int(k): (float(v[0]), float(v[1]))
        for k, v in task_positions_raw.items()
    }
    uav_start = {
        int(k): (float(v["start"][0]), float(v["start"][1]))
        for k, v in uav_positions_raw.items()
    }
    depot_pos = uav_start.get(0, (0.0, 0.0))

    score = entry.get("score", "N/A")
    if isinstance(score, float):
        score = f"{score:.4f}"

    return {
        "source_type": "experiment",
        "label": f"{result_file.parent.parent.name}/{result_file.stem}",
        "score": score,
        "snapshot": snapshot,
        "task_positions": task_positions,
        "depot_pos": depot_pos,
    }


def _extract_plot_data(
    input_path: Path,
    gen: int | None,
    individual_choice: str,
) -> dict:
    if input_path.is_file() and input_path.name.startswith("run_seed_"):
        return _extract_from_experiment_run(input_path)

    if input_path.is_dir():
        run_dir = _resolve_run_dir(str(input_path))
        return _extract_from_legacy_run(run_dir, gen, individual_choice)

    raise FileNotFoundError(
        f"unsupported input: {input_path}. Expected a run directory or run_seed_*.json"
    )


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Unified UAV trajectory visualization for legacy and D1 experiment outputs"
    )
    parser.add_argument(
        "--input",
        default=None,
        help="Run directory or run_seed_*.json. Default: latest D1 run_seed_<seed>.json",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=42,
        help="Seed used only for auto-locating the latest D1 run (default: 42)",
    )
    parser.add_argument(
        "--gen",
        type=int,
        default=None,
        help="Generation number for legacy run directories (default: last)",
    )
    parser.add_argument(
        "--individual",
        default="best",
        help="'best' or index for legacy run directories (default: best)",
    )
    parser.add_argument(
        "--mode",
        choices=["trajectory", "assignment", "both"],
        default="both",
        help="Plot mode (default: both)",
    )
    parser.add_argument(
        "--save",
        default=None,
        help="Save to file (PNG/PDF/SVG). For both-mode, suffixes are appended automatically.",
    )
    parser.add_argument(
        "--no-show",
        action="store_true",
        help="Do not display the plot window",
    )
    args = parser.parse_args()

    try:
        input_path = _resolve_input(args.input, args.seed)
        plot_data = _extract_plot_data(input_path, args.gen, args.individual)
    except (FileNotFoundError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    trajectories = _extract_trajectories(plot_data["snapshot"])
    assignments = _extract_assignments(
        plot_data["snapshot"],
        n_tasks=len(plot_data["task_positions"]),
    )

    print(f"input: {input_path}")
    print(f"source_type: {plot_data['source_type']}")
    print(f"label: {plot_data['label']}")
    print(f"score: {plot_data['score']}")
    print(
        f"UAVs: {len(trajectories)}  tasks: {len(plot_data['task_positions'])}  "
        f"timeslots: {next(iter(trajectories.values())).shape[0]}"
    )

    _apply_matlab_style()
    import matplotlib.pyplot as plt

    modes = []
    if args.mode in ("trajectory", "both"):
        modes.append("trajectory")
    if args.mode in ("assignment", "both"):
        modes.append("assignment")

    for mode in modes:
        if args.mode == "both":
            fig, ax = plt.subplots(figsize=(8, 8))
        else:
            fig, ax = plt.subplots(figsize=(8, 8))

        if mode == "trajectory":
            _plot_trajectory(
                ax,
                trajectories,
                plot_data["task_positions"],
                plot_data["depot_pos"],
                title=f"UAV Trajectory - {plot_data['label']} (score={plot_data['score']})",
            )
        else:
            _plot_assignment(
                ax,
                trajectories,
                plot_data["task_positions"],
                plot_data["depot_pos"],
                assignments,
                title=f"UAV Assignment - {plot_data['label']} (score={plot_data['score']})",
            )

        fig.tight_layout()

        if args.save:
            save_path = Path(args.save)
            if len(modes) > 1:
                save_path = save_path.with_name(
                    f"{save_path.stem}_{mode}{save_path.suffix}"
                )
            fig.savefig(str(save_path), dpi=150, bbox_inches="tight")
            print(f"Saved: {save_path.resolve()}")

    if not args.no_show:
        plt.show()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
