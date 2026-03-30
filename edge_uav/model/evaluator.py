"""Edge UAV 固定评估器 — 与 LLM 生成的目标函数无关的统一评分。

HS（Harmony Search）进化的是不同目标函数，各自 objVal 不可比。
本模块提供固定公式评估所有个体的决策质量，确保种群排序公平。

评分方向：MINIMIZE（越小越好），与 hsSorting 升序排列兼容。
"""

from __future__ import annotations

from typing import Any

INVALID_OUTPUT_PENALTY: float = 1e12


# =====================================================================
# outputs 索引与校验
# =====================================================================

def _index_outputs(
    outputs: dict,
    scenario: Any,
) -> dict[int, tuple[str, int | None, int]]:
    """将 OffloadingModel.getOutputs() 的嵌套结构转为平坦映射并校验。

    返回
    -------
    dict[(i, t)] = ("local", None) | ("offload", j)

    校验规则（任一失败抛 ValueError）:
      - 每个 active (i, t) 恰好出现一次
      - 无 inactive 任务被分配
      - 无未知 task_id 或 uav_id
      - 无重复分配
    """
    valid_tasks = set(scenario.tasks.keys())
    valid_uavs = set(scenario.uavs.keys())

    assignments: dict[int, tuple[str, int | None, int]] = {}

    for t in scenario.time_slots:
        slot = outputs.get(t)
        if slot is None:
            raise ValueError(f"outputs missing time slot {t}")

        # 本地分配
        for i in slot.get("local", []):
            if i not in valid_tasks:
                raise ValueError(f"unknown task_id={i} in local at t={t}")
            if i in assignments:
                raise ValueError(f"duplicate assignment for task {i}")
            if not scenario.tasks[i].active.get(t, False):
                raise ValueError(f"inactive task ({i}, {t}) incorrectly assigned")
            assignments[i] = ("local", None, t)

        # 卸载分配
        for j, task_ids in slot.get("offload", {}).items():
            if j not in valid_uavs:
                raise ValueError(f"unknown uav_id={j} in offload at t={t}")
            for i in task_ids:
                if i not in valid_tasks:
                    raise ValueError(f"unknown task_id={i} in offload to UAV {j} at t={t}")
                if i in assignments:
                    raise ValueError(f"duplicate assignment for task {i}")
                if not scenario.tasks[i].active.get(t, False):
                    raise ValueError(f"inactive task ({i}, {t}) incorrectly assigned")
                assignments[i] = ("offload", j, t)

    # 完备性检查：每个 active (i, t) 必须被分配，inactive 不得出现
    for i in scenario.tasks:
        if i not in assignments:
            raise ValueError(f"task {i} not assigned")

    return assignments


# =====================================================================
# 固定评估函数
# =====================================================================

def evaluate_solution(
    outputs: dict,
    precompute_result: Any,
    scenario: Any,
    *,
    delay_weight: float = 1.0,
    energy_weight: float = 1.0,
    deadline_weight: float = 0.0,
    balance_weight: float = 0.0,
) -> float:
    """固定评估函数，独立于 LLM 生成的目标函数。

    score = delay_weight  * sum(delay_i_t / tau_i)
          + energy_weight * sum(E_comp_j_i_t / E_max_j)
          + deadline_weight * sum(max(0, delay/tau - 1))
          + balance_weight * load_variance_term

    参数
    ----------
    outputs : dict
        OffloadingModel.getOutputs() 的输出。
    precompute_result : PrecomputeResult
        预计算结果（D_hat_local, D_hat_offload, E_hat_comp）。
    scenario : EdgeUavScenario
        场景数据。
    delay_weight, energy_weight : float
        归一化时延/能耗权重，默认各 1.0。
    deadline_weight : float
        截止期超限罚项权重，默认 0.0（BLP 硬约束已保证）。
    balance_weight : float
        负载均衡罚项权重，默认 0.0。

    返回
    -------
    float
        评估分数（MINIMIZE，越小越好）。
        校验失败时返回 INVALID_OUTPUT_PENALTY。
    """
    try:
        assignments = _index_outputs(outputs, scenario)
    except (ValueError, TypeError, AttributeError):
        return INVALID_OUTPUT_PENALTY

    try:
        return _compute_score(
            assignments, precompute_result, scenario,
            delay_weight=delay_weight,
            energy_weight=energy_weight,
            deadline_weight=deadline_weight,
            balance_weight=balance_weight,
        )
    except (KeyError, TypeError, ZeroDivisionError):
        return INVALID_OUTPUT_PENALTY


def _compute_score(
    assignments, precompute_result, scenario,
    *, delay_weight, energy_weight, deadline_weight, balance_weight,
):
    """内部评分计算，抛出异常由调用方统一处理。"""
    delay_term = 0.0
    energy_term = 0.0
    deadline_term = 0.0
    offload_counts: dict[int, int] = {j: 0 for j in scenario.uavs}

    for i, task in scenario.tasks.items():
        tau = float(task.tau)
        mode, j, t = assignments[i]

        if mode == "local":
            delay = precompute_result.D_hat_local[i][t]
        else:
            delay = precompute_result.D_hat_offload[i][j][t]
            energy_term += (
                precompute_result.E_hat_comp[j][i][t]
                / scenario.uavs[j].E_max
            )
            offload_counts[j] += 1

        normalized_delay = delay / tau
        delay_term += normalized_delay

        if deadline_weight > 0.0:
            overshoot = normalized_delay - 1.0
            if overshoot > 0.0:
                deadline_term += overshoot

    # 负载均衡项：卸载任务数的方差（归一化）
    balance_term = 0.0
    if balance_weight > 0.0:
        total_offloaded = sum(offload_counts.values())
        if total_offloaded > 0:
            mean_load = total_offloaded / len(offload_counts)
            balance_term = sum(
                (cnt - mean_load) ** 2 for cnt in offload_counts.values()
            ) / total_offloaded

    return (
        delay_weight * delay_term
        + energy_weight * energy_term
        + deadline_weight * deadline_term
        + balance_weight * balance_term
    )
