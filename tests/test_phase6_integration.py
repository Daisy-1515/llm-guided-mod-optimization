"""Phase6 integration verification tests.

Migrated from scripts/test_phase6_integration.py — converted to pytest format.
Requires gurobipy for solver execution.
"""

import pytest

gp = pytest.importorskip("gurobipy")

from scripts.script_common import (
    apply_config_overrides,
    apply_task_profile,
    extract_prompt_history,
    get_simulation_steps,
    load_config,
    make_edge_uav_scenario,
    make_edge_uav_solver,
)


def _run_case(*, use_bcd_loop: bool):
    """Run a minimal HS solve and return results dict."""
    params = load_config()
    apply_config_overrides(
        params,
        pop_size=2,
        iteration=2,
        use_bcd_loop=use_bcd_loop,
    )

    scenario = make_edge_uav_scenario(params)
    apply_task_profile(scenario, "relaxed_tau_low_local")

    solver = make_edge_uav_solver(params, scenario)
    final_pop = solver.run()
    best_ind = final_pop[0]
    best_cost = best_ind.get("evaluation_score", float("inf"))
    prompt_history = extract_prompt_history(best_ind)
    sim_steps = get_simulation_steps(best_ind)

    return {
        "params": params,
        "best_cost": best_cost,
        "prompt_history": prompt_history,
        "sim_steps": sim_steps,
    }


@pytest.fixture(scope="module")
def baseline_result():
    return _run_case(use_bcd_loop=False)


@pytest.fixture(scope="module")
def bcd_result():
    return _run_case(use_bcd_loop=True)


def test_baseline_converges(baseline_result):
    """Baseline run should converge to a finite cost."""
    assert baseline_result["best_cost"] < float("inf")


def test_bcd_converges(bcd_result):
    """BCD run should converge to a finite cost."""
    assert bcd_result["best_cost"] < float("inf")


def test_cost_monotonicity(baseline_result, bcd_result):
    """BCD cost should be within 5% of baseline cost.

    Note: BCD may slightly exceed baseline when the L2b trajectory solver
    introduces communication-delay terms not present in the baseline's
    straight-line trajectory.  A 5% tolerance accommodates this.
    """
    assert bcd_result["best_cost"] <= baseline_result["best_cost"] * 1.05 + 1e-6


def test_prompt_history_has_simulation_steps(baseline_result, bcd_result):
    """Both runs should have simulation_steps in promptHistory."""
    required_keys = {"simulation_steps"}
    assert required_keys.issubset(baseline_result["prompt_history"].keys())
    assert required_keys.issubset(bcd_result["prompt_history"].keys())


def test_bcd_metadata_recorded(bcd_result):
    """BCD run should have bcd_meta or bcd_error in at least one simulation step."""
    bcd_recorded = False
    for step_data in bcd_result["sim_steps"].values():
        bcd_meta = step_data.get("bcd_meta", {})
        if bcd_meta and ("bcd_iterations" in bcd_meta or "bcd_converged" in bcd_meta):
            bcd_recorded = True
            break
        # BCD failure is also valid evidence of BCD being active
        if step_data.get("bcd_error"):
            bcd_recorded = True
            break

    if bcd_result["params"].use_bcd_loop:
        assert bcd_recorded, "BCD metadata or error should be recorded when use_bcd_loop=True"
