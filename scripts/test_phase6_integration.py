"""Relocated Phase6 integration verification entry script."""

import traceback

from script_common import (
    apply_config_overrides,
    apply_task_profile,
    extract_prompt_history,
    get_simulation_steps,
    load_config,
    make_edge_uav_scenario,
    make_edge_uav_solver,
)


def run_case(*, label: str, test_number: int, use_bcd_loop: bool):
    print(f"\n[TEST {test_number}] {label} ...")

    params = load_config()
    apply_config_overrides(
        params,
        pop_size=2,
        iteration=2,
        use_bcd_loop=use_bcd_loop,
    )

    print(
        "  Config: "
        f"popSize={params.popSize}, "
        f"iteration={params.iteration}, "
        f"use_bcd_loop={params.use_bcd_loop}"
    )

    scenario = make_edge_uav_scenario(params)
    apply_task_profile(scenario, "relaxed_tau_low_local")

    solver = make_edge_uav_solver(params, scenario)

    try:
        final_pop = solver.run()
        best_ind = final_pop[0]
        best_cost = best_ind.get("evaluation_score", float("inf"))
        prompt_history = extract_prompt_history(best_ind)
        sim_steps = get_simulation_steps(best_ind)

        print(f"  [OK] {label} succeeded")
        print(f"    Best cost: {best_cost:.4f}")
        print(f"    [DEBUG] best_ind keys: {list(best_ind.keys())}")
        print(f"    promptHistory keys: {list(prompt_history.keys())}")
        print(f"    simulation_steps keys: {list(sim_steps.keys())}")

        if use_bcd_loop:
            for step_key, step_data in sim_steps.items():
                bcd_meta = step_data.get("bcd_meta", {})
                if bcd_meta:
                    print(
                        f"    bcd_meta (step {step_key}): "
                        f"converged={bcd_meta.get('converged')}, "
                        f"iterations={bcd_meta.get('iterations')}"
                    )

        return {
            "params": params,
            "best_cost": best_cost,
            "prompt_history": prompt_history,
            "sim_steps": sim_steps,
        }
    except Exception as exc:
        print(f"  [FAIL] {label} failed: {exc}")
        traceback.print_exc()
        return None


def run_phase6_integration():
    print("\n" + "=" * 70)
    print("Phase6 Step4 BCD integration verification")
    print("=" * 70)

    baseline_result = run_case(
        label="Baseline run (use_bcd_loop=False)",
        test_number=1,
        use_bcd_loop=False,
    )
    if baseline_result is None:
        return False

    bcd_result = run_case(
        label="BCD integration run (use_bcd_loop=True)",
        test_number=2,
        use_bcd_loop=True,
    )
    if bcd_result is None:
        return False

    baseline_best_cost = baseline_result["best_cost"]
    baseline_prompt_history = baseline_result["prompt_history"]

    bcd_best_cost = bcd_result["best_cost"]
    bcd_prompt_history = bcd_result["prompt_history"]
    bcd_sim_steps = bcd_result["sim_steps"]
    params_bcd = bcd_result["params"]

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
