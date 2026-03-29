"""Shared helpers for command-line scripts in this repository."""

from __future__ import annotations

import json
import sys
from copy import deepcopy
from datetime import datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

DEFAULT_HS_TIMEOUT_SEC = 600
DEFAULT_RELAXED_TASK_TAU = 200.0
DEFAULT_RELAXED_TASK_LOCAL_FREQ = 1e6


def load_config(config_path: str | None = None, env_path: str | None = None):
    from config.config import configPara

    params = configPara(config_path, env_path)
    params.getConfigInfo()
    return params


def clone_config(params):
    return deepcopy(params)


def apply_config_overrides(
    params,
    *,
    pop_size: int | None = None,
    iteration: int | None = None,
    use_bcd_loop: bool | None = None,
    scenario_seed: int | None = None,
    extra: dict[str, Any] | None = None,
):
    if pop_size is not None:
        params.popSize = pop_size
    if iteration is not None:
        params.iteration = iteration
    if use_bcd_loop is not None:
        params.use_bcd_loop = bool(use_bcd_loop)
    if scenario_seed is not None:
        params.scenario_seed = scenario_seed
    for key, value in (extra or {}).items():
        setattr(params, key, value)
    return params


def make_edge_uav_scenario(params):
    from edge_uav.scenario_generator import EdgeUavScenarioGenerator

    return EdgeUavScenarioGenerator().getScenarioInfo(params)


def make_edge_uav_solver(
    params,
    scenario,
    *,
    individual_type: str = "edge_uav",
    timeout: int = DEFAULT_HS_TIMEOUT_SEC,
):
    from heuristics.hsFrame import HarmonySearchSolver

    solver = HarmonySearchSolver(params, scenario, individual_type=individual_type)
    solver.pop.timeout = timeout
    return solver


def apply_task_profile(scenario, task_mode: str):
    if task_mode == "baseline":
        return scenario

    task_ids = sorted(scenario.tasks.keys())
    midpoint = len(task_ids) // 2

    for idx, task_id in enumerate(task_ids):
        task = scenario.tasks[task_id]
        if task_mode == "relaxed_tau_low_local":
            task.tau = DEFAULT_RELAXED_TASK_TAU
            task.f_local = DEFAULT_RELAXED_TASK_LOCAL_FREQ
        elif task_mode == "mixed_local_vs_offload":
            task.tau = DEFAULT_RELAXED_TASK_TAU
            task.f_local = 1e9 if idx < midpoint else DEFAULT_RELAXED_TASK_LOCAL_FREQ
        else:
            raise ValueError(f"Unknown task_mode: {task_mode}")

    return scenario


def extract_prompt_history(individual: dict[str, Any]) -> dict[str, Any]:
    return individual.get("promptHistory", individual)


def get_simulation_steps(individual: dict[str, Any]) -> dict[str, Any]:
    return extract_prompt_history(individual).get("simulation_steps", {})


def get_simulation_step(individual: dict[str, Any], step_key: str = "0") -> dict[str, Any]:
    return get_simulation_steps(individual).get(step_key) or {}


def write_json(path: str | Path, payload: Any):
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


def make_timestamped_output_dir(
    output_root: str | Path,
    *,
    prefix: str | None = None,
    timestamp: str | None = None,
) -> tuple[str, Path]:
    resolved_timestamp = timestamp or datetime.now().strftime("%Y%m%d_%H%M%S")
    directory_name = (
        f"{prefix}_{resolved_timestamp}" if prefix else resolved_timestamp
    )
    output_dir = Path(output_root) / directory_name
    output_dir.mkdir(parents=True, exist_ok=True)
    return resolved_timestamp, output_dir
