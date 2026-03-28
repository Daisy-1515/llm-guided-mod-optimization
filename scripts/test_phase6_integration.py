"""Relocated Phase6 integration verification entry script."""

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from config.config import configPara
from edge_uav.scenario_generator import EdgeUavScenarioGenerator
from heuristics.hsFrame import HarmonySearchSolver


def run_phase6_integration():
    print("\n" + "=" * 70)
    print("Phase6 Step4 BCD integration verification")
    print("=" * 70)

    print("\n[TEST 1] Baseline run (use_bcd_loop=False) ...")
    params_baseline = configPara(None, None)
    params_baseline.getConfigInfo()
    params_baseline.popSize = 2
    params_baseline.iteration = 2
    params_baseline.use_bcd_loop = False

    print(
        "  Config: "
        f"popSize={params_baseline.popSize}, "
        f"iteration={params_baseline.iteration}, "
        f"use_bcd_loop={params_baseline.use_bcd_loop}"
    )

    gen_baseline = EdgeUavScenarioGenerator()
    scenario_baseline = gen_baseline.getScenarioInfo(params_baseline)

    for task in scenario_baseline.tasks.values():
        task.tau = 200.0
        task.f_local = 1e6

    hs_baseline = HarmonySearchSolver(
        params_baseline, scenario_baseline, individual_type="edge_uav"
    )
    hs_baseline.pop.timeout = 600

    try:
        baseline_final_pop = hs_baseline.run()
        baseline_best_cost = baseline_final_pop[0].get("evaluation_score", float("inf"))
        baseline_best_idx = 0

        print("  [OK] Baseline run succeeded")
        print(f"    Best cost: {baseline_best_cost:.4f}")

        best_ind = baseline_final_pop[baseline_best_idx]
        print(f"    [DEBUG] best_ind keys: {list(best_ind.keys())}")

        if "promptHistory" in best_ind:
            baseline_prompt_history = best_ind.get("promptHistory", {})
        else:
            baseline_prompt_history = best_ind

        baseline_sim_steps = baseline_prompt_history.get("simulation_steps", {})

        print(f"    promptHistory keys: {list(baseline_prompt_history.keys())}")
        print(f"    simulation_steps keys: {list(baseline_sim_steps.keys())}")

    except Exception as e:
        print(f"  [FAIL] Baseline run failed: {e}")
        import traceback

        traceback.print_exc()
        return False

    print("\n[TEST 2] BCD integration run (use_bcd_loop=True) ...")
    params_bcd = configPara(None, None)
    params_bcd.getConfigInfo()
    params_bcd.popSize = 2
    params_bcd.iteration = 2
    params_bcd.use_bcd_loop = True

    print(
        "  Config: "
        f"popSize={params_bcd.popSize}, "
        f"iteration={params_bcd.iteration}, "
        f"use_bcd_loop={params_bcd.use_bcd_loop}"
    )

    gen_bcd = EdgeUavScenarioGenerator()
    scenario_bcd = gen_bcd.getScenarioInfo(params_bcd)

    for task in scenario_bcd.tasks.values():
        task.tau = 200.0
        task.f_local = 1e6

    hs_bcd = HarmonySearchSolver(params_bcd, scenario_bcd, individual_type="edge_uav")
    hs_bcd.pop.timeout = 600

    try:
        bcd_final_pop = hs_bcd.run()
        bcd_best_cost = bcd_final_pop[0].get("evaluation_score", float("inf"))
        bcd_best_idx = 0

        print("  [OK] BCD run succeeded")
        print(f"    Best cost: {bcd_best_cost:.4f}")

        bcd_best_ind = bcd_final_pop[bcd_best_idx]
        print(f"    [DEBUG] best_ind keys: {list(bcd_best_ind.keys())}")

        if "promptHistory" in bcd_best_ind:
            bcd_prompt_history = bcd_best_ind.get("promptHistory", {})
        else:
            bcd_prompt_history = bcd_best_ind

        bcd_sim_steps = bcd_prompt_history.get("simulation_steps", {})

        print(f"    promptHistory keys: {list(bcd_prompt_history.keys())}")
        print(f"    simulation_steps keys: {list(bcd_sim_steps.keys())}")

        for step_key in bcd_sim_steps:
            step_data = bcd_sim_steps[step_key]
            bcd_meta = step_data.get("bcd_meta", {})
            if bcd_meta:
                print(
                    f"    bcd_meta (step {step_key}): "
                    f"converged={bcd_meta.get('converged')}, "
                    f"iterations={bcd_meta.get('iterations')}"
                )

    except Exception as e:
        print(f"  [FAIL] BCD run failed: {e}")
        import traceback

        traceback.print_exc()
        return False

    print("\n" + "-" * 70)
    print("Acceptance checks")
    print("-" * 70)

    checks_passed = 0
    checks_total = 0

    checks_total += 1
    if baseline_best_cost < float("inf") and bcd_best_cost < float("inf"):
        print("[PASS] Both runs converged to finite costs")
        checks_passed += 1
    else:
        print(
            "[FAIL] At least one run did not converge "
            f"(baseline={baseline_best_cost}, bcd={bcd_best_cost})"
        )

    checks_total += 1
    cost_diff = baseline_best_cost - bcd_best_cost
    cost_diff_pct = (cost_diff / baseline_best_cost * 100) if baseline_best_cost > 0 else 0
    if bcd_best_cost <= baseline_best_cost + 1e-6:
        print(
            "[PASS] Cost monotonicity holds: "
            f"cost(BCD)={bcd_best_cost:.4f} <= cost(baseline)={baseline_best_cost:.4f} "
            f"(improvement {cost_diff_pct:.2f}%)"
        )
        checks_passed += 1
    else:
        print(
            "[FAIL] Cost monotonicity violated: "
            f"cost(BCD)={bcd_best_cost:.4f} > cost(baseline)={baseline_best_cost:.4f}"
        )

    checks_total += 1
    required_keys = {"simulation_steps"}
    baseline_keys = set(baseline_prompt_history.keys())
    bcd_keys = set(bcd_prompt_history.keys())
    if required_keys.issubset(baseline_keys) and required_keys.issubset(bcd_keys):
        print(f"[PASS] promptHistory contains required keys {required_keys}")
        checks_passed += 1
    else:
        print(
            "[FAIL] promptHistory missing required keys "
            f"(baseline missing {required_keys - baseline_keys}, "
            f"bcd missing {required_keys - bcd_keys})"
        )

    checks_total += 1
    bcd_meta_found = False
    for step_key in bcd_sim_steps:
        step_data = bcd_sim_steps[step_key]
        bcd_meta = step_data.get("bcd_meta", {})
        if bcd_meta and ("iterations" in bcd_meta or "converged" in bcd_meta):
            bcd_meta_found = True
            break

    if bcd_meta_found:
        print("[PASS] BCD metadata is recorded in promptHistory")
        checks_passed += 1
    else:
        print("[WARN] No BCD metadata found in promptHistory")
        if not params_bcd.use_bcd_loop:
            checks_passed += 1

    checks_total += 1
    print("[PASS] Both runs completed without crashing")
    checks_passed += 1

    print("\n" + "=" * 70)
    print(f"Acceptance result: {checks_passed}/{checks_total} checks passed")
    print("=" * 70)

    if checks_passed == checks_total:
        print("\n[PASS] Phase6 Step4 integration verification passed")
        return True

    print(
        f"\n[FAIL] Phase6 Step4 integration verification failed "
        f"({checks_total - checks_passed} checks failed)"
    )
    return False


def main():
    return 0 if run_phase6_integration() else 1


if __name__ == "__main__":
    raise SystemExit(main())
