"""Debug script for trajectory optimization unbounded issue."""

import sys
import numpy as np
import cvxpy as cp

# Add project to path
sys.path.insert(0, "E:/aaa_dev/llm-guided-mod-optimization")

from config.config import configPara
from edge_uav.data import ComputeTask, EdgeUavScenario, UAV
from edge_uav.model.precompute import (
    PrecomputeParams,
    precompute_offloading_inputs,
    make_initial_level2_snapshot,
    Level2Snapshot,
)
from edge_uav.model.trajectory_opt import (
    TrajectoryOptParams,
    solve_trajectory_sca,
    _build_sca_subproblem,
    _extract_active_offloads,
)
from edge_uav.model.bcd_loop import run_bcd_loop
from edge_uav.model.offloading import OffloadingModel


def make_realistic_d1_scenario():
    """Create a scenario matching D1 experiment (3 UAVs, shared depot)."""
    config = configPara(None, None)

    # Generate tasks similar to D1
    np.random.seed(42)
    tasks = {}
    for i in range(20):  # numTasks = 20
        # Random positions within map
        pos = (
            np.random.uniform(50, 450),
            np.random.uniform(50, 450),
        )
        # Generate active window
        window_start = np.random.randint(24, 64)
        window_end = min(window_start + np.random.randint(5, 15), 80)
        active = {t: (window_start <= t < window_end) for t in range(80)}

        tasks[i] = ComputeTask(
            index=i,
            pos=pos,
            D_l=np.random.uniform(1e5, 3e5),
            D_r=np.random.uniform(2e4, 8e4),
            F=np.random.uniform(5e7, 2.5e8),
            tau=0.5,
            active=active,
            f_local=3e8,
        )

    # 3 UAVs sharing the same depot (matching setting.cfg)
    uavs = {
        0: UAV(
            index=0,
            pos=(500.0, 500.0),
            pos_final=(500.0, 500.0),
            E_max=9999.0,
            f_max=2e10,
        ),
        1: UAV(
            index=1,
            pos=(500.0, 500.0),
            pos_final=(500.0, 500.0),
            E_max=9999.0,
            f_max=2e10,
        ),
        2: UAV(
            index=2,
            pos=(500.0, 500.0),
            pos_final=(500.0, 500.0),
            E_max=9999.0,
            f_max=2e10,
        ),
    }

    meta = {
        "x_max": 500.0,
        "y_max": 500.0,
        "delta": 0.5,
        "H": 100.0,
        "B_up": 4e7,
        "B_down": 4e7,
        "P_i": 0.5,
        "P_j": 1.0,
        "rho_0": 1e-5,
        "N_0": 1e-10,
    }

    return EdgeUavScenario(
        tasks=tasks,
        uavs=uavs,
        time_slots=list(range(80)),
        seed=42,
        meta=meta,
    )


def debug_d1_scenario():
    """Debug D1 scenario with actual D1 parameters."""
    config = configPara(None, None)
    scenario = make_realistic_d1_scenario()

    params = PrecomputeParams.from_config(config)
    traj_params = TrajectoryOptParams(
        eta_1=float(config.eta_1),
        eta_2=float(config.eta_2),
        eta_3=float(config.eta_3),
        eta_4=float(config.eta_4),
        v_tip=float(config.v_tip),
        v_max=float(config.v_traj_max),
        d_safe=float(config.d_safe_traj),
    )

    print("=" * 70)
    print("D1 Scenario Debug")
    print("=" * 70)

    print(f"\nScenario:")
    print(f"  Tasks: {len(scenario.tasks)}")
    print(f"  UAVs: {len(scenario.uavs)}")
    print(f"  Time slots: {len(scenario.time_slots)}")
    print(f"  v_max: {traj_params.v_max}")
    print(f"  d_safe: {traj_params.d_safe}")

    # Make initial snapshot
    initial_snapshot = make_initial_level2_snapshot(scenario)

    print(f"\nInitial trajectory positions:")
    for j in scenario.uavs:
        print(f"  UAV {j}: start={initial_snapshot.q[j][0]}, end={initial_snapshot.q[j][79]}")

    # Run precompute
    precompute_result = precompute_offloading_inputs(scenario, params, initial_snapshot)

    print(f"\nPrecompute result:")
    print(f"  N_act: {precompute_result.N_act}")
    print(f"  N_fly: {precompute_result.N_fly}")
    print(f"  E_prop: {precompute_result.E_prop}")

    # Solve offloading
    print(f"\nSolving offloading...")
    offloading_model = OffloadingModel(
        tasks=scenario.tasks,
        uavs=scenario.uavs,
        time_list=scenario.time_slots,
        D_hat_local=precompute_result.D_hat_local,
        D_hat_offload=precompute_result.D_hat_offload,
        E_hat_comp=precompute_result.E_hat_comp,
        alpha=float(config.alpha),
        gamma_w=float(config.gamma_w),
        N_act=precompute_result.N_act,
    )
    success, obj_val = offloading_model.solveProblem()
    print(f"  Success: {success}, Objective: {obj_val}")
    offloading_outputs = offloading_model.getOutputs()

    # Extract active offloads
    active_offloads = _extract_active_offloads(
        scenario, offloading_outputs, initial_snapshot.f_edge
    )
    print(f"  Active offloads count: {len(active_offloads)}")

    # Build SCA subproblem
    print(f"\nBuilding SCA subproblem...")
    try:
        problem, q_var, slack_safe, obj_expr = _build_sca_subproblem(
            scenario=scenario,
            q_ref=initial_snapshot.q,
            f_fixed=initial_snapshot.f_edge,
            params=params,
            traj_params=traj_params,
            active_offloads=active_offloads,
            safe_slack_penalty=float(config.safe_slack_penalty),
            alpha=float(config.alpha),
            lambda_w=float(config.lambda_w),
            N_act=precompute_result.N_act,
            N_fly=precompute_result.N_fly,
        )
        print(f"  Problem built successfully")
        print(f"  Constraints: {len(problem.constraints)}")

        # Test solvers
        solver_fallback = ("CLARABEL", "ECOS", "SCS")
        for solver_name in solver_fallback:
            print(f"\n  Testing solver: {solver_name}")
            try:
                problem.solve(solver=getattr(cp, solver_name), verbose=False)
                print(f"    Status: {problem.status}")
                print(f"    Value: {problem.value}")
            except Exception as e:
                print(f"    Error: {e}")

    except Exception as e:
        print(f"  Error: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    debug_d1_scenario()