#!/usr/bin/env python3
"""
Verify N_max parameter behavior during optimization.

Compare runs with:
1. N_max = 1 (max 1 task per slot)
2. N_max = 2 (max 2 tasks per slot)
3. N_max = None (unlimited)

Check if constraints are correctly applied to objective function.
"""

import os
import sys
from pathlib import Path

# Add project root to path
repo_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(repo_root))

from config.config import configPara
from edge_uav.scenario_generator import EdgeUavScenarioGenerator
from edge_uav.model.offloading import OffloadingModel
from edge_uav.model.precompute import (
    PrecomputeParams,
    precompute_offloading_inputs,
    make_initial_level2_snapshot,
)


def run_nmax_verification():
    """Verify N_max parameter is effective."""

    print("="*70)
    print("N_max Parameter Verification Test")
    print("="*70)

    # Load configuration
    cfg = configPara(None, None)
    cfg.getConfigInfo()

    # Store original
    original_n_max = cfg.N_max
    print(f"\n[OK] Original config N_max = {original_n_max}")

    # Generate scenario once (keep consistent)
    print("\nGenerating scenario...")
    generator = EdgeUavScenarioGenerator()
    scenario = generator.getScenarioInfo(cfg)

    print(f"  Scenario: {len(scenario.tasks)} tasks, {len(scenario.uavs)} UAVs, {len(scenario.time_slots)} slots")

    # Precompute
    print("\nRunning precompute module...")
    params = PrecomputeParams.from_config(cfg)
    snapshot = make_initial_level2_snapshot(scenario)
    precompute_result = precompute_offloading_inputs(
        scenario=scenario,
        params=params,
        snapshot=snapshot,
    )
    D_hat_local = precompute_result.D_hat_local
    D_hat_offload = precompute_result.D_hat_offload
    E_hat_comp = precompute_result.E_hat_comp

    # Test different N_max values
    nmax_values = [1, 2, None]
    results = {}

    for nmax in nmax_values:
        print(f"\n{'='*70}")
        print(f"Testing N_max = {nmax}")
        print(f"{'='*70}")

        # Modify UAV N_max
        for uav in scenario.uavs.values():
            uav.N_max = nmax

        # Build model
        print("Building optimization model...")
        model = OffloadingModel(
            tasks=scenario.tasks,
            uavs=scenario.uavs,
            time_list=scenario.time_slots,
            D_hat_local=D_hat_local,
            D_hat_offload=D_hat_offload,
            E_hat_comp=E_hat_comp,
            alpha=cfg.alpha,
            gamma_w=cfg.gamma_w,
        )

        # Solve
        print(f"Solving model (N_max={nmax})...")
        feasible, cost = model.solveProblem()

        if feasible:
            outputs = model.getOutputs()

            # Analyze output
            stats = {
                'feasible': True,
                'cost': cost,
                'total_offload': 0,
                'total_local': 0,
                'per_uav_per_slot': {},
            }

            for t in scenario.time_slots:
                local_count = len(outputs[t]['local'])
                stats['total_local'] += local_count

                for j in scenario.uavs.keys():
                    offload_count = len(outputs[t]['offload'][j])
                    stats['total_offload'] += offload_count

                    key = f"UAV{j}_Slot{t}"
                    stats['per_uav_per_slot'][key] = offload_count

                    # Check N_max violation
                    if nmax is not None and offload_count > nmax:
                        print(f"  [WARN] {key} assigned {offload_count} tasks, exceeds N_max={nmax}")

            # Report
            print(f"\n  [OK] Feasible solution found!")
            print(f"    - Objective value: {cost:.6f}")
            print(f"    - Total local execution: {stats['total_local']} tasks")
            print(f"    - Total offload execution: {stats['total_offload']} tasks")

            if nmax is not None:
                max_per_slot = {}
                for t in scenario.time_slots:
                    max_in_slot = max(
                        (len(outputs[t]['offload'][j]) for j in scenario.uavs.keys()),
                        default=0
                    )
                    max_per_slot[t] = max_in_slot

                print(f"    - Max UAV load per slot: {max_per_slot}")
                all_within_limit = all(v <= nmax for v in max_per_slot.values())
                if all_within_limit:
                    print(f"    [OK] All slots respect N_max={nmax} constraint")
                else:
                    print(f"    [ERROR] Some slots violate N_max={nmax} constraint")
        else:
            print(f"  [ERROR] Model is infeasible")
            stats = {'feasible': False, 'cost': -1}

        results[nmax] = stats

    # Comparison summary
    print(f"\n{'='*70}")
    print("Comparison Summary")
    print(f"{'='*70}")

    for nmax in nmax_values:
        r = results[nmax]
        status = "[OK] Feasible" if r['feasible'] else "[ERROR] Infeasible"
        cost_str = f"{r['cost']:.6f}" if r['feasible'] else "N/A"
        print(f"N_max={str(nmax):8s}  {status}  Cost={cost_str}")

    print("\nVerification complete!")


if __name__ == "__main__":
    try:
        run_nmax_verification()
    except Exception as e:
        print(f"\n[ERROR] {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
