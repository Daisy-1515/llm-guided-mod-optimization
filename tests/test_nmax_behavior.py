"""Test N_max parameter behavior during optimization.

Migrated from scripts/verify_nmax_behavior.py — converted to pytest format.
Requires gurobipy for solver execution.
"""

import pytest

gp = pytest.importorskip("gurobipy")

from config.config import configPara
from edge_uav.scenario_generator import EdgeUavScenarioGenerator
from edge_uav.model.offloading import OffloadingModel
from edge_uav.model.precompute import (
    PrecomputeParams,
    precompute_offloading_inputs,
    make_initial_level2_snapshot,
)


@pytest.fixture(scope="module")
def scenario_and_precompute():
    """Build scenario and precompute once for all N_max tests."""
    cfg = configPara(None, None)
    cfg.getConfigInfo()

    generator = EdgeUavScenarioGenerator()
    scenario = generator.getScenarioInfo(cfg)

    params = PrecomputeParams.from_config(cfg)
    snapshot = make_initial_level2_snapshot(scenario)
    precompute_result = precompute_offloading_inputs(
        scenario=scenario,
        params=params,
        snapshot=snapshot,
    )

    return cfg, scenario, precompute_result


def _solve_with_nmax(cfg, scenario, precompute_result, nmax):
    """Set N_max on all UAVs and solve."""
    for uav in scenario.uavs.values():
        uav.N_max = nmax

    model = OffloadingModel(
        tasks=scenario.tasks,
        uavs=scenario.uavs,
        time_list=scenario.time_slots,
        D_hat_local=precompute_result.D_hat_local,
        D_hat_offload=precompute_result.D_hat_offload,
        E_hat_comp=precompute_result.E_hat_comp,
        alpha=cfg.alpha,
        gamma_w=cfg.gamma_w,
    )

    feasible, cost = model.solveProblem()
    outputs = model.getOutputs() if feasible else None
    return feasible, cost, outputs


@pytest.mark.parametrize("nmax", [1, 2, None])
def test_nmax_feasibility(scenario_and_precompute, nmax):
    """Each N_max value should produce a feasible solution."""
    cfg, scenario, precompute_result = scenario_and_precompute
    feasible, cost, _ = _solve_with_nmax(cfg, scenario, precompute_result, nmax)
    assert feasible, f"Model infeasible for N_max={nmax}"
    assert cost >= 0


@pytest.mark.parametrize("nmax", [1, 2])
def test_nmax_constraint_respected(scenario_and_precompute, nmax):
    """No UAV-slot should exceed the N_max limit."""
    cfg, scenario, precompute_result = scenario_and_precompute
    feasible, _, outputs = _solve_with_nmax(cfg, scenario, precompute_result, nmax)
    if not feasible:
        pytest.skip(f"Model infeasible for N_max={nmax}")

    for t in scenario.time_slots:
        for j in scenario.uavs.keys():
            offload_count = len(outputs[t]["offload"][j])
            assert offload_count <= nmax, (
                f"UAV {j}, slot {t}: {offload_count} tasks assigned, exceeds N_max={nmax}"
            )
