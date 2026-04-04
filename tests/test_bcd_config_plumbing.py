from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

from edge_uav.data import ComputeTask, EdgeUavScenario, UAV
from edge_uav.model.bcd_loop import run_bcd_loop
from edge_uav.model.precompute import Level2Snapshot, PrecomputeParams
from edge_uav.model.trajectory_opt import TrajectoryOptParams, TrajectoryResult
from heuristics.hsIndividualEdgeUav import hsIndividualEdgeUav


def _make_scenario() -> EdgeUavScenario:
    tasks = {
        0: ComputeTask(
            index=0,
            pos=(10.0, 10.0),
            D_l=1e6,
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
            pos_final=(0.0, 0.0),
            E_max=1e6,
            f_max=5e9,
        )
    }
    return EdgeUavScenario(
        tasks=tasks,
        uavs=uavs,
        time_slots=[0, 1, 2],
        seed=42,
        meta={"x_max": 100.0, "y_max": 100.0, "delta": 1.0},
    )


def _make_snapshot(scenario: EdgeUavScenario) -> Level2Snapshot:
    return Level2Snapshot(
        q={j: {t: scenario.uavs[j].pos for t in scenario.time_slots} for j in scenario.uavs},
        f_edge={
            j: {
                i: {t: 1e9 for t in scenario.time_slots}
                for i in scenario.tasks
            }
            for j in scenario.uavs
        },
        source="test_init",
    )


def _make_params() -> PrecomputeParams:
    return PrecomputeParams(
        H=10.0,
        B_up=1e6,
        B_down=1e6,
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


def _make_traj_params() -> TrajectoryOptParams:
    return TrajectoryOptParams(
        eta_1=10.0,
        eta_2=5.0,
        eta_3=1e4,
        eta_4=0.1,
        v_tip=120.0,
        v_max=15.0,
        d_safe=5.0,
    )


def test_create_trajectory_opt_params_prefers_edge_uav_bcd_values():
    ind = hsIndividualEdgeUav.__new__(hsIndividualEdgeUav)
    ind.config = SimpleNamespace(
        eta_1=79.86,
        eta_2=88.63,
        eta_3=0.0151,
        eta_4=0.0048,
        v_tip=120.0,
        v_traj_max=12.5,
        v_U_max=30.0,
        d_safe_traj=7.5,
    )

    traj_params = ind._create_trajectory_opt_params()

    assert traj_params.v_max == 12.5
    assert traj_params.d_safe == 7.5


def test_run_bcd_loop_passes_configured_sca_controls():
    scenario = _make_scenario()
    params = _make_params()
    traj_params = _make_traj_params()
    initial_snapshot = _make_snapshot(scenario)
    config = SimpleNamespace(
        alpha=1.0,
        gamma_w=1.0,
        max_sca_iter=7,
        eps_sca=5e-4,
        safe_slack_penalty=321.0,
    )

    precompute_result = SimpleNamespace(
        D_hat_local={0: {0: 0.1, 1: 0.1, 2: 0.1}},
        D_hat_offload={0: {0: {0: 0.1, 1: 0.1, 2: 0.1}}},
        E_hat_comp={0: {0: {0: 0.1, 1: 0.1, 2: 0.1}}},
        diagnostics={},
    )
    ra_result = SimpleNamespace(
        f_edge={0: {0: {0: 1e9, 1: 1e9, 2: 1e9}}},
        diagnostics={"binding_slots": 0},
    )
    offloading_outputs = {
        0: {"local": [0], "offload": {0: []}},
        1: {"local": [0], "offload": {0: []}},
        2: {"local": [0], "offload": {0: []}},
    }
    traj_result = TrajectoryResult(
        q=initial_snapshot.q,
        objective_value=1.0,
        total_comm_delay=0.0,
        total_prop_energy=1.0,
        per_uav_energy={0: 1.0},
        sca_iterations=1,
        converged=True,
        solver_status="optimal",
        max_safe_slack=0.0,
        diagnostics={},
    )

    with patch("edge_uav.model.bcd_loop.precompute_offloading_inputs", return_value=precompute_result), \
         patch("edge_uav.model.bcd_loop.validate_offloading_outputs", return_value=offloading_outputs), \
         patch("edge_uav.model.bcd_loop.solve_resource_allocation", return_value=ra_result), \
         patch("edge_uav.model.bcd_loop.validate_resource_allocation_feasibility", return_value=True), \
         patch("edge_uav.model.bcd_loop.solve_trajectory_sca", return_value=traj_result) as solve_mock, \
         patch("edge_uav.model.bcd_loop.check_trajectory_monotonicity", return_value=(initial_snapshot.q, 1.0)), \
         patch("edge_uav.model.bcd_loop.adapt_f_edge_for_snapshot", return_value=initial_snapshot.f_edge):
        offloading_model = patch("edge_uav.model.bcd_loop.OffloadingModel").start()
        try:
            offloading_model.return_value.solveProblem.return_value = (True, 1.0)
            offloading_model.return_value.getOutputs.return_value = offloading_outputs
            offloading_model.return_value.gap = 0.0

            run_bcd_loop(
                scenario=scenario,
                config=config,
                params=params,
                traj_params=traj_params,
                dynamic_obj_func=None,
                initial_snapshot=initial_snapshot,
                max_bcd_iter=1,
            )
        finally:
            patch.stopall()

    kwargs = solve_mock.call_args.kwargs
    assert kwargs["max_sca_iter"] == 7
    assert kwargs["eps_sca"] == 5e-4
    assert kwargs["safe_slack_penalty"] == 321.0
