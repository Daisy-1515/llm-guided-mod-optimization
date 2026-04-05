"""Unit tests for greedy trajectory initialization (_init_trajectory_greedy)."""

import math
import pytest
from edge_uav.data import ComputeTask, UAV, EdgeUavScenario
from edge_uav.model.precompute import (
    _dist_sq,
    _interpolate_waypoints,
    _init_trajectory_greedy,
    make_initial_level2_snapshot,
)


# ============================================================================
# Helpers
# ============================================================================

def _make_scenario(n_uavs: int, n_tasks: int, T: int = 15) -> EdgeUavScenario:
    """Build a scenario with n_uavs UAVs and n_tasks tasks on a 1000x1000 map."""
    tasks = {}
    # Spread tasks across the map
    for i in range(n_tasks):
        x = 100.0 + 800.0 * (i % 5) / max(4, 1)
        y = 100.0 + 800.0 * (i // 5) / max(n_tasks // 5, 1)
        tasks[i] = ComputeTask(
            index=i,
            pos=(x, y),
            D_l=1e7,
            D_r=1e5,
            F=1e8,
            tau=2.0,
            active={t: True for t in range(T)},
            f_local=1e9,
        )

    uavs = {}
    for j in range(n_uavs):
        uavs[j] = UAV(
            index=j,
            pos=(0.0, 0.0),
            pos_final=(1000.0, 1000.0),
            E_max=1e6,
            f_max=1e10,
            N_max=4,
        )

    return EdgeUavScenario(
        tasks=tasks,
        uavs=uavs,
        time_slots=list(range(T)),
        seed=42,
        meta={
            "T": T,
            "delta": 1.0,
            "x_max": 1000.0,
            "y_max": 1000.0,
            "H": 100.0,
            "B_up": 2e7,
            "B_down": 2e7,
            "P_i": 0.5,
            "P_j": 1.0,
            "rho_0": 1e-5,
            "N_0": 1e-10,
            "depot_pos": (0.0, 0.0),
        },
    )


# ============================================================================
# T1: 3 UAV 10 tasks — trajectories are distinct
# ============================================================================

def test_t1_three_uavs_distinct_trajectories():
    """3 UAV, 10 tasks: greedy init produces distinct trajectories."""
    scenario = _make_scenario(n_uavs=3, n_tasks=10, T=15)
    q = _init_trajectory_greedy(scenario)

    assert len(q) == 3

    # Collect all positions as tuples for comparison
    trajs = []
    for j in sorted(q.keys()):
        positions = tuple(q[j][t] for t in scenario.time_slots)
        trajs.append(positions)

    # All pairs must be different
    for a in range(len(trajs)):
        for b in range(a + 1, len(trajs)):
            assert trajs[a] != trajs[b], (
                f"UAV {a} and UAV {b} have identical trajectories"
            )


# ============================================================================
# T2: Boundary conditions
# ============================================================================

def test_t2_boundary_conditions():
    """q[j][0] = pos and q[j][T-1] = pos_final for all UAVs."""
    scenario = _make_scenario(n_uavs=3, n_tasks=6, T=15)
    q = _init_trajectory_greedy(scenario)

    for j, uav in scenario.uavs.items():
        start = q[j][scenario.time_slots[0]]
        end = q[j][scenario.time_slots[-1]]
        assert start == pytest.approx(uav.pos, abs=1e-9), (
            f"UAV {j} start {start} != {uav.pos}"
        )
        assert end == pytest.approx(uav.pos_final, abs=1e-9), (
            f"UAV {j} end {end} != {uav.pos_final}"
        )


# ============================================================================
# T3: 0 tasks — degenerates to straight line
# ============================================================================

def test_t3_zero_tasks_straight_line():
    """0 tasks: greedy falls back to straight line depot->depot_end."""
    scenario = _make_scenario(n_uavs=2, n_tasks=0, T=10)
    q = _init_trajectory_greedy(scenario)

    for j, uav in scenario.uavs.items():
        x0, y0 = uav.pos
        xf, yf = uav.pos_final
        T = len(scenario.time_slots)
        for t_idx, t in enumerate(scenario.time_slots):
            ratio = t_idx / (T - 1)
            expected = (x0 + (xf - x0) * ratio, y0 + (yf - y0) * ratio)
            actual = q[j][t]
            assert actual == pytest.approx(expected, abs=1e-9), (
                f"UAV {j}, t={t}: expected {expected}, got {actual}"
            )


# ============================================================================
# T4: UAV count > task count — doesn't crash
# ============================================================================

def test_t4_more_uavs_than_tasks():
    """5 UAVs, 2 tasks: no crash, all UAVs get trajectories."""
    scenario = _make_scenario(n_uavs=5, n_tasks=2, T=10)
    q = _init_trajectory_greedy(scenario)

    assert len(q) == 5
    for j in scenario.uavs:
        assert len(q[j]) == len(scenario.time_slots)


# ============================================================================
# T5: Time slot allocation sums to T-1
# ============================================================================

def test_t5_interpolate_slot_sum():
    """_interpolate_waypoints produces exactly T positions."""
    waypoints = [(0.0, 0.0), (100.0, 0.0), (100.0, 200.0), (500.0, 500.0)]
    time_slots = list(range(20))
    result = _interpolate_waypoints(waypoints, time_slots)

    assert len(result) == len(time_slots)
    assert set(result.keys()) == set(time_slots)
    assert result[time_slots[0]] == pytest.approx(waypoints[0], abs=1e-9)
    assert result[time_slots[-1]] == pytest.approx(waypoints[-1], abs=1e-9)


# ============================================================================
# T6: All positions within map bounds
# ============================================================================

def test_t6_positions_within_bounds():
    """All greedy positions lie within [0, x_max] x [0, y_max]."""
    scenario = _make_scenario(n_uavs=3, n_tasks=10, T=15)
    q = _init_trajectory_greedy(scenario)

    x_max = scenario.meta["x_max"]
    y_max = scenario.meta["y_max"]

    for j in scenario.uavs:
        for t in scenario.time_slots:
            x, y = q[j][t]
            assert 0.0 <= x <= x_max, f"UAV {j}, t={t}: x={x} out of bounds"
            assert 0.0 <= y <= y_max, f"UAV {j}, t={t}: y={y} out of bounds"


# ============================================================================
# T7: Round-robin even split (3 UAVs, 6 tasks -> 2 each)
# ============================================================================

def test_t7_round_robin_even_split():
    """3 UAVs, 6 tasks: greedy init gives each UAV a distinct trajectory with waypoints."""
    scenario = _make_scenario(n_uavs=3, n_tasks=6, T=15)
    q = _init_trajectory_greedy(scenario)

    # Each UAV should have a full trajectory
    for j in scenario.uavs:
        assert len(q[j]) == len(scenario.time_slots)

    # With 6 tasks and 3 UAVs, trajectories must be distinct
    trajs = [tuple(q[j][t] for t in scenario.time_slots) for j in sorted(q.keys())]
    for a in range(len(trajs)):
        for b in range(a + 1, len(trajs)):
            assert trajs[a] != trajs[b], (
                f"UAV {a} and UAV {b} have identical trajectories"
            )


# ============================================================================
# T8: make_initial_level2_snapshot(policy="greedy") passes validate()
# ============================================================================

def test_t8_snapshot_greedy_passes_validate():
    """Full snapshot with greedy policy passes Level2Snapshot.validate()."""
    scenario = _make_scenario(n_uavs=3, n_tasks=10, T=15)
    snap = make_initial_level2_snapshot(scenario, policy="greedy")

    # validate() raises ValueError on failure — if we get here, it passed
    snap.validate(scenario)

    # Also check basic structural properties
    assert len(snap.q) == 3
    assert snap.source == "init"
    for j in scenario.uavs:
        assert len(snap.q[j]) == len(scenario.time_slots)
        for i in scenario.tasks:
            assert len(snap.f_edge[j][i]) == len(scenario.time_slots)


# ============================================================================
# T9: _interpolate_waypoints start point edge case (short first segment)
# ============================================================================

def test_t9_interpolate_start_point_preserved():
    """Short first segment must not lose the start point."""
    # First segment is 1m, second is 100m — floor gives 0 slots to first seg
    waypoints = [(0.0, 0.0), (1.0, 0.0), (101.0, 0.0)]
    time_slots = [0, 1, 2]
    result = _interpolate_waypoints(waypoints, time_slots)

    assert result[0] == pytest.approx((0.0, 0.0), abs=1e-9), (
        f"Start point lost: result[0] = {result[0]}"
    )
    assert result[2] == pytest.approx((101.0, 0.0), abs=1e-9), (
        f"End point wrong: result[2] = {result[2]}"
    )
    assert len(result) == 3


# ============================================================================
# T10: Default policy is now "greedy"
# ============================================================================

def test_t10_default_policy_is_greedy():
    """make_initial_level2_snapshot() without explicit policy uses greedy."""
    scenario = _make_scenario(n_uavs=3, n_tasks=6, T=15)

    # Default call (no policy arg)
    snap_default = make_initial_level2_snapshot(scenario)
    # Explicit greedy
    snap_greedy = make_initial_level2_snapshot(scenario, policy="greedy")

    # They should produce identical trajectories
    for j in scenario.uavs:
        for t in scenario.time_slots:
            assert snap_default.q[j][t] == pytest.approx(snap_greedy.q[j][t], abs=1e-12)
