"""Diagnostic runner for Edge-UAV offloading feasibility and BCD impact.

This script is intentionally narrower than run_all_experiments.py:
it focuses on answering two questions before any paper-scale experiment:

1. Which scenario variants actually permit meaningful offloading?
2. On those variants, does BCD change the evaluated solution under the
   fixed default objective?
"""

from __future__ import annotations

import argparse
import json
import sys
from copy import deepcopy
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from config.config import configPara
from edge_uav.model.bcd_loop import run_bcd_loop
from edge_uav.model.evaluator import INVALID_OUTPUT_PENALTY, evaluate_solution
from edge_uav.model.offloading import OffloadingModel
from edge_uav.model.precompute import (
    PrecomputeParams,
    make_initial_level2_snapshot,
    precompute_offloading_inputs,
)
from edge_uav.model.trajectory_opt import TrajectoryOptParams
from edge_uav.scenario_generator import EdgeUavScenarioGenerator


@dataclass(frozen=True)
class ScenarioCase:
    name: str
    config_overrides: dict[str, float | int]
    task_mode: str = "baseline"


CASES: tuple[ScenarioCase, ...] = (
    ScenarioCase(
        name="baseline_default",
        config_overrides={},
        task_mode="baseline",
    ),
    ScenarioCase(
        name="relaxed_tau_low_local",
        config_overrides={},
        task_mode="relaxed_tau_low_local",
    ),
    ScenarioCase(
        name="mixed_local_vs_offload",
        config_overrides={},
        task_mode="mixed_local_vs_offload",
    ),
    ScenarioCase(
        name="single_uav_relaxed",
        config_overrides={"numUAVs": 1},
        task_mode="relaxed_tau_low_local",
    ),
    ScenarioCase(
        name="three_uav_relaxed",
        config_overrides={"numUAVs": 3},
        task_mode="relaxed_tau_low_local",
    ),
    ScenarioCase(
        name="small_map_300_three_uav_relaxed",
        config_overrides={
            "numUAVs": 3,
            "x_max": 300.0,
            "y_max": 300.0,
            "depot_x": 150.0,
            "depot_y": 150.0,
        },
        task_mode="relaxed_tau_low_local",
    ),
    ScenarioCase(
        name="small_map_500_three_uav_relaxed",
        config_overrides={
            "numUAVs": 3,
            "x_max": 500.0,
            "y_max": 500.0,
            "depot_x": 250.0,
            "depot_y": 250.0,
        },
        task_mode="relaxed_tau_low_local",
    ),
    ScenarioCase(
        name="comm_boosted_relaxed",
        config_overrides={"B_up": 5e6, "B_down": 5e6, "P_i": 1.0, "P_j": 2.0},
        task_mode="relaxed_tau_low_local",
    ),
    ScenarioCase(
        name="more_uavs_high_freq_relaxed",
        config_overrides={"numUAVs": 5, "f_max": 2e10},
        task_mode="relaxed_tau_low_local",
    ),
)


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--seeds",
        nargs="+",
        type=int,
        default=[42],
        help="Scenario seeds to evaluate.",
    )
    parser.add_argument(
        "--output-root",
        default="discussion/diagnostics",
        help="Directory used to store diagnostic summaries.",
    )
    return parser.parse_args()


def make_config(seed: int, overrides: dict[str, float | int]) -> configPara:
    config = configPara(None, None)
    config.getConfigInfo()
    config.scenario_seed = seed
    config.use_bcd_loop = False
    config.popSize = 1
    config.iteration = 1
    for key, value in overrides.items():
        setattr(config, key, value)
    return config


def apply_task_mode(scenario, task_mode: str):
    task_ids = sorted(scenario.tasks.keys())
    midpoint = len(task_ids) // 2
    for idx, task_id in enumerate(task_ids):
        task = scenario.tasks[task_id]
        if task_mode == "baseline":
            continue
        if task_mode == "relaxed_tau_low_local":
            task.tau = 200.0
            task.f_local = 1e6
        elif task_mode == "mixed_local_vs_offload":
            task.tau = 200.0
            task.f_local = 1e9 if idx < midpoint else 1e6
        else:
            raise ValueError(f"Unknown task_mode: {task_mode}")


def make_traj_params(config: configPara) -> TrajectoryOptParams:
    return TrajectoryOptParams(
        eta_1=float(config.eta_1),
        eta_2=float(config.eta_2),
        eta_3=float(config.eta_3),
        eta_4=float(config.eta_4),
        v_tip=float(config.v_tip),
        v_max=float(getattr(config, "v_traj_max", config.v_U_max)),
        d_safe=float(getattr(config, "d_safe_traj", config.d_U_safe)),
    )


def count_assignments(outputs: dict) -> dict[str, int]:
    local_count = sum(len(slot.get("local", [])) for slot in outputs.values())
    offload_count = sum(
        len(task_ids)
        for slot in outputs.values()
        for task_ids in slot.get("offload", {}).values()
    )
    return {"local": local_count, "offload": offload_count}


def run_level1_only(scenario, params: PrecomputeParams, precompute_result, config: configPara):
    model = OffloadingModel(
        tasks=scenario.tasks,
        uavs=scenario.uavs,
        time_list=scenario.time_slots,
        D_hat_local=precompute_result.D_hat_local,
        D_hat_offload=precompute_result.D_hat_offload,
        E_hat_comp=precompute_result.E_hat_comp,
        alpha=float(config.alpha),
        gamma_w=float(config.gamma_w),
    )
    feasible, solver_cost = model.solveProblem()
    outputs = model.getOutputs()
    score = evaluate_solution(outputs, precompute_result, scenario)
    counts = count_assignments(outputs)
    return {
        "feasible": bool(feasible),
        "solver_cost": float(solver_cost),
        "evaluation_score": float(score),
        "assignment_counts": counts,
    }


def run_bcd_default(scenario, params: PrecomputeParams, config: configPara):
    initial_snapshot = make_initial_level2_snapshot(scenario)
    try:
        bcd_result = run_bcd_loop(
            scenario=scenario,
            config=config,
            params=params,
            traj_params=make_traj_params(config),
            dynamic_obj_func=None,
            initial_snapshot=initial_snapshot,
            max_bcd_iter=int(getattr(config, "bcd_max_iter", 5)),
            eps_bcd=float(getattr(config, "bcd_eps", 1e-3)),
            cost_rollback_delta=float(getattr(config, "bcd_rollback_delta", 0.05)),
            max_rollbacks=int(getattr(config, "bcd_max_rollbacks", 2)),
        )
        final_precompute = precompute_offloading_inputs(
            scenario,
            params,
            bcd_result.snapshot,
            mu=None,
            active_only=True,
        )
        score = evaluate_solution(
            bcd_result.offloading_outputs,
            final_precompute,
            scenario,
        )
        counts = count_assignments(bcd_result.offloading_outputs)
        return {
            "status": "ok",
            "feasible": bool(bcd_result.converged),
            "solver_cost": float(bcd_result.total_cost),
            "evaluation_score": float(score),
            "assignment_counts": counts,
            "bcd_iterations": int(bcd_result.bcd_iterations),
            "bcd_converged": bool(bcd_result.converged),
            "cost_history": list(bcd_result.cost_history),
            "solution_details": dict(bcd_result.solution_details),
            "final_precompute_diagnostics": final_precompute.diagnostics,
        }
    except Exception as exc:
        return {
            "status": "error",
            "error": str(exc),
            "feasible": False,
            "solver_cost": float(INVALID_OUTPUT_PENALTY),
            "evaluation_score": float(INVALID_OUTPUT_PENALTY),
            "assignment_counts": {"local": 0, "offload": 0},
        }


def run_case(case: ScenarioCase, seed: int):
    config = make_config(seed, case.config_overrides)
    scenario = EdgeUavScenarioGenerator().getScenarioInfo(config)
    apply_task_mode(scenario, case.task_mode)

    params = PrecomputeParams.from_config(config)
    initial_snapshot = make_initial_level2_snapshot(scenario)
    initial_precompute = precompute_offloading_inputs(
        scenario,
        params,
        initial_snapshot,
        mu=None,
        active_only=True,
    )

    baseline = run_level1_only(scenario, params, initial_precompute, config)

    bcd_config = deepcopy(config)
    bcd_config.use_bcd_loop = True
    bcd = run_bcd_default(scenario, params, bcd_config)

    return {
        "case": case.name,
        "seed": seed,
        "task_mode": case.task_mode,
        "config_overrides": case.config_overrides,
        "initial_diagnostics": initial_precompute.diagnostics,
        "baseline_level1": baseline,
        "bcd_default": bcd,
        "delta_evaluation_score": (
            bcd["evaluation_score"] - baseline["evaluation_score"]
        ),
        "delta_offload_count": (
            bcd["assignment_counts"]["offload"] - baseline["assignment_counts"]["offload"]
        ),
    }


def main():
    args = parse_args()
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_dir = Path(args.output_root) / f"edge_uav_bcd_diag_{timestamp}"
    output_dir.mkdir(parents=True, exist_ok=True)

    summary = {
        "created_at": timestamp,
        "cases": [asdict(case) for case in CASES],
        "seeds": list(args.seeds),
        "results": [],
    }

    for seed in args.seeds:
        for case in CASES:
            print(f"[diag] case={case.name} seed={seed}")
            result = run_case(case, seed)
            summary["results"].append(result)

    output_path = output_dir / "summary.json"
    output_path.write_text(
        json.dumps(summary, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    print(f"[diag] wrote {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
