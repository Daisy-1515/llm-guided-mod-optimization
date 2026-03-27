"""Phase⑥ Step4 BCD 集成验证脚本 — 小规模 HS 运行（popSize=2, iteration=2）

用法:
    uv run python test_phase6_integration.py

验证内容:
    1. 基线运行 (use_bcd_loop=False) — 回归测试
    2. BCD 运行 (use_bcd_loop=True) — 验证 Level 1+2a+2b 集成
    3. 成本单调性：cost(L1+2a+2b) <= cost(L1)
    4. promptHistory 兼容性检查
"""

import os
import json
from pathlib import Path
from config.config import configPara
from edge_uav.scenario_generator import EdgeUavScenarioGenerator
from heuristics.hsFrame import HarmonySearchSolver


def run_phase6_integration():
    """执行 Phase⑥ Step4 集成验证。"""

    print("\n" + "="*70)
    print("Phase⑥ Step4 BCD 集成验证 (小规模 HS 运行)")
    print("="*70)

    # ---- 基线运行 (use_bcd_loop=False) ----
    print("\n[TEST 1] 基线运行 (use_bcd_loop=False) ...")
    params_baseline = configPara(None, None)
    params_baseline.getConfigInfo()

    # 小规模配置
    params_baseline.popSize = 2
    params_baseline.iteration = 2
    params_baseline.use_bcd_loop = False  # 明确禁用 BCD

    print(f"  Config: popSize={params_baseline.popSize}, iteration={params_baseline.iteration}, use_bcd_loop={params_baseline.use_bcd_loop}")

    gen_baseline = EdgeUavScenarioGenerator()
    scenario_baseline = gen_baseline.getScenarioInfo(params_baseline)

    # 放宽 tau 确保 BLP 可行
    for task in scenario_baseline.tasks.values():
        task.tau = 200.0
        task.f_local = 1e6

    hs_baseline = HarmonySearchSolver(params_baseline, scenario_baseline, individual_type="edge_uav")
    hs_baseline.pop.timeout = 600

    try:
        baseline_final_pop = hs_baseline.run()
        # 从最终种群中获取最优个体（已排序，索引0是最优）
        baseline_best_cost = baseline_final_pop[0].get("evaluation_score", float('inf'))
        baseline_best_idx = 0

        print(f"  [OK] Baseline run succeeded")
        print(f"    最优成本: {baseline_best_cost:.4f}")

        # 抽取 promptHistory 进行兼容性检查
        best_ind = baseline_final_pop[baseline_best_idx]
        print(f"    [DEBUG] best_ind keys: {list(best_ind.keys())}")

        # promptHistory might be nested or the entire dict might be promptHistory
        if "promptHistory" in best_ind:
            baseline_prompt_history = best_ind.get("promptHistory", {})
        else:
            # The entire dict might BE the promptHistory
            baseline_prompt_history = best_ind

        baseline_sim_steps = baseline_prompt_history.get("simulation_steps", {})

        print(f"    promptHistory keys: {list(baseline_prompt_history.keys())}")
        print(f"    simulation_steps keys: {list(baseline_sim_steps.keys())}")

    except Exception as e:
        print(f"  [FAIL] 基线运行失败: {e}")
        import traceback
        traceback.print_exc()
        return False

    # ---- BCD 集成运行 (use_bcd_loop=True) ----
    print("\n[TEST 2] BCD 集成运行 (use_bcd_loop=True) ...")
    params_bcd = configPara(None, None)
    params_bcd.getConfigInfo()

    # 小规模配置 + 启用 BCD
    params_bcd.popSize = 2
    params_bcd.iteration = 2
    params_bcd.use_bcd_loop = True  # 启用 BCD

    print(f"  Config: popSize={params_bcd.popSize}, iteration={params_bcd.iteration}, use_bcd_loop={params_bcd.use_bcd_loop}")

    gen_bcd = EdgeUavScenarioGenerator()
    scenario_bcd = gen_bcd.getScenarioInfo(params_bcd)

    # 放宽 tau 确保 BLP 可行
    for task in scenario_bcd.tasks.values():
        task.tau = 200.0
        task.f_local = 1e6

    hs_bcd = HarmonySearchSolver(params_bcd, scenario_bcd, individual_type="edge_uav")
    hs_bcd.pop.timeout = 600

    try:
        bcd_final_pop = hs_bcd.run()
        # 从最终种群中获取最优个体（已排序，索引0是最优）
        bcd_best_cost = bcd_final_pop[0].get("evaluation_score", float('inf'))
        bcd_best_idx = 0

        print(f"  [OK] BCD run succeeded")
        print(f"    最优成本: {bcd_best_cost:.4f}")

        # 抽取 promptHistory 进行 BCD 检查
        bcd_best_ind = bcd_final_pop[bcd_best_idx]
        print(f"    [DEBUG] best_ind keys: {list(bcd_best_ind.keys())}")

        # promptHistory might be nested or the entire dict might be promptHistory
        if "promptHistory" in bcd_best_ind:
            bcd_prompt_history = bcd_best_ind.get("promptHistory", {})
        else:
            # The entire dict might BE the promptHistory
            bcd_prompt_history = bcd_best_ind

        bcd_sim_steps = bcd_prompt_history.get("simulation_steps", {})

        print(f"    promptHistory keys: {list(bcd_prompt_history.keys())}")
        print(f"    simulation_steps keys: {list(bcd_sim_steps.keys())}")

        # 检查 bcd_meta 字段
        for step_key in bcd_sim_steps:
            step_data = bcd_sim_steps[step_key]
            bcd_meta = step_data.get("bcd_meta", {})
            if bcd_meta:
                print(f"    bcd_meta (step {step_key}): converged={bcd_meta.get('converged')}, iterations={bcd_meta.get('iterations')}")

    except Exception as e:
        print(f"  [FAIL] BCD 运行失败: {e}")
        import traceback
        traceback.print_exc()
        return False

    # ---- 验收检查 ----
    print("\n" + "-"*70)
    print("验收检查")
    print("-"*70)

    checks_passed = 0
    checks_total = 0

    # 检查 1: 基线和 BCD 都收敛
    checks_total += 1
    if baseline_best_cost < float('inf') and bcd_best_cost < float('inf'):
        print(f"[PASS] [检查1] 两个运行都收敛到有限成本")
        checks_passed += 1
    else:
        print(f"[FAIL] [检查1] 至少一个运行未收敛 (baseline={baseline_best_cost}, bcd={bcd_best_cost})")

    # 检查 2: 成本单调性 (Level 1+2a+2b <= Level 1)
    checks_total += 1
    cost_diff = baseline_best_cost - bcd_best_cost
    cost_diff_pct = (cost_diff / baseline_best_cost * 100) if baseline_best_cost > 0 else 0

    if bcd_best_cost <= baseline_best_cost + 1e-6:  # 允许数值误差
        print(f"[PASS] [检查2] 成本单调性: cost(BCD)={bcd_best_cost:.4f} <= cost(baseline)={baseline_best_cost:.4f} (改进 {cost_diff_pct:.2f}%)")
        checks_passed += 1
    else:
        print(f"[FAIL] [检查2] 成本单调性违反: cost(BCD)={bcd_best_cost:.4f} > cost(baseline)={baseline_best_cost:.4f}")

    # 检查 3: promptHistory 完整性
    checks_total += 1
    required_keys = {"simulation_steps"}
    baseline_keys = set(baseline_prompt_history.keys())
    bcd_keys = set(bcd_prompt_history.keys())

    if required_keys.issubset(baseline_keys) and required_keys.issubset(bcd_keys):
        print(f"[PASS] [检查3] promptHistory 包含必要字段 {required_keys}")
        checks_passed += 1
    else:
        print(f"[FAIL] [检查3] promptHistory 缺少必要字段 (baseline缺少{required_keys - baseline_keys}, bcd缺少{required_keys - bcd_keys})")

    # 检查 4: BCD 元数据（仅当 use_bcd_loop=True 时）
    checks_total += 1
    bcd_meta_found = False
    for step_key in bcd_sim_steps:
        step_data = bcd_sim_steps[step_key]
        bcd_meta = step_data.get("bcd_meta", {})
        if bcd_meta and ("iterations" in bcd_meta or "converged" in bcd_meta):
            bcd_meta_found = True
            break

    if bcd_meta_found:
        print(f"[PASS] [检查4] BCD 元数据已记录到 promptHistory")
        checks_passed += 1
    else:
        print(f"[WARN] [检查4] BCD 元数据未找到（可能因为 use_bcd_loop=False 或 BCD 禁用）")
        # 这不算失败，因为如果 BCD 禁用了，就不应该有元数据
        if params_bcd.use_bcd_loop:
            print(f"  但 use_bcd_loop=True，这是异常的")
        else:
            checks_passed += 1

    # 检查 5: 无崩溃
    checks_total += 1
    print(f"[PASS] [检查5] 两个运行完成无崩溃")
    checks_passed += 1

    # ---- 总结 ----
    print("\n" + "="*70)
    print(f"验收结果: {checks_passed}/{checks_total} 检查通过")
    print("="*70)

    if checks_passed == checks_total:
        print("\n[PASS] Phase6 Step4 Integration Verification PASSED")
        return True
    else:
        print(f"\n[FAIL] Phase6 Step4 Integration Verification FAILED ({checks_total - checks_passed} checks failed)")
        return False


if __name__ == "__main__":
    success = run_phase6_integration()
    exit(0 if success else 1)
