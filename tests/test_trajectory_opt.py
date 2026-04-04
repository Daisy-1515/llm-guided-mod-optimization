"""Unit tests for Block D trajectory optimization (trajectory_opt.py)."""

import math
import pytest
import numpy as np
from edge_uav.data import ComputeTask, UAV, EdgeUavScenario
from edge_uav.model.precompute import PrecomputeParams
from edge_uav.model.trajectory_opt import (
    TrajectoryOptParams, TrajectoryResult, solve_trajectory_sca
)


# ============================================================================
# Fixtures
# ============================================================================

@pytest.fixture
def base_scenario_1uav():
    """Single UAV, single task, 3 time slots."""
    tasks = {
        0: ComputeTask(
            index=0,
            pos=(50.0, 50.0),
            D_l=1e7,
            D_r=1e5,
            F=1e8,
            tau=1.0,
            active={0: True, 1: True, 2: True},
            f_local=1e9,
        )
    }
    uavs = {
        0: UAV(
            index=0,
            pos=(0.0, 0.0),
            pos_final=(10.0, 0.0),
            E_max=1e6,
            f_max=5e9,
            N_max=4,
        )
    }
    scenario = EdgeUavScenario(
        tasks=tasks,
        uavs=uavs,
        time_slots=[0, 1, 2],
        seed=42,
        meta={
            'T': 3,
            'delta': 0.5,
            'x_max': 100.0,
            'y_max': 100.0,
            'H': 10.0,
            'B_up': 2e7,
            'B_down': 2e7,
            'P_i':   0.5,
            'P_j':   1.0,
            'rho_0': 1e-5,
            'N_0':   1e-10,
            'depot_pos': (50.0, 50.0),
        },
    )
    return scenario


@pytest.fixture
def base_scenario_2uav():
    """Two UAVs, shared task, 3 time slots."""
    tasks = {
        0: ComputeTask(
            index=0,
            pos=(50.0, 50.0),
            D_l=1e7,
            D_r=1e5,
            F=1e8,
            tau=1.0,
            active={0: True, 1: True, 2: True},
            f_local=1e9,
        )
    }
    uavs = {
        0: UAV(
            index=0,
            pos=(0.0, 0.0),
            pos_final=(10.0, 0.0),
            E_max=1e6,
            f_max=5e9,
            N_max=4,
        ),
        1: UAV(
            index=1,
            pos=(0.0, 5.0),
            pos_final=(10.0, 5.0),
            E_max=1e6,
            f_max=5e9,
            N_max=4,
        ),
    }
    scenario = EdgeUavScenario(
        tasks=tasks,
        uavs=uavs,
        time_slots=[0, 1, 2],
        seed=42,
        meta={
            'T': 3,
            'delta': 0.5,
            'x_max': 100.0,
            'y_max': 100.0,
            'H': 10.0,
            'B_up': 2e7,
            'B_down': 2e7,
            'P_i':   0.5,
            'P_j':   1.0,
            'rho_0': 1e-5,
            'N_0':   1e-10,
            'depot_pos': (50.0, 50.0),
        },
    )
    return scenario


@pytest.fixture
def params():
    """PrecomputeParams fixture."""
    return PrecomputeParams(
        H=10.0,
        B_up=2e7,
        B_down=2e7,
        P_i=0.5,
        P_j=1.0,
        N_0=1e-10,
        rho_0=1e-5,
        gamma_j=1e-28,
        eps_dist_sq=1e-12,
        eps_rate=1e-12,
        eps_freq=1e-12,
        tau_tol=1e-9,
        big_m_delay=1e6,
    )


@pytest.fixture
def traj_params():
    """TrajectoryOptParams fixture."""
    return TrajectoryOptParams(
        eta_1=10.0,
        eta_2=5.0,
        eta_3=1e4,
        eta_4=0.1,
        v_tip=120.0,
        v_max=15.0,
        d_safe=5.0,
    )


@pytest.fixture
def linear_init_trajectory_1uav(base_scenario_1uav):
    """Linear interpolation from start to end for 1 UAV."""
    scenario = base_scenario_1uav
    j = 0
    T = len(scenario.time_slots)
    pos_start = scenario.uavs[j].pos
    pos_end = scenario.uavs[j].pos_final

    q_init = {
        j: {
            t: (
                pos_start[0] + (pos_end[0] - pos_start[0]) * t / (T - 1),
                pos_start[1] + (pos_end[1] - pos_start[1]) * t / (T - 1),
            )
            for t in range(T)
        }
    }
    return q_init


@pytest.fixture
def linear_init_trajectory_2uav(base_scenario_2uav):
    """Linear interpolation for 2 UAVs."""
    scenario = base_scenario_2uav
    T = len(scenario.time_slots)
    q_init = {}
    for j in scenario.uavs:
        pos_start = scenario.uavs[j].pos
        pos_end = scenario.uavs[j].pos_final
        q_init[j] = {
            t: (
                pos_start[0] + (pos_end[0] - pos_start[0]) * t / (T - 1),
                pos_start[1] + (pos_end[1] - pos_start[1]) * t / (T - 1),
            )
            for t in range(T)
        }
    return q_init


# ============================================================================
# Core Tests (T1-T6)
# ============================================================================

def test_stationary_endpoint_returns_hover_path(
    base_scenario_1uav, params, traj_params, linear_init_trajectory_1uav
):
    """T1: Stationary endpoint (pos == pos_final) returns minimal energy path."""
    scenario = base_scenario_1uav

    # Modify to have stationary UAV
    j = 0
    scenario.uavs[j].pos_final = (0.0, 0.0)  # Same as start

    # Reset init trajectory
    q_init = {j: {t: (0.0, 0.0) for t in range(len(scenario.time_slots))}}

    # No offloading
    f_fixed = {}
    offloading_decisions = {}

    result = solve_trajectory_sca(
        scenario, offloading_decisions, f_fixed, q_init, params, traj_params
    )

    # Trajectory should remain at (0, 0)
    for t in range(len(scenario.time_slots)):
        assert np.allclose(result.q[j][t], (0.0, 0.0), atol=1e-4)

    # Objective should be positive (hovering energy)
    assert result.objective_value > 0


def test_single_uav_path_respects_boundary_and_speed(
    base_scenario_1uav, params, traj_params, linear_init_trajectory_1uav
):
    """T2: Single UAV path respects boundary and speed constraints."""
    scenario = base_scenario_1uav
    q_init = linear_init_trajectory_1uav
    f_fixed = {}
    offloading_decisions = {}

    result = solve_trajectory_sca(
        scenario, offloading_decisions, f_fixed, q_init, params, traj_params
    )

    j = 0
    x_max = float(scenario.meta.get('x_max', 100.0))
    y_max = float(scenario.meta.get('y_max', 100.0))

    for t in range(len(scenario.time_slots)):
        x, y = result.q[j][t]
        # Boundary check
        assert 0 <= x <= x_max, f"x={x} outside [0, {x_max}]"
        assert 0 <= y <= y_max, f"y={y} outside [0, {y_max}]"

    # Speed check
    for t in range(len(scenario.time_slots) - 1):
        delta_q = np.array(result.q[j][t + 1]) - np.array(result.q[j][t])
        dist = np.linalg.norm(delta_q)
        delta = float(scenario.meta.get('delta', 0.5))
        max_allowed = traj_params.v_max * delta
        assert dist <= max_allowed + 1e-6, f"Speed violation at t={t}: {dist} > {max_allowed}"


def test_infeasible_endpoint_pair_raises(base_scenario_1uav, params, traj_params):
    """T3: Infeasible endpoint distance raises ValueError before solving."""
    scenario = base_scenario_1uav

    # Make endpoint unreachable
    j = 0
    scenario.uavs[j].pos_final = (1000.0, 1000.0)

    q_init = {j: {t: (0.0, 0.0) for t in range(len(scenario.time_slots))}}

    with pytest.raises(ValueError, match="endpoint distance"):
        solve_trajectory_sca(
            scenario, {}, {}, q_init, params, traj_params
        )


def test_comm_constraint_moves_uav_toward_offloaded_task(
    base_scenario_1uav, params, traj_params, linear_init_trajectory_1uav
):
    """T4: Communication constraint incentivizes proximity to task base."""
    scenario = base_scenario_1uav
    q_init = linear_init_trajectory_1uav
    j = 0
    i = 0

    # Offload task i to UAV j at slot t=1
    f_fixed = {
        j: {
            i: {
                1: 5e8,  # 500 MHz
            }
        }
    }
    offloading_decisions = {}

    result = solve_trajectory_sca(
        scenario, offloading_decisions, f_fixed, q_init, params, traj_params
    )

    # Check that trajectory exists
    assert result.objective_value > 0
    assert result.converged or result.sca_iterations == 5


def test_two_uav_safe_distance_interim_enforced(
    base_scenario_2uav, params, traj_params, linear_init_trajectory_2uav
):
    """T5: Safe distance enforced in interim slots, not at endpoints."""
    scenario = base_scenario_2uav
    q_init = linear_init_trajectory_2uav
    f_fixed = {}
    offloading_decisions = {}

    # Note: default linear init may violate safe distance at endpoints
    # But with enforce_safe_at_endpoints=False, should only check 0 < t < T-1

    result = solve_trajectory_sca(
        scenario, offloading_decisions, f_fixed, q_init, params, traj_params
    )

    # Check interim safe distance
    for t in range(1, len(scenario.time_slots) - 1):
        q_0 = np.array(result.q[0][t])
        q_1 = np.array(result.q[1][t])
        dist = np.linalg.norm(q_0 - q_1)
        # Allow small numeric error
        assert dist >= traj_params.d_safe - 1e-3, \
            f"Safe distance violated at t={t}: {dist} < {traj_params.d_safe}"


def test_sca_reports_convergence_metadata(
    base_scenario_1uav, params, traj_params, linear_init_trajectory_1uav
):
    """T6: SCA reports iterations, convergence status, and diagnostics."""
    scenario = base_scenario_1uav
    q_init = linear_init_trajectory_1uav

    result = solve_trajectory_sca(
        scenario, {}, {}, q_init, params, traj_params,
        max_sca_iter=5, eps_sca=1e-3
    )

    # Check metadata
    assert 1 <= result.sca_iterations <= 5
    assert isinstance(result.converged, bool)
    assert isinstance(result.solver_status, str)
    assert result.solver_status in ["optimal", "optimal_inaccurate"]

    # Check diagnostics
    assert len(result.diagnostics["true_objective_history"]) == result.sca_iterations
    assert len(result.diagnostics["sca_times"]) == result.sca_iterations


def test_project_scale_params_do_not_go_unbounded(base_scenario_1uav, params, linear_init_trajectory_1uav):
    """Project-scale trajectory params should remain bounded in the SOCP subproblem."""
    scenario = base_scenario_1uav
    q_init = linear_init_trajectory_1uav

    project_traj_params = TrajectoryOptParams(
        eta_1=79.86,
        eta_2=88.63,
        eta_3=0.0151,
        eta_4=0.0048,
        v_tip=120.0,
        v_max=15.0,
        d_safe=5.0,
    )

    result = solve_trajectory_sca(
        scenario,
        {},
        {},
        q_init,
        params,
        project_traj_params,
        max_sca_iter=5,
    )

    assert result.solver_status in {"optimal", "optimal_inaccurate"}
    assert math.isfinite(result.objective_value)
    assert all(t >= 0 for t in result.diagnostics["sca_times"])

    # Objective should be positive
    assert result.objective_value > 0


# ============================================================================
# Supplementary Tests (T7-T12)
# ============================================================================

def test_empty_offload_slot_returns_minimal_result(
    base_scenario_1uav, params, traj_params, linear_init_trajectory_1uav
):
    """T7': Empty offload slot (no communication constraint) returns hovering energy."""
    scenario = base_scenario_1uav
    q_init = linear_init_trajectory_1uav

    # No offloads
    f_fixed = {}

    result = solve_trajectory_sca(
        scenario, {}, f_fixed, q_init, params, traj_params
    )

    # Should complete and report objective
    assert result.objective_value > 0
    assert result.sca_iterations >= 1


def test_unsafe_initial_trajectory_warns_and_allows_slack(
    base_scenario_2uav, params, traj_params
):
    """T8: Unsafe initial trajectory (safe distance violation) allowed with slack."""
    scenario = base_scenario_2uav

    # Create init trajectory with UAVs close together at t=1
    q_init = {
        0: {0: (0.0, 0.0), 1: (1.0, 1.0), 2: (10.0, 0.0)},
        1: {0: (0.0, 5.0), 1: (1.5, 1.5), 2: (10.0, 5.0)},  # Close to UAV 0 at t=1
    }

    # Distance at t=1: sqrt((1.5-1.0)² + (1.5-1.0)²) = sqrt(0.5) ≈ 0.707 < d_safe=5.0

    # Solve with tight safe distance
    f_fixed = {}

    result = solve_trajectory_sca(
        scenario, {}, f_fixed, q_init, params, traj_params
    )

    # Should handle via slack penalty
    assert result.objective_value > 0
    # max_safe_slack may be > 0 due to initial violation
    assert result.max_safe_slack >= 0


def test_negative_communication_budget_raises(
    base_scenario_1uav, params, traj_params, linear_init_trajectory_1uav
):
    """T9: Negative communication budget (τ_comm ≤ 0) raises ValueError."""
    scenario = base_scenario_1uav
    q_init = linear_init_trajectory_1uav
    j, i, t = 0, 0, 1

    # Set f_edge very low so F_i/f_edge > τ_i
    f_fixed = {
        j: {
            i: {
                t: 1e5,  # Very low => F_i/f_edge > tau_i, so tau_comm < 0
            }
        }
    }

    with pytest.raises(ValueError, match="Infeasible communication budget"):
        solve_trajectory_sca(
            scenario, {}, f_fixed, q_init, params, traj_params
        )


def test_solver_fallback_on_failure(
    base_scenario_1uav, params, traj_params, linear_init_trajectory_1uav
):
    """T10: Solver fallback list is tried in order."""
    scenario = base_scenario_1uav
    q_init = linear_init_trajectory_1uav

    # Use custom fallback: even if first fails, others should work
    result = solve_trajectory_sca(
        scenario, {}, {}, q_init, params, traj_params,
        solver_fallback=("CLARABEL", "ECOS", "SCS")
    )

    # Should succeed using one of the solvers
    assert result.objective_value > 0
    assert result.solver_status in ["optimal", "optimal_inaccurate"]


def test_default_scenario_with_safe_distance_non_endpoint(
    base_scenario_2uav, params, traj_params, linear_init_trajectory_2uav
):
    """T11: Default 2-UAV scenario with safe distance checks (non-endpoint only)."""
    scenario = base_scenario_2uav
    q_init = linear_init_trajectory_2uav

    result = solve_trajectory_sca(
        scenario, {}, {}, q_init, params, traj_params,
        max_sca_iter=3, eps_sca=1e-2
    )

    # Should converge or reach max iter
    assert result.sca_iterations >= 1
    assert result.objective_value > 0

    # Per-UAV energy should be assigned
    assert len(result.per_uav_energy) == len(scenario.uavs)
    for j in scenario.uavs:
        assert result.per_uav_energy[j] > 0


def test_trajectory_result_fields_complete(
    base_scenario_1uav, params, traj_params, linear_init_trajectory_1uav
):
    """T12: TrajectoryResult contains all required fields with correct semantics."""
    scenario = base_scenario_1uav
    q_init = linear_init_trajectory_1uav

    result = solve_trajectory_sca(
        scenario, {}, {}, q_init, params, traj_params
    )

    # Check all fields exist and have correct types
    assert isinstance(result.q, dict)
    assert isinstance(result.objective_value, (int, float))
    assert isinstance(result.total_comm_delay, (int, float))
    assert isinstance(result.total_prop_energy, (int, float))
    assert isinstance(result.per_uav_energy, dict)
    assert isinstance(result.sca_iterations, int)
    assert isinstance(result.converged, bool)
    assert isinstance(result.solver_status, str)
    assert isinstance(result.max_safe_slack, (int, float))
    assert isinstance(result.diagnostics, dict)

    # Check diagnostics keys
    assert "true_objective_history" in result.diagnostics
    assert "total_comm_delay_history" in result.diagnostics
    assert "total_prop_energy_history" in result.diagnostics
    assert "sca_times" in result.diagnostics
    assert "solver_status_history" in result.diagnostics

    # No-offload case: comm_delay=0, so objective == lambda_w(=1) * prop_energy
    assert np.isclose(result.objective_value, result.total_prop_energy, rtol=1e-6)
    assert result.total_comm_delay == 0.0
    assert np.isclose(
        sum(result.per_uav_energy.values()), result.total_prop_energy, rtol=1e-6
    )


# ============================================================================
# New Tests (T13-T16)
# ============================================================================

def test_combined_objective_decomposes_with_offload(
    base_scenario_1uav, params, traj_params, linear_init_trajectory_1uav
):
    """T13: objective_value = alpha*total_comm_delay + lambda_w*total_prop_energy with offload."""
    scenario = base_scenario_1uav
    q_init = linear_init_trajectory_1uav
    j, i, t_off = 0, 0, 1

    f_fixed = {j: {i: {t_off: 5e8}}}
    offloading_decisions = {}  # fallback mode

    alpha = 2.0
    lambda_w = 0.5
    result = solve_trajectory_sca(
        scenario, offloading_decisions, f_fixed, q_init, params, traj_params,
        alpha=alpha, lambda_w=lambda_w,
    )

    # Decomposition check
    expected_obj = alpha * result.total_comm_delay + lambda_w * result.total_prop_energy
    assert np.isclose(result.objective_value, expected_obj, rtol=1e-6), (
        f"objective_value={result.objective_value} != "
        f"alpha*comm + lambda_w*prop = {expected_obj}"
    )

    # With offload, comm delay must be positive
    assert result.total_comm_delay > 0, "Expected positive comm delay with active offload"


def test_b_down_sensitivity(
    base_scenario_1uav, params, traj_params, linear_init_trajectory_1uav
):
    """T14: Reducing B_down increases total_comm_delay (downlink rate impact)."""
    import copy

    base_scenario = base_scenario_1uav
    q_init = linear_init_trajectory_1uav
    j, i, t_off = 0, 0, 1
    f_fixed = {j: {i: {t_off: 5e8}}}

    # Baseline: B_down = 2e7
    result_high = solve_trajectory_sca(
        base_scenario, {}, f_fixed, q_init, params, traj_params,
        max_sca_iter=3,
    )

    # Build scenario with lower B_down
    low_meta = dict(base_scenario.meta)
    low_meta['B_down'] = 1e6  # 10x smaller
    scenario_low = EdgeUavScenario(
        tasks=base_scenario.tasks,
        uavs=base_scenario.uavs,
        time_slots=base_scenario.time_slots,
        seed=base_scenario.seed,
        meta=low_meta,
    )
    result_low = solve_trajectory_sca(
        scenario_low, {}, f_fixed, q_init, params, traj_params,
        max_sca_iter=3,
    )

    assert result_low.total_comm_delay > result_high.total_comm_delay, (
        f"Lower B_down should yield higher comm delay: "
        f"low={result_low.total_comm_delay:.4f}, high={result_high.total_comm_delay:.4f}"
    )


def test_offloading_decisions_f_fixed_consistency_error(
    base_scenario_1uav, params, traj_params, linear_init_trajectory_1uav
):
    """T15: offloading_decisions/f_fixed inconsistency raises ValueError."""
    scenario = base_scenario_1uav
    q_init = linear_init_trajectory_1uav

    # offloading_decisions says no offload for any UAV at any slot
    offloading_decisions = {
        0: {"local": [0], "offload": {}},
        1: {"local": [0], "offload": {}},
        2: {"local": [0], "offload": {}},
    }
    # But f_fixed has a positive entry: residual allocation
    f_fixed = {0: {0: {1: 5e8}}}

    with pytest.raises(ValueError, match="residual"):
        solve_trajectory_sca(
            scenario, offloading_decisions, f_fixed, q_init, params, traj_params
        )


def test_endpoint_reachability_constraint_4e(
    base_scenario_1uav, params, traj_params, linear_init_trajectory_1uav
):
    """T16: After optimization, endpoint reachability constraint holds for all t."""
    scenario = base_scenario_1uav
    q_init = linear_init_trajectory_1uav

    result = solve_trajectory_sca(
        scenario, {}, {}, q_init, params, traj_params,
        max_sca_iter=5,
    )

    delta = float(scenario.meta.get('delta', 0.5))
    T = len(scenario.time_slots)

    for j in scenario.uavs:
        pos_final = np.array(scenario.uavs[j].pos_final, dtype=float)
        for t in range(T - 1):
            remaining = T - 1 - t
            max_dist = traj_params.v_max * remaining * delta
            q_jt = np.array(result.q[j][t], dtype=float)
            dist_sq = np.sum((q_jt - pos_final) ** 2)
            assert dist_sq <= max_dist ** 2 + 1e-3, (
                f"UAV {j} at t={t}: dist²={dist_sq:.4f} > max_dist²={max_dist**2:.4f}"
            )
