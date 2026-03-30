#!/usr/bin/env python3
"""
诊断脚本：区分"未分配对"vs"被分配对"的卸载可行性统计

核心问题：offload_feasible_ratio 现在混合了：
1. 被分配对（f_edge > 0）中满足 tau 的比例
2. 未分配对（f_edge = 0）中满足 tau 的比例（通常很小，因为 f_edge=0 导致时延爆炸）

这个脚本分离统计，以及查看每个未分配对的实际可行性（如果赋予合理 f_edge）。
"""

import math

from script_common import ROOT, load_config, make_edge_uav_scenario

from edge_uav.model.precompute import precompute_offloading_inputs, _offload_delay
from edge_uav.model.scenario import EdgeUavScenario
from config.config import configPara


def diagnose_feasibility(
    scenario: EdgeUavScenario,
    snapshot,
    params: configPara,
    seed: int = None,
):
    """
    诊断卸载可行性，分离"分配vs未分配"统计
    """
    tasks = scenario.tasks
    uavs = scenario.uavs
    time_slots = scenario.timeList

    # 统计三大类
    assigned_feasible = 0    # f_edge > 0 且 d_offload <= tau
    assigned_infeasible = 0  # f_edge > 0 且 d_offload > tau
    unassigned_theoretically_feasible = 0  # f_edge = 0，但若赋予 f_max 则 d_offload <= tau
    unassigned_intrinsically_infeasible = 0  # f_edge = 0，即使 f_max 也不满足 tau

    # 详细记录
    assigned_pairs = []
    unassigned_feasible = []
    unassigned_infeasible = []

    eps_freq = params.eps_freq
    eps_rate = params.eps_rate
    big_m_delay = params.big_m_delay
    tau_tol = params.tau_tol

    for i, task in tasks.items():
        tau_limit = float(task.tau) + tau_tol
        for j, uav in uavs.items():
            for t in time_slots:
                is_active = bool(task.active.get(t, False))
                if not is_active:
                    continue

                # 获取频率分配和链路参数
                f_edge_val = float(snapshot.f_edge[j][i][t])

                # 计算链路速率
                pos_j = uav.trajectory.get_position(t)
                pos_i = task.location
                gain = uav.channel.calc_gain_db(pos_j, pos_i)

                r_up = uav.channel.calc_rate(
                    gain, params.B_up, params.P_i, params.N_0, params.rho_0
                )
                r_up = max(r_up, eps_rate)

                r_down = uav.channel.calc_rate(
                    gain, params.B_down, params.P_j, params.N_0, params.rho_0
                )
                r_down = max(r_down, eps_rate)

                # 情形 1: 被分配（f_edge > 0）
                if f_edge_val > 0:
                    d_offload = _offload_delay(
                        D_l=float(task.D_l),
                        D_r=float(task.D_r),
                        workload=float(task.F),
                        r_up=r_up,
                        r_down=r_down,
                        f_edge=f_edge_val,
                        eps_rate=eps_rate,
                        eps_freq=eps_freq,
                        big_m_delay=big_m_delay,
                    )

                    is_feasible = d_offload <= tau_limit
                    if is_feasible:
                        assigned_feasible += 1
                    else:
                        assigned_infeasible += 1

                    assigned_pairs.append({
                        "task": i,
                        "uav": j,
                        "slot": t,
                        "f_edge": f_edge_val,
                        "d_offload": d_offload,
                        "tau": task.tau,
                        "feasible": is_feasible,
                    })

                # 情形 2: 未分配（f_edge = 0）
                else:
                    # 2a. 如果赋予 f_max，能否满足?
                    d_offload_max_freq = _offload_delay(
                        D_l=float(task.D_l),
                        D_r=float(task.D_r),
                        workload=float(task.F),
                        r_up=r_up,
                        r_down=r_down,
                        f_edge=params.f_max,
                        eps_rate=eps_rate,
                        eps_freq=eps_freq,
                        big_m_delay=big_m_delay,
                    )

                    # 2b. 当前 f_edge=0 的情况
                    d_offload_zero_freq = _offload_delay(
                        D_l=float(task.D_l),
                        D_r=float(task.D_r),
                        workload=float(task.F),
                        r_up=r_up,
                        r_down=r_down,
                        f_edge=eps_freq,  # 用 eps_freq 代替 0
                        eps_rate=eps_rate,
                        eps_freq=eps_freq,
                        big_m_delay=big_m_delay,
                    )

                    if d_offload_max_freq <= tau_limit:
                        unassigned_theoretically_feasible += 1
                        unassigned_feasible.append({
                            "task": i,
                            "uav": j,
                            "slot": t,
                            "d_at_f_max": d_offload_max_freq,
                            "d_at_eps": d_offload_zero_freq,
                            "tau": task.tau,
                        })
                    else:
                        unassigned_intrinsically_infeasible += 1
                        unassigned_infeasible.append({
                            "task": i,
                            "uav": j,
                            "slot": t,
                            "d_at_f_max": d_offload_max_freq,
                            "d_at_eps": d_offload_zero_freq,
                            "tau": task.tau,
                        })

    total_pairs = (
        assigned_feasible + assigned_infeasible +
        unassigned_theoretically_feasible + unassigned_intrinsically_infeasible
    )

    print("\n" + "="*80)
    print(f"OFFLOAD FEASIBILITY DIAGNOSIS (seed={seed})")
    print("="*80)
    print(f"\n【总对数】{total_pairs}")
    print(f"  ├─ 被分配对（f_edge > 0）: {assigned_feasible + assigned_infeasible}")
    print(f"  │  ├─ 可行（d_offload ≤ tau）: {assigned_feasible}")
    print(f"  │  └─ 不可行（d_offload > tau）: {assigned_infeasible}")
    print(f"  └─ 未分配对（f_edge = 0）: {unassigned_theoretically_feasible + unassigned_intrinsically_infeasible}")
    print(f"     ├─ 理论可行（若 f_edge=f_max 则 d_offload ≤ tau）: {unassigned_theoretically_feasible}")
    print(f"     └─ 本质不可行（即使 f_edge=f_max 仍 d_offload > tau）: {unassigned_intrinsically_infeasible}")

    print(f"\n【当前混合口径】")
    current_ratio = (assigned_feasible + unassigned_intrinsically_infeasible) / total_pairs if total_pairs > 0 else 0
    # 注：这里假设"未分配对"在预计算里用 eps_freq，导致几乎都看成不可行，所以分子只有 assigned_feasible
    actual_ratio = assigned_feasible / total_pairs if total_pairs > 0 else 0
    print(f"  offload_feasible_ratio ≈ {actual_ratio:.4f}  ({assigned_feasible}/{total_pairs})")
    print(f"  ┗─ 这就是为啥"初始 50%"降到"最终 <1%"——未分配对被算成不可行了")

    print(f"\n【如果分离统计】")
    if assigned_feasible + assigned_infeasible > 0:
        assigned_ratio = assigned_feasible / (assigned_feasible + assigned_infeasible)
        print(f"  已分配对可行率: {assigned_ratio:.4f}  ({assigned_feasible}/{assigned_feasible + assigned_infeasible})")
    else:
        print(f"  已分配对: 无")

    if unassigned_theoretically_feasible + unassigned_intrinsically_infeasible > 0:
        unassigned_ratio = unassigned_theoretically_feasible / (
            unassigned_theoretically_feasible + unassigned_intrinsically_infeasible
        )
        print(f"  未分配对理论可行率: {unassigned_ratio:.4f}  ({unassigned_theoretically_feasible}/{unassigned_theoretically_feasible + unassigned_intrinsically_infeasible})")
    else:
        print(f"  未分配对: 无")

    print(f"\n【诊断结论】")
    if actual_ratio < 0.1:
        print(f"  ⚠ 当前混合口径 < 10%，说明：")
        print(f"    1. 被分配对本身也很少满足 tau（deadline 压力很大）")
        print(f"    2. 或者大部分对都未分配，被算成"不可行"拉低了整体比例")
        if assigned_feasible / total_pairs < 0.05:
            print(f"    3. 特别地，被分配可行对占比 {assigned_feasible / total_pairs:.4f} < 5%")
            print(f"       说明 deadline 本身非常紧张，不是"未分配"问题")
    else:
        print(f"  ✓ 混合口径 ≥ 10%，被分配对中多数满足 tau")

    print("\n" + "="*80)


if __name__ == "__main__":
    import json

    params = load_config()
    scenario = make_edge_uav_scenario(params)

    # 尝试找一个最近的运行结果
    discussion_dir = ROOT / "discussion"
    if discussion_dir.exists():
        runs = sorted(discussion_dir.glob("*"), key=lambda p: p.stat().st_mtime, reverse=True)
        if runs:
            latest_run = runs[0]
            print(f"Loading from: {latest_run}")

            # 加载诊断元数据（如果有）
            diag_file = latest_run / "final_precompute_diagnostics.json"
            if diag_file.exists():
                with open(diag_file) as f:
                    diag = json.load(f)
                print(f"已有诊断数据：offload_feasible_ratio = {diag.get('offload_feasible_ratio', 'N/A')}")
                print(f"  candidate_offload_pairs: {diag.get('candidate_offload_pairs', 'N/A')}")
                print(f"  deadline_feasible_pairs: {diag.get('deadline_feasible_pairs', 'N/A')}")
