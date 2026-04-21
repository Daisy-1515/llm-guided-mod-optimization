from __future__ import annotations

import argparse
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_TASKS = list(range(5, 51, 5))


def parse_args():
    parser = argparse.ArgumentParser(
        description="Run group A numTasks sweep for one uplink bandwidth."
    )
    parser.add_argument("--bandwidth", type=float, required=True, help="Uplink bandwidth B_up in Hz.")
    parser.add_argument(
        "--tasks",
        nargs="+",
        type=int,
        default=DEFAULT_TASKS,
        help="Task counts to sweep. Default: 5 10 ... 50",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=42,
        help="Scenario seed. Default: 42",
    )
    parser.add_argument(
        "--num-uavs",
        type=int,
        default=3,
        help="Number of UAVs. Default: 3",
    )
    parser.add_argument(
        "--output-root",
        default="discussion/bandwidth_sweep",
        help="Base output directory.",
    )
    parser.add_argument(
        "--hs-pop-size",
        type=int,
        default=None,
        help="Optional HS popSize override.",
    )
    parser.add_argument(
        "--hs-iterations",
        type=int,
        default=None,
        help="Optional HS iteration override.",
    )
    parser.add_argument(
        "--no-bcd-loop",
        action="store_true",
        help="Disable BCD loop.",
    )
    return parser.parse_args()


def run_once(args, task_count: int):
    output_root = Path(args.output_root) / f"bup_{args.bandwidth:.0e}" / f"tasks_{task_count}"
    command = [
        "uv",
        "run",
        "python",
        str(ROOT / "scripts" / "run_all_experiments.py"),
        "--groups",
        "A",
        "--seeds",
        str(args.seed),
        "--num-tasks",
        str(task_count),
        "--num-uavs",
        str(args.num_uavs),
        "--b-up",
        str(args.bandwidth),
        "--output-root",
        str(output_root),
    ]
    if args.hs_pop_size is not None:
        command.extend(["--hs-pop-size", str(args.hs_pop_size)])
    if args.hs_iterations is not None:
        command.extend(["--hs-iterations", str(args.hs_iterations)])
    if args.no_bcd_loop:
        command.append("--no-bcd-loop")

    print(f"[bandwidth-sweep] B_up={args.bandwidth:.0f} tasks={task_count}")
    subprocess.run(command, check=True, cwd=ROOT)


def main():
    args = parse_args()
    for task_count in args.tasks:
        run_once(args, task_count)
    print(
        f"[bandwidth-sweep] done B_up={args.bandwidth:.0f} seed={args.seed} tasks={args.tasks}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
