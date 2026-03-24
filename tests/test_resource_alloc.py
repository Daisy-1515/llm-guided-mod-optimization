"""Tests for edge_uav.model.resource_alloc module."""

import math

import pytest

from edge_uav.data import ComputeTask, EdgeUavScenario, UAV
from edge_uav.model.precompute import PrecomputeParams
from edge_uav.model.resource_alloc import solve_resource_allocation


# =====================================================================
# Fixtures & helpers
# =====================================================================

@pytest.fixture
def params():
    """Standard physical parameters for resource allocation tests."""
    return PrecomputeParams(
        H=100.0,
        B_up=1e6,
        B_down=1e6,
        P_i=0.1,
        P_j=1.0,
        N_0=1e-11,
        rho_0=1.0,
        gamma_j=1e-28,
        eps_freq=1e-12,
    )


def _make_scenario(n_tasks=2, n_uavs=1, n_slots=2, **kwargs):
    """Minimal scenario factory."""
    time_slots = list(range(n_slots))
    active_all = {t: True for t in time_slots}

    tasks = {}
    for i in range(n_tasks):
        tasks[i] = ComputeTask(
            index=i,
            pos=(100.0 + 10.0 * i, 100.0),
            D_l=1000.0,
            D_r=500.0,
            F=kwargs.get(f"F_{i}", 1e9),
            tau=kwargs.get(f"tau_{i}", 0.5),
            active=dict(active_all),
            f_local=kwargs.get(f"f_local_{i}", 1e9),
        )

    uavs = {}
    for j in range(n_uavs):
        uavs[j] = UAV(
            index=j,
            pos=(500.0, 500.0),
            pos_final=(600.0, 600.0),
            E_max=kwargs.get(f"E_max_{j}", 3600.0),
            f_max=kwargs.get(f"f_max_{j}", 1e9),
        )

    return EdgeUavScenario(
        tasks=tasks, uavs=uavs, time_slots=time_slots,
        seed=42, meta={"T": n_slots},
    )


def _all_local(scenario):
    """Build all-local offloading decisions."""
    return {
        t: {"local": list(scenario.tasks.keys()), "offload": {}}
        for t in scenario.time_slots
    }


# =====================================================================
# T1: all-local
# =====================================================================

class TestLocalOnly:
    """All tasks executed locally — edge allocation should be empty."""

    def test_all_local_no_offload(self, params):
        """T1: f_edge empty, f_local = task.f_local, obj = 0."""
        scenario = _make_scenario(n_tasks=2, n_slots=2)
        result = solve_resource_allocation(
            scenario, _all_local(scenario), params,
            alpha=1.0, gamma_w=1e-9,
        )

        # f_edge: no time slot entries for any task (all empty dicts)
        for j in scenario.uavs:
            assert len(result.f_edge.get(j, {})) == len(scenario.tasks)
            for i in scenario.tasks:
                assert len(result.f_edge[j][i]) == 0

        # f_local: equals task.f_local
        for i, task in scenario.tasks.items():
            for t in scenario.time_slots:
                assert result.f_local[i][t] == task.f_local

        assert result.objective_value == 0.0


# =====================================================================
# T2: unconstrained KKT
# =====================================================================

class TestEdgeKKT:
    """Unconstrained edge-side KKT closed-form solution."""

    def test_unconstrained_kkt_exact(self, params):
        """T2: single task with large f_max matches (a/(2b))^(1/3)."""
        scenario = _make_scenario(
            n_tasks=1, n_uavs=1, n_slots=1,
            f_max_0=1e15,  # effectively unbounded
        )
        offloading = {0: {"local": [], "offload": {0: [0]}}}

        alpha, gamma_w = 1.0, 1e-9
        task = scenario.tasks[0]
        uav = scenario.uavs[0]

        result = solve_resource_allocation(
            scenario, offloading, params, alpha=alpha, gamma_w=gamma_w,
        )

        expected = (alpha * uav.E_max
                    / (2.0 * gamma_w * params.gamma_j * task.tau)) ** (1.0 / 3.0)
        actual = result.f_edge[0][0][0]
        assert actual == pytest.approx(expected, rel=1e-6)
        assert result.diagnostics["binding_slots"] == 0


# =====================================================================
# T3, T4: capacity binding
# =====================================================================

class TestCapacityBinding:
    """Scenarios where Σf > f_max triggers dual bisection."""

    def test_capacity_binds(self, params):
        """T3: 3 tasks sharing tight f_max — sum of frequencies equals f_max."""
        scenario = _make_scenario(
            n_tasks=3, n_uavs=1, n_slots=1,
            f_max_0=1e8,  # tight capacity
        )
        offloading = {0: {"local": [], "offload": {0: [0, 1, 2]}}}

        result = solve_resource_allocation(
            scenario, offloading, params, alpha=1.0, gamma_w=1e-9,
        )

        # All 3 tasks at time slot 0 should sum to f_max (capacity binding)
        total_f = sum(result.f_edge[0][i][0] for i in [0, 1, 2])
        assert total_f == pytest.approx(scenario.uavs[0].f_max, rel=1e-5)
        assert result.diagnostics["binding_slots"] >= 1

    def test_single_task_upper_bound(self, params):
        """T4: single task with very small f_max — frequency capped at f_max."""
        scenario = _make_scenario(n_tasks=1, n_uavs=1, n_slots=1, f_max_0=1e7)
        offloading = {0: {"local": [], "offload": {0: [0]}}}

        result = solve_resource_allocation(
            scenario, offloading, params, alpha=1.0, gamma_w=1e-9,
        )

        assert result.f_edge[0][0][0] == pytest.approx(1e7, rel=1e-12)


# =====================================================================
# T5, T6: objective value
# =====================================================================

class TestObjective:
    """Objective value computation checks."""

    def test_objective_hand_computed(self, params):
        """T5: hand-computed objective for single-task scenario."""
        scenario = _make_scenario(
            n_tasks=1, n_uavs=1, n_slots=1,
            F_0=1e8, f_max_0=1e15,
        )
        offloading = {0: {"local": [], "offload": {0: [0]}}}

        alpha, gamma_w = 1.0, 1e-10
        task = scenario.tasks[0]
        uav = scenario.uavs[0]

        result = solve_resource_allocation(
            scenario, offloading, params, alpha=alpha, gamma_w=gamma_w,
        )

        f = result.f_edge[0][0][0]
        expected_obj = (
            alpha * task.F / (f * task.tau)
            + gamma_w * params.gamma_j * f ** 2 * task.F / uav.E_max
        )
        assert result.objective_value == pytest.approx(expected_obj, rel=1e-6)

        # Verify total_comp_energy: γ_j · f² · F (Eq. 3-24)
        expected_energy = params.gamma_j * f ** 2 * task.F
        assert result.total_comp_energy[0] == pytest.approx(expected_energy, rel=1e-6)

    def test_empty_scenario(self, params):
        """T6: no offloaded tasks — objective is zero."""
        scenario = _make_scenario(n_tasks=1, n_uavs=1, n_slots=1)
        result = solve_resource_allocation(
            scenario, _all_local(scenario), params,
            alpha=1.0, gamma_w=1e-9,
        )
        assert result.objective_value == 0.0


# =====================================================================
# T7: heterogeneous tau
# =====================================================================

class TestHeterogeneousTau:
    """Heterogeneous deadlines — dual bisection ≠ proportional scaling."""

    def test_heterogeneous_tau(self, params):
        """T7: different tau values produce different allocation vs naive scaling."""
        scenario = _make_scenario(
            n_tasks=2, n_uavs=1, n_slots=1,
            tau_0=0.1, tau_1=0.5,
            f_max_0=1e8,
        )
        offloading = {0: {"local": [], "offload": {0: [0, 1]}}}

        alpha, gamma_w = 1.0, 1e-9
        uav = scenario.uavs[0]

        result = solve_resource_allocation(
            scenario, offloading, params, alpha=alpha, gamma_w=gamma_w,
        )

        f0_dual = result.f_edge[0][0][0]  # task 0, time slot 0
        f1_dual = result.f_edge[0][1][0]  # task 1, time slot 0

        # Naive proportional scaling baseline
        c0 = (alpha * uav.E_max / (2.0 * gamma_w * params.gamma_j * 0.1)) ** (1.0 / 3.0)
        c1 = (alpha * uav.E_max / (2.0 * gamma_w * params.gamma_j * 0.5)) ** (1.0 / 3.0)
        f0_scale = uav.f_max * c0 / (c0 + c1)

        # Dual solution differs from proportional scaling under heterogeneous tau
        assert abs(f0_dual - f0_scale) > 1e-6 * max(f0_dual, f0_scale)


# =====================================================================
# T8: KKT first-order condition residual
# =====================================================================

class TestKKTVerification:
    """Verify that returned frequencies satisfy KKT conditions."""

    def test_kkt_first_order_condition(self, params):
        """T8: KKT residual < 1e-8 for binding constraint scenario."""
        scenario = _make_scenario(
            n_tasks=2, n_uavs=1, n_slots=1,
            F_0=8e8, F_1=1.2e9,
            tau_0=0.25, tau_1=0.75,
            f_max_0=1e8,
        )
        offloading = {0: {"local": [], "offload": {0: [0, 1]}}}

        alpha, gamma_w = 1.0, 1e-9
        uav = scenario.uavs[0]

        result = solve_resource_allocation(
            scenario, offloading, params, alpha=alpha, gamma_w=gamma_w,
        )

        f0 = result.f_edge[0][0][0]  # task 0, time slot 0
        f1 = result.f_edge[0][1][0]  # task 1, time slot 0
        task0, task1 = scenario.tasks[0], scenario.tasks[1]

        # KKT: ∂L/∂f = -a/f² + 2b·f + λ = 0  ⟹  λ = a/f² - 2b·f
        a0 = alpha * task0.F / task0.tau
        a1 = alpha * task1.F / task1.tau
        b0 = gamma_w * params.gamma_j * task0.F / uav.E_max
        b1 = gamma_w * params.gamma_j * task1.F / uav.E_max

        lam0 = a0 / (f0 ** 2) - 2.0 * b0 * f0
        lam1 = a1 / (f1 ** 2) - 2.0 * b1 * f1

        # Both tasks should yield the same dual variable λ
        assert math.isfinite(lam0)
        assert math.isfinite(lam1)
        assert abs(lam0 - lam1) < 1e-8
