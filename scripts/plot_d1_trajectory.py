"""Plot UAV trajectory for D1 (default-objective) experiment results.

Usage:
    uv run python scripts/plot_d1_trajectory.py
    uv run python scripts/plot_d1_trajectory.py --result-file discussion/experiment_results/20260403_xxx/D1/run_seed_42.json
    uv run python scripts/plot_d1_trajectory.py --seed 42 --mode trajectory --save traj.png --no-show
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.plot_trajectory import (
    _apply_matlab_style,
    _extract_assignments,
    _extract_trajectories,
    _plot_assignment,
    _plot_trajectory,
)


def _resolve_result_file(result_file_arg: str | None, seed: int) -> Path:
    if result_file_arg:
        path = Path(result_file_arg)
        if not path.is_absolute():
            path = ROOT / path
        return path

    # Auto-locate: latest experiment_results/*/D1/run_seed_<seed>.json
    base = ROOT / "discussion" / "experiment_results"
    candidates = sorted(p for p in base.glob(f"*/D1/run_seed_{seed}.json") if p.is_file())
    if not candidates:
        raise FileNotFoundError(
            f"no D1/run_seed_{seed}.json found under {base}. "
            "Run: uv run python scripts/run_all_experiments.py --groups D1 --seeds {seed}"
        )
    return candidates[-1]


def _load_result(path: Path) -> dict:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"unexpected JSON type in {path}: {type(data)}")
    return data


def main() -> int:
    parser = argparse.ArgumentParser(description="Plot UAV trajectory from D1 experiment result")
    parser.add_argument("--result-file", default=None, help="Path to run_seed_*.json (default: auto-locate)")
    parser.add_argument("--seed", type=int, default=42, help="Seed to auto-locate (default: 42)")
    parser.add_argument("--mode", choices=["trajectory", "assignment", "both"], default="both",
                        help="Plot mode (default: both)")
    parser.add_argument("--save", default=None, help="Save to file (PNG/PDF/SVG)")
    parser.add_argument("--no-show", action="store_true", help="Do not display the plot window")
    args = parser.parse_args()

    # ── Resolve file ──
    try:
        result_file = _resolve_result_file(args.result_file, args.seed)
    except FileNotFoundError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    print(f"Loading: {result_file}")

    try:
        result = _load_result(result_file)
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    # ── Extract snapshot from history[0] ──
    history = result.get("history", [])
    if not history:
        print("ERROR: 'history' is empty or missing in result JSON", file=sys.stderr)
        return 1

    entry = history[0]
    bcd_meta = entry.get("bcd_meta", {})
    snapshot = bcd_meta.get("optimal_snapshot")
    if not snapshot or "q" not in snapshot:
        print(
            "ERROR: bcd_meta.optimal_snapshot.q not found.\n"
            "Hint: re-run D1 with the updated run_all_experiments.py to generate trajectory data.",
            file=sys.stderr,
        )
        return 1

    # ── Extract positions ──
    task_positions_raw = entry.get("task_positions", {})
    uav_positions_raw = entry.get("uav_positions", {})

    if not task_positions_raw or not uav_positions_raw:
        print("ERROR: task_positions or uav_positions missing in result JSON", file=sys.stderr)
        return 1

    task_positions: dict[int, tuple[float, float]] = {
        int(k): (float(v[0]), float(v[1])) for k, v in task_positions_raw.items()
    }
    uav_start: dict[int, tuple[float, float]] = {
        int(k): (float(v["start"][0]), float(v["start"][1]))
        for k, v in uav_positions_raw.items()
    }

    # Depot = UAV 0 start position
    depot_pos = uav_start.get(0, (0.0, 0.0))

    # ── Extract trajectories and assignments ──
    trajectories = _extract_trajectories(snapshot)
    assignments = _extract_assignments(snapshot, n_tasks=len(task_positions))

    n_tasks = len(task_positions)
    n_uavs = len(trajectories)
    print(f"UAVs: {n_uavs}, Tasks: {n_tasks}, Timeslots: {next(iter(trajectories.values())).shape[0]}")

    # ── Plot ──
    import matplotlib.pyplot as plt

    _apply_matlab_style()

    run_label = result_file.parent.parent.name  # e.g. 20260403_123456
    seed_label = result_file.stem  # e.g. run_seed_42

    if args.mode == "both":
        fig, axes = plt.subplots(1, 2, figsize=(16, 8))
        _plot_trajectory(axes[0], trajectories, task_positions, depot_pos,
                         title=f"D1 Trajectory — {run_label} / {seed_label}")
        _plot_assignment(axes[1], trajectories, task_positions, depot_pos, assignments,
                         title=f"D1 Assignment — {run_label} / {seed_label}")
    elif args.mode == "trajectory":
        fig, ax = plt.subplots(1, 1, figsize=(8, 8))
        _plot_trajectory(ax, trajectories, task_positions, depot_pos,
                         title=f"D1 Trajectory — {run_label} / {seed_label}")
    else:  # assignment
        fig, ax = plt.subplots(1, 1, figsize=(8, 8))
        _plot_assignment(ax, trajectories, task_positions, depot_pos, assignments,
                         title=f"D1 Assignment — {run_label} / {seed_label}")

    plt.tight_layout()

    if args.save:
        save_path = Path(args.save)
        fig.savefig(save_path, dpi=150, bbox_inches="tight")
        print(f"Saved: {save_path.resolve()}")

    if not args.no_show:
        plt.show()

    return 0


if __name__ == "__main__":
    sys.exit(main())
