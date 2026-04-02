"""UAV trajectory 2D visualization — MATLAB style.

Usage:
    uv run python scripts/plot_trajectory.py
    uv run python scripts/plot_trajectory.py --run-dir discussion/20260402_231832 --gen 1
    uv run python scripts/plot_trajectory.py --run-dir discussion/20260402_231832 --gen 1 --save trajectory.pdf --no-show
    uv run python scripts/plot_trajectory.py --mode assignment
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.script_common import get_simulation_step

# ─── Constants ────────────────────────────────────────────────────────────────

GEN_FILE_RE = re.compile(r"population_result_(\d+)\.json$")

UAV_COLORS = ["#0072BD", "#D95319", "#77AC30"]  # MATLAB default blue/orange/green
TASK_COLOR = "#333333"
DEPOT_COLOR = "#A2142F"  # MATLAB dark red
UNASSIGNED_COLOR = "#999999"

TASK_POS_RE = re.compile(r"pos=\(([^)]+)\)")
UAV_POS_RE = re.compile(r"pos=\(([^)]+)\)")
UAV_POS_FINAL_RE = re.compile(r"pos_final=\(([^)]+)\)")


# ─── MATLAB-style rcParams ───────────────────────────────────────────────────

def _apply_matlab_style():
    import matplotlib.pyplot as plt

    plt.rcParams.update({
        "figure.figsize": (8, 8),
        "figure.dpi": 150,
        "axes.grid": True,
        "grid.alpha": 0.3,
        "grid.linestyle": "--",
        "axes.axisbelow": True,
        "font.family": "serif",
        "font.serif": ["Times New Roman", "DejaVu Serif"],
        "font.size": 12,
        "axes.labelsize": 14,
        "axes.titlesize": 16,
        "legend.fontsize": 11,
        "axes.facecolor": "white",
        "figure.facecolor": "white",
        "axes.edgecolor": "black",
        "axes.linewidth": 1.0,
        "xtick.direction": "in",
        "ytick.direction": "in",
        "xtick.major.size": 5,
        "ytick.major.size": 5,
    })


# ─── Data loading ────────────────────────────────────────────────────────────

def _resolve_run_dir(run_dir_arg: str | None) -> Path:
    if run_dir_arg:
        path = Path(run_dir_arg)
        if not path.is_absolute():
            path = ROOT / path
    else:
        candidates = sorted(
            p for p in (ROOT / "discussion").glob("20*_*") if p.is_dir()
        )
        if not candidates:
            raise FileNotFoundError("no discussion/YYYYMMDD_* directories found")
        path = candidates[-1]
    if not path.is_dir():
        raise FileNotFoundError(f"run_dir not found: {path}")
    return path


def _collect_generation_files(run_dir: Path) -> list[tuple[int, Path]]:
    files = []
    for p in run_dir.glob("population_result_*.json"):
        m = GEN_FILE_RE.match(p.name)
        if m:
            files.append((int(m.group(1)), p))
    return sorted(files)


def _load_generation(path: Path) -> list[dict] | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"WARN: skip unreadable JSON {path}: {exc}", file=sys.stderr)
        return None
    if not isinstance(data, list):
        return None
    return data


def _select_individual(population: list[dict], choice: str) -> dict:
    if choice == "best":
        scored = []
        for ind in population:
            try:
                scored.append((float(ind["evaluation_score"]), ind))
            except (KeyError, TypeError, ValueError):
                pass
        if not scored:
            raise ValueError("no individuals with evaluation_score found")
        scored.sort(key=lambda x: x[0])
        return scored[0][1]
    else:
        idx = int(choice)
        if idx < 0 or idx >= len(population):
            raise IndexError(f"individual index {idx} out of range [0, {len(population) - 1}]")
        return population[idx]


def _parse_task_positions(task_info: str) -> dict[int, tuple[float, float]]:
    positions = {}
    for line in task_info.splitlines():
        m_task = re.match(r"Task\s+(\d+):", line)
        m_pos = TASK_POS_RE.search(line)
        if m_task and m_pos:
            tid = int(m_task.group(1))
            coords = m_pos.group(1).split(",")
            positions[tid] = (float(coords[0].strip()), float(coords[1].strip()))
    return positions


def _parse_uav_positions(uav_info: str) -> tuple[dict[int, tuple[float, float]], dict[int, tuple[float, float]]]:
    start_positions = {}
    end_positions = {}
    for line in uav_info.splitlines():
        m_uav = re.match(r"UAV\s+(\d+):", line)
        if not m_uav:
            continue
        uid = int(m_uav.group(1))
        m_start = UAV_POS_RE.search(line)
        m_end = UAV_POS_FINAL_RE.search(line)
        if m_start:
            coords = m_start.group(1).split(",")
            start_positions[uid] = (float(coords[0].strip()), float(coords[1].strip()))
        if m_end:
            coords = m_end.group(1).split(",")
            end_positions[uid] = (float(coords[0].strip()), float(coords[1].strip()))
    return start_positions, end_positions


def _extract_trajectories(snapshot: dict) -> dict[int, np.ndarray]:
    """Extract q[j][t] -> dict[uav_id, ndarray(T, 2)]."""
    q_raw = snapshot["q"]
    trajectories = {}
    for uav_key in sorted(q_raw.keys(), key=int):
        uav_id = int(uav_key)
        timeslots = q_raw[uav_key]
        T = len(timeslots)
        arr = np.zeros((T, 2))
        for t_key in sorted(timeslots.keys(), key=int):
            t = int(t_key)
            arr[t] = timeslots[t_key]
        trajectories[uav_id] = arr
    return trajectories


def _extract_assignments(snapshot: dict, n_tasks: int) -> dict[int, list[int]]:
    """From f_edge[j][i][t], determine which tasks are assigned to each UAV.

    Returns dict[uav_id, list[task_id]].
    """
    f_edge = snapshot.get("f_edge", {})
    assignments: dict[int, list[int]] = {}
    for uav_key in sorted(f_edge.keys(), key=int):
        uav_id = int(uav_key)
        assigned = []
        for task_key in sorted(f_edge[uav_key].keys(), key=int):
            task_id = int(task_key)
            timeslots = f_edge[uav_key][task_key]
            if any(float(v) > 0 for v in timeslots.values()):
                assigned.append(task_id)
        assignments[uav_id] = assigned
    return assignments


# ─── Plotting ────────────────────────────────────────────────────────────────

def _plot_trajectory(
    ax,
    trajectories: dict[int, np.ndarray],
    task_positions: dict[int, tuple[float, float]],
    depot_pos: tuple[float, float],
    *,
    title: str = "UAV Trajectory Optimization",
):
    import matplotlib.pyplot as plt

    # Plot UAV trajectories
    for uav_id, traj in trajectories.items():
        color = UAV_COLORS[uav_id % len(UAV_COLORS)]
        T = traj.shape[0]

        # Main trajectory line
        ax.plot(traj[:, 0], traj[:, 1], "-", color=color, linewidth=2.0,
                label=f"UAV {uav_id}", zorder=3)

        # Timeslot markers — small dots, label every 5
        for t in range(T):
            ax.plot(traj[t, 0], traj[t, 1], ".", color=color, markersize=3, zorder=4)
            if t > 0 and t % 5 == 0:
                ax.annotate(str(t), (traj[t, 0], traj[t, 1]),
                            fontsize=7, color=color, ha="left", va="bottom",
                            xytext=(3, 3), textcoords="offset points", zorder=5)

        # Direction arrows at ~25% and ~75% of trajectory
        for frac in (0.25, 0.75):
            idx = int(frac * (T - 1))
            if idx + 1 < T:
                ax.annotate(
                    "", xy=(traj[idx + 1, 0], traj[idx + 1, 1]),
                    xytext=(traj[idx, 0], traj[idx, 1]),
                    arrowprops=dict(arrowstyle="->", color=color, lw=2.0),
                    zorder=4,
                )

        # Start marker (circle)
        ax.plot(traj[0, 0], traj[0, 1], "o", color=color, markersize=10,
                markeredgecolor="black", markeredgewidth=0.8, zorder=6)

        # End marker (triangle)
        ax.plot(traj[-1, 0], traj[-1, 1], "^", color=color, markersize=10,
                markeredgecolor="black", markeredgewidth=0.8, zorder=6)

    # Plot tasks
    for tid, (tx, ty) in sorted(task_positions.items()):
        ax.plot(tx, ty, "s", color=TASK_COLOR, markersize=7,
                markeredgecolor="black", markeredgewidth=0.5, zorder=5)
        ax.annotate(f"Task {tid}", (tx, ty), fontsize=6, color=TASK_COLOR,
                    ha="center", va="top", xytext=(0, -8), textcoords="offset points",
                    zorder=5)

    # Plot depot
    ax.plot(depot_pos[0], depot_pos[1], "*", color=DEPOT_COLOR, markersize=18,
            markeredgecolor="black", markeredgewidth=0.5, zorder=7)
    ax.annotate("Depot", (depot_pos[0], depot_pos[1]), fontsize=10, fontweight="bold",
                color=DEPOT_COLOR, ha="center", va="bottom",
                xytext=(0, 12), textcoords="offset points", zorder=7)

    # Axes
    ax.set_xlabel("x (m)")
    ax.set_ylabel("y (m)")
    ax.set_title(title)
    ax.set_aspect("equal")
    ax.legend(loc="upper right")

    # Auto-compute axis limits with padding
    all_x, all_y = [], []
    for traj in trajectories.values():
        all_x.extend(traj[:, 0])
        all_y.extend(traj[:, 1])
    for tx, ty in task_positions.values():
        all_x.append(tx)
        all_y.append(ty)
    all_x.append(depot_pos[0])
    all_y.append(depot_pos[1])

    x_min, x_max = min(all_x), max(all_x)
    y_min, y_max = min(all_y), max(all_y)
    pad = max(x_max - x_min, y_max - y_min) * 0.08
    ax.set_xlim(x_min - pad, x_max + pad)
    ax.set_ylim(y_min - pad, y_max + pad)

    # Map boundary (dashed rectangle at [0, x_max_area] x [0, y_max_area])
    area_max = max(x_max + pad, y_max + pad)
    area_min = min(0, x_min - pad)
    ax.plot(
        [area_min, area_max, area_max, area_min, area_min],
        [area_min, area_min, area_max, area_max, area_min],
        "--", color="gray", linewidth=0.8, alpha=0.5, zorder=1,
    )


def _plot_assignment(
    ax,
    trajectories: dict[int, np.ndarray],
    task_positions: dict[int, tuple[float, float]],
    depot_pos: tuple[float, float],
    assignments: dict[int, list[int]],
    *,
    title: str = "UAV Trajectory + Task Assignment",
):
    # First draw the base trajectory
    _plot_trajectory(ax, trajectories, task_positions, depot_pos, title=title)

    # Determine assigned tasks (for gray marking of unassigned)
    all_assigned = set()
    for tasks in assignments.values():
        all_assigned.update(tasks)

    # Draw assignment lines at mid-timeslot
    for uav_id, assigned_tasks in assignments.items():
        color = UAV_COLORS[uav_id % len(UAV_COLORS)]
        traj = trajectories[uav_id]
        mid_t = traj.shape[0] // 2
        uav_pos = traj[mid_t]

        for tid in assigned_tasks:
            if tid not in task_positions:
                continue
            tx, ty = task_positions[tid]
            ax.plot(
                [uav_pos[0], tx], [uav_pos[1], ty],
                "--", color=color, linewidth=0.8, alpha=0.5, zorder=2,
            )

    # Mark unassigned tasks in gray
    for tid, (tx, ty) in task_positions.items():
        if tid not in all_assigned:
            ax.plot(tx, ty, "s", color=UNASSIGNED_COLOR, markersize=7,
                    markeredgecolor="gray", markeredgewidth=0.5, zorder=5)


# ─── Main ────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="UAV trajectory 2D visualization — MATLAB style")
    parser.add_argument("--run-dir", help="Result directory (default: latest discussion/)")
    parser.add_argument("--gen", type=int, default=None, help="Generation number (default: last)")
    parser.add_argument("--individual", default="best", help="'best' or index (default: best)")
    parser.add_argument("--mode", choices=["trajectory", "assignment", "both"], default="both",
                        help="Plot mode (default: both)")
    parser.add_argument("--save", default=None, help="Save to file (PNG/PDF), e.g. trajectory.pdf")
    parser.add_argument("--no-show", action="store_true", help="Do not display the plot window")
    args = parser.parse_args()

    # ── Resolve run directory and generation ──
    try:
        run_dir = _resolve_run_dir(args.run_dir)
    except FileNotFoundError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    gen_files = _collect_generation_files(run_dir)
    if not gen_files:
        print(f"ERROR: no population_result_*.json found in {run_dir}", file=sys.stderr)
        return 1

    if args.gen is not None:
        target_gen = args.gen
    else:
        target_gen = gen_files[-1][0]

    gen_path = None
    for g, p in gen_files:
        if g == target_gen:
            gen_path = p
            break
    if gen_path is None:
        available = [g for g, _ in gen_files]
        print(f"ERROR: generation {target_gen} not found. Available: {available}", file=sys.stderr)
        return 1

    # ── Load data ──
    population = _load_generation(gen_path)
    if population is None:
        print(f"ERROR: failed to load {gen_path}", file=sys.stderr)
        return 1

    try:
        individual = _select_individual(population, args.individual)
    except (ValueError, IndexError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    step0 = get_simulation_step(individual, "0")
    if not step0:
        print("ERROR: no simulation step 0 found in individual", file=sys.stderr)
        return 1

    if not step0.get("bcd_enabled", False):
        print("ERROR: BCD not enabled for this individual — no trajectory data available.", file=sys.stderr)
        print("Hint: run with bcd_enabled=True to generate trajectory data.", file=sys.stderr)
        return 1

    bcd_meta = step0.get("bcd_meta", {})
    snapshot = bcd_meta.get("optimal_snapshot", {})
    if not snapshot or "q" not in snapshot:
        print("ERROR: no optimal_snapshot.q found in bcd_meta", file=sys.stderr)
        return 1

    # ── Extract data ──
    trajectories = _extract_trajectories(snapshot)
    task_positions = _parse_task_positions(step0.get("task_info", ""))
    uav_starts, uav_ends = _parse_uav_positions(step0.get("uav_info", ""))

    # Depot = UAV 0 start position (all UAVs share the same depot)
    depot_pos = uav_starts.get(0, (250.0, 250.0))

    run_id = run_dir.name
    score = individual.get("evaluation_score", "N/A")
    if isinstance(score, float):
        score = f"{score:.4f}"

    print(f"run_dir: {run_dir}")
    print(f"generation: {target_gen}  individual: {args.individual}  score: {score}")
    print(f"UAVs: {len(trajectories)}  tasks: {len(task_positions)}  "
          f"timeslots: {next(iter(trajectories.values())).shape[0]}")

    # ── Plot ──
    _apply_matlab_style()
    import matplotlib.pyplot as plt

    modes = []
    if args.mode in ("trajectory", "both"):
        modes.append("trajectory")
    if args.mode in ("assignment", "both"):
        modes.append("assignment")

    for mode in modes:
        fig, ax = plt.subplots()

        if mode == "trajectory":
            _plot_trajectory(
                ax, trajectories, task_positions, depot_pos,
                title=f"UAV Trajectory — {run_id} (score={score})",
            )
        else:
            assignments = _extract_assignments(snapshot, len(task_positions))
            _plot_assignment(
                ax, trajectories, task_positions, depot_pos, assignments,
                title=f"UAV Trajectory + Assignment — {run_id} (score={score})",
            )

        fig.tight_layout()

        if args.save:
            save_path = Path(args.save)
            if len(modes) > 1:
                stem = save_path.stem
                suffix = save_path.suffix
                save_path = save_path.with_name(f"{stem}_{mode}{suffix}")
            fig.savefig(str(save_path), bbox_inches="tight")
            print(f"Saved: {save_path}")

    if not args.no_show:
        plt.show()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
