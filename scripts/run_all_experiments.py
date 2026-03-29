"""Batch runner for the LLM-HS Edge-UAV experiment suite.

This script standardizes experiment outputs across:

- A: LLM + HS
- B: LLM only
- C1: random-template + HS
- C2: parametric-weight + HS
- D1: default objective
- D2: manually tuned default objective
"""

from __future__ import annotations

import argparse
import json
import statistics
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from script_common import (
    apply_config_overrides,
    clone_config,
    get_simulation_step,
    load_config,
    make_edge_uav_scenario,
    make_edge_uav_solver,
    write_json,
)
from edge_uav.model.evaluator import INVALID_OUTPUT_PENALTY, evaluate_solution
from edge_uav.model.offloading import OffloadingModel
from edge_uav.model.precompute import (
    PrecomputeParams,
    make_initial_level2_snapshot,
    precompute_offloading_inputs,
)
from heuristics.hsIndividualEdgeUav import hsIndividualEdgeUav
from heuristics.hs_way_constants import WAY_RANDOM


DEFAULT_GROUPS = ("A", "B", "C1", "C2", "D1")
ALL_GROUPS = frozenset({"A", "B", "C1", "C2", "D1", "D2"})
SCHEMA_VERSION = "experiment-run-v1"


@dataclass(frozen=True)
class ScenarioBundle:
    scenario: object
    precompute: object
    params: object


def parse_args():
    parser = argparse.ArgumentParser(description="Run the Edge-UAV experiment suite.")
    parser.add_argument(
        "--groups",
        nargs="+",
        default=list(DEFAULT_GROUPS),
        help="Subset of groups to run. Default: %(default)s",
    )
    parser.add_argument(
        "--seeds",
        nargs="+",
        type=int,
        default=[42, 43, 44],
        help="Scenario seeds for repeated runs. Default: %(default)s",
    )
    parser.add_argument(
        "--output-root",
        default="discussion/experiment_results",
        help="Directory used to store experiment outputs.",
    )
    parser.add_argument(
        "--manual-alpha",
        type=float,
        default=None,
        help="Manual alpha used by D2.",
    )
    parser.add_argument(
        "--manual-gamma",
        type=float,
        default=None,
        help="Manual gamma used by D2.",
    )
    parser.add_argument(
        "--hs-pop-size",
        type=int,
        default=None,
        help="Override popSize for HS-based groups.",
    )
    parser.add_argument(
        "--hs-iterations",
        type=int,
        default=None,
        help="Override iteration for HS-based groups.",
    )
    parser.add_argument(
        "--use-bcd-loop",
        action="store_true",
        help="Enable BCD loop for all groups. Default stays off.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the planned runs without executing them.",
    )
    return parser.parse_args()


def make_params(args):
    params = load_config()
    apply_config_overrides(
        params,
        pop_size=args.hs_pop_size,
        iteration=args.hs_iterations,
        use_bcd_loop=args.use_bcd_loop,
    )
    return params


def make_scenario_bundle(base_params, seed):
    params = clone_config(base_params)
    apply_config_overrides(params, scenario_seed=seed)
    scenario = make_edge_uav_scenario(params)
    precompute = precompute_offloading_inputs(
        scenario,
        PrecomputeParams.from_config(params),
        make_initial_level2_snapshot(scenario),
    )
    return ScenarioBundle(scenario=scenario, precompute=precompute, params=params)


def flatten_evaluations(evaluation_history):
    flattened = []
    evaluation_index = 1
    for generation_record in evaluation_history:
        generation = generation_record["generation"]
        for individual in generation_record["individuals"]:
            step = get_simulation_step(individual)
            score = float(individual.get("evaluation_score", INVALID_OUTPUT_PENALTY))
            flattened.append(
                {
                    "evaluation_index": evaluation_index,
                    "generation": generation,
                    "score": score,
                    "feasible": bool(step.get("feasible", False)),
                    "llm_status": step.get("llm_status", "unknown"),
                    "used_default_obj": bool(step.get("used_default_obj", True)),
                    "solver_cost": float(step.get("solver_cost", -1.0)),
                    "response_format": step.get("response_format", ""),
                }
            )
            evaluation_index += 1
    return flattened


def summarize_history(history):
    scores = [row["score"] for row in history]
    feasible = [row["feasible"] for row in history]
    if not scores:
        return {
            "best_cost": float(INVALID_OUTPUT_PENALTY),
            "mean_cost": float(INVALID_OUTPUT_PENALTY),
            "std_cost": 0.0,
            "feasible_rate": 0.0,
            "best_so_far": [],
        }

    best_so_far = []
    running_best = float("inf")
    for row in history:
        running_best = min(running_best, row["score"])
        best_so_far.append(
            {
                "evaluation_index": row["evaluation_index"],
                "best_cost": running_best,
            }
        )

    return {
        "best_cost": min(scores),
        "mean_cost": statistics.fmean(scores),
        "std_cost": statistics.pstdev(scores) if len(scores) > 1 else 0.0,
        "feasible_rate": sum(feasible) / len(feasible),
        "best_so_far": best_so_far,
    }


def run_group_a(bundle):
    solver = make_edge_uav_solver(bundle.params, bundle.scenario)
    started = time.time()
    solver.run()
    wall_time_sec = time.time() - started
    history = flatten_evaluations(solver.evaluation_history)
    metrics = summarize_history(history)
    return {
        "group": "A",
        "label": "llm_hs",
        "eval_budget_target": bundle.params.popSize * bundle.params.iteration,
        "eval_budget_used": len(history),
        "llm_calls": len(history),
        "wall_time_sec": wall_time_sec,
        "source_run_dir": solver.out_dir,
        "history": history,
        "metrics": metrics,
    }


def run_group_b(bundle):
    history = []
    eval_budget = bundle.params.popSize * bundle.params.iteration
    started = time.time()
    for evaluation_index in range(1, eval_budget + 1):
        individual = hsIndividualEdgeUav(
            bundle.params,
            bundle.scenario,
            shared_precompute=bundle.precompute,
        )
        individual.runOptModel("", WAY_RANDOM)
        step = individual.promptHistory["simulation_steps"]["0"]
        history.append(
            {
                "evaluation_index": evaluation_index,
                "generation": 0,
                "score": float(individual.promptHistory["evaluation_score"]),
                "feasible": bool(step.get("feasible", False)),
                "llm_status": step.get("llm_status", "unknown"),
                "used_default_obj": bool(step.get("used_default_obj", True)),
                "solver_cost": float(step.get("solver_cost", -1.0)),
                "response_format": step.get("response_format", ""),
            }
        )
    wall_time_sec = time.time() - started
    return {
        "group": "B",
        "label": "llm_only",
        "eval_budget_target": eval_budget,
        "eval_budget_used": len(history),
        "llm_calls": len(history),
        "wall_time_sec": wall_time_sec,
        "history": history,
        "metrics": summarize_history(history),
    }


def run_group_random_hs(bundle, mode, group_name):
    params = clone_config(bundle.params)
    apply_config_overrides(params, extra={"random_hs_mode": mode})
    solver = make_edge_uav_solver(
        params,
        bundle.scenario,
        individual_type="edge_uav_random",
    )
    started = time.time()
    solver.run()
    wall_time_sec = time.time() - started
    history = flatten_evaluations(solver.evaluation_history)
    return {
        "group": group_name,
        "label": f"random_hs_{mode}",
        "eval_budget_target": params.popSize * params.iteration,
        "eval_budget_used": len(history),
        "llm_calls": 0,
        "wall_time_sec": wall_time_sec,
        "source_run_dir": solver.out_dir,
        "history": history,
        "metrics": summarize_history(history),
    }


def solve_default_objective(bundle, *, alpha, gamma_w, evaluation_index):
    model = OffloadingModel(
        tasks=bundle.scenario.tasks,
        uavs=bundle.scenario.uavs,
        time_list=bundle.scenario.time_slots,
        D_hat_local=bundle.precompute.D_hat_local,
        D_hat_offload=bundle.precompute.D_hat_offload,
        E_hat_comp=bundle.precompute.E_hat_comp,
        alpha=alpha,
        gamma_w=gamma_w,
        dynamic_obj_func=None,
    )
    feasible, solver_cost = model.solveProblem()
    outputs = model.getOutputs()
    score = evaluate_solution(outputs, bundle.precompute, bundle.scenario)
    return {
        "evaluation_index": evaluation_index,
        "generation": 0,
        "score": float(score),
        "feasible": bool(feasible),
        "llm_status": "default",
        "used_default_obj": True,
        "solver_cost": float(solver_cost),
        "response_format": model.error_message or "",
    }


def run_group_default(bundle, *, group_name, alpha, gamma_w):
    eval_budget = bundle.params.popSize * bundle.params.iteration
    history = []
    started = time.time()
    for evaluation_index in range(1, eval_budget + 1):
        history.append(
            solve_default_objective(
                bundle,
                alpha=alpha,
                gamma_w=gamma_w,
                evaluation_index=evaluation_index,
            )
        )
    wall_time_sec = time.time() - started
    return {
        "group": group_name,
        "label": "default_objective",
        "eval_budget_target": eval_budget,
        "eval_budget_used": len(history),
        "llm_calls": 0,
        "wall_time_sec": wall_time_sec,
        "history": history,
        "metrics": summarize_history(history),
    }


def build_run_payload(result, seed, bundle):
    return {
        "schema_version": SCHEMA_VERSION,
        "group": result["group"],
        "label": result["label"],
        "seed": seed,
        "scenario": {
            "numTasks": bundle.params.numTasks,
            "numUAVs": bundle.params.numUAVs,
            "T": bundle.params.T,
            "use_bcd_loop": bool(bundle.params.use_bcd_loop),
        },
        "search": {
            "pop_size": bundle.params.popSize,
            "iterations": bundle.params.iteration,
            "eval_budget_target": result["eval_budget_target"],
            "eval_budget_used": result["eval_budget_used"],
            "llm_calls": result["llm_calls"],
        },
        "wall_time_sec": result["wall_time_sec"],
        "source_run_dir": result.get("source_run_dir"),
        "metrics": result["metrics"],
        "history": result["history"],
    }


def summarize_group_runs(run_payloads):
    best_costs = [payload["metrics"]["best_cost"] for payload in run_payloads]
    feasible_rates = [payload["metrics"]["feasible_rate"] for payload in run_payloads]
    wall_times = [payload["wall_time_sec"] for payload in run_payloads]
    return {
        "schema_version": SCHEMA_VERSION,
        "group": run_payloads[0]["group"],
        "runs": len(run_payloads),
        "seeds": [payload["seed"] for payload in run_payloads],
        "best_cost_mean": statistics.fmean(best_costs),
        "best_cost_std": statistics.pstdev(best_costs) if len(best_costs) > 1 else 0.0,
        "best_cost_min": min(best_costs),
        "feasible_rate_mean": statistics.fmean(feasible_rates),
        "wall_time_mean_sec": statistics.fmean(wall_times),
    }


def validate_groups(groups, args):
    invalid = [group for group in groups if group not in ALL_GROUPS]
    if invalid:
        raise ValueError(f"Unsupported groups: {', '.join(invalid)}")
    if "D2" in groups and (args.manual_alpha is None or args.manual_gamma is None):
        raise ValueError("D2 requires both --manual-alpha and --manual-gamma")


def run_group(group, bundle, args):
    if group == "A":
        return run_group_a(bundle)
    if group == "B":
        return run_group_b(bundle)
    if group == "C1":
        return run_group_random_hs(bundle, mode="template", group_name="C1")
    if group == "C2":
        return run_group_random_hs(bundle, mode="parametric", group_name="C2")
    if group == "D1":
        return run_group_default(
            bundle,
            group_name="D1",
            alpha=bundle.params.alpha,
            gamma_w=bundle.params.gamma_w,
        )
    if group == "D2":
        return run_group_default(
            bundle,
            group_name="D2",
            alpha=args.manual_alpha,
            gamma_w=args.manual_gamma,
        )
    raise ValueError(f"Unhandled group: {group}")


def main():
    args = parse_args()
    groups = tuple(args.groups)
    validate_groups(groups, args)

    base_params = make_params(args)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_root = Path(args.output_root) / timestamp

    if args.dry_run:
        print(
            json.dumps(
                {
                    "groups": groups,
                    "seeds": args.seeds,
                    "output_root": str(output_root),
                    "hs_pop_size": base_params.popSize,
                    "hs_iterations": base_params.iteration,
                    "use_bcd_loop": bool(base_params.use_bcd_loop),
                },
                indent=2,
            )
        )
        return 0

    manifest = {
        "schema_version": SCHEMA_VERSION,
        "created_at": timestamp,
        "groups": groups,
        "seeds": args.seeds,
        "hs_pop_size": base_params.popSize,
        "hs_iterations": base_params.iteration,
        "use_bcd_loop": bool(base_params.use_bcd_loop),
        "manual_alpha": args.manual_alpha,
        "manual_gamma": args.manual_gamma,
    }
    write_json(output_root / "manifest.json", manifest)

    group_payloads = {group: [] for group in groups}

    for seed in args.seeds:
        bundle = make_scenario_bundle(base_params, seed)
        for group in groups:
            print(f"[experiment] group={group} seed={seed}")
            result = run_group(group, bundle, args)
            payload = build_run_payload(result, seed, bundle)
            group_payloads[group].append(payload)
            write_json(
                output_root / group / f"run_seed_{seed}.json",
                payload,
            )

    comparison = {}
    for group, payloads in group_payloads.items():
        summary = summarize_group_runs(payloads)
        comparison[group] = summary
        write_json(output_root / group / "summary.json", summary)

    write_json(output_root / "comparison_summary.json", comparison)
    print(f"[experiment] results written to {output_root}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
