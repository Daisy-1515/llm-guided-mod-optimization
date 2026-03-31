"""L1 Solver 完整性测试 — 无 Drop 版本

测试核心项：
  T1. 变量无条件创建 (test_vars_unconditional)：所有活跃 (i,t) 都有 x_local 和 x_offload
  T2. 按 i 聚合约束 (test_assign_once_per_task)：每个任务恰好分配一次
  T3. 输出格式无 drop (test_output_no_drop)：getOutputs 不含 drop 字段
  T4. 超时任务仍被分配 (test_tight_deadline_still_assigned)：D > tau 的任务不被丢弃

对应变更：移除 drop 失败机制，回退到 9d562f2 语义 + 移除卸载过滤
"""

from __future__ import annotations

import pytest

from config.config import configPara
from edge_uav.data import ComputeTask, UAV, EdgeUavScenario
from edge_uav.model.offloading import OffloadingModel
from edge_uav.model.precompute import (
    Level2Snapshot,
    PrecomputeParams,
    precompute_offloading_inputs,
)


# =====================================================================
# 辅助函数 — 构造测试场景与快照
# =====================================================================


def _make_initial_snapshot(scenario: EdgeUavScenario) -> Level2Snapshot:
    """创建初始 Level2 快照：所有 UAV 初始位置，所有边缘频率设为 1e9"""
    q = {j: {t: scenario.uavs[j].pos for t in scenario.time_slots} for j in scenario.uavs}
    f_edge = {
        j: {i: {t: 1e9 for t in scenario.time_slots} for i in scenario.tasks}
        for j in scenario.uavs
    }
    return Level2Snapshot(q=q, f_edge=f_edge, source="test_init")


def _make_tight_scenario() -> EdgeUavScenario:
    """构造截止期非常紧张的场景（以前会 drop，现在应被正常分配）。

    tasks[0]：tau=0.01s，本地和卸载延迟都会超期，但仍应被分配。
    """
    tasks = {
        0: ComputeTask(
            index=0,
            pos=(100.0, 200.0),
            D_l=1e6,
            D_r=5e5,
            F=1e9,
            tau=0.01,  # 非常紧张的截止期
            active={0: True, 1: True},
            f_local=1e9,
        ),
    }
    uavs = {
        0: UAV(
            index=0,
            pos=(500.0, 500.0),
            pos_final=(500.0, 500.0),
            E_max=1000.0,
            f_max=1e10,
            N_max=1,
        ),
        1: UAV(
            index=1,
            pos=(600.0, 600.0),
            pos_final=(600.0, 600.0),
            E_max=1000.0,
            f_max=1e10,
            N_max=1,
        ),
    }
    return EdgeUavScenario(
        tasks=tasks,
        uavs=uavs,
        time_slots=[0, 1],
        seed=42,
        meta={},
    )


def _make_normal_scenario() -> EdgeUavScenario:
    """构造常规场景：任务可行，有 local/offload 选项"""
    tasks = {
        0: ComputeTask(
            index=0,
            pos=(100.0, 200.0),
            D_l=1e6,
            D_r=5e5,
            F=1e9,
            tau=5.0,
            active={0: True, 1: True},
            f_local=1e9,
        ),
    }
    uavs = {
        0: UAV(
            index=0,
            pos=(500.0, 500.0),
            pos_final=(500.0, 500.0),
            E_max=1000.0,
            f_max=1e10,
            N_max=1,
        ),
    }
    return EdgeUavScenario(
        tasks=tasks,
        uavs=uavs,
        time_slots=[0, 1],
        seed=43,
        meta={},
    )


def _build_model(scenario):
    """构建 OffloadingModel 并返回 (model, precompute_result)"""
    config = configPara(None, None)
    params = PrecomputeParams.from_config(config)
    snapshot = _make_initial_snapshot(scenario)
    precompute_result = precompute_offloading_inputs(scenario, params, snapshot)

    model = OffloadingModel(
        tasks=scenario.tasks,
        uavs=scenario.uavs,
        time_list=scenario.time_slots,
        D_hat_local=precompute_result.D_hat_local,
        D_hat_offload=precompute_result.D_hat_offload,
        E_hat_comp=precompute_result.E_hat_comp,
        alpha=config.alpha,
        gamma_w=config.gamma_w,
    )
    return model, precompute_result


# =====================================================================
# Test T1: 变量无条件创建
# =====================================================================


def test_vars_unconditional():
    """所有活跃 (i,t) 都应有 x_local 变量，所有活跃 (i,j,t) 都应有 x_offload 变量。"""
    scenario = _make_tight_scenario()
    model, _ = _build_model(scenario)
    model.initModel()
    model.setupVars()

    for i in model.taskList:
        for t in model.timeList:
            if model.task[i].active[t]:
                assert (i, t) in model.x_local, \
                    f"x_local[{i},{t}] 应无条件创建"
                for j in model.uavList:
                    assert (i, j, t) in model.x_offload, \
                        f"x_offload[{i},{j},{t}] 应无条件创建"

    # 确认无 drop 属性或 drop 为空
    assert not hasattr(model, 'drop') or not model.drop, \
        "不应有 drop 变量"


# =====================================================================
# Test T2: 按 i 聚合约束（每个任务恰好分配一次）
# =====================================================================


def test_assign_once_per_task():
    """求解后，每个任务在所有时隙中恰好出现在一个位置。"""
    scenario = _make_normal_scenario()
    model, _ = _build_model(scenario)
    feasible, cost = model.solveProblem()

    assert feasible, "常规场景应可行"
    outputs = model.getOutputs()

    # 统计每个任务被分配的次数
    for i in scenario.tasks:
        count = 0
        for t in outputs:
            if i in outputs[t]["local"]:
                count += 1
            for j in outputs[t]["offload"]:
                if i in outputs[t]["offload"][j]:
                    count += 1
        assert count == 1, f"任务 {i} 应恰好分配 1 次，实际 {count} 次"


# =====================================================================
# Test T3: 输出格式无 drop
# =====================================================================


def test_output_no_drop():
    """getOutputs 返回的字典不应包含 'drop' 字段。"""
    scenario = _make_normal_scenario()
    model, _ = _build_model(scenario)
    feasible, cost = model.solveProblem()
    outputs = model.getOutputs()

    for t in outputs:
        assert "drop" not in outputs[t], \
            f"时隙 {t} 不应包含 'drop' 字段"
        assert "local" in outputs[t]
        assert "offload" in outputs[t]


# =====================================================================
# Test T4: 超时任务仍被分配（不被丢弃）
# =====================================================================


def test_tight_deadline_still_assigned():
    """即使 D > tau（超时），任务仍应被分配到某个位置。

    超时通过 D/τ > 1 自然反映在目标值中，不应被 drop。
    """
    scenario = _make_tight_scenario()
    model, _ = _build_model(scenario)
    feasible, cost = model.solveProblem()

    assert feasible, "即使截止期紧张，模型仍应可行（无 drop 约束）"

    outputs = model.getOutputs()

    # 每个任务都应被分配
    for i in scenario.tasks:
        assigned = False
        for t in outputs:
            if i in outputs[t]["local"]:
                assigned = True
                break
            for j in outputs[t]["offload"]:
                if i in outputs[t]["offload"][j]:
                    assigned = True
                    break
            if assigned:
                break
        assert assigned, f"任务 {i} 应被分配（即使超时），不应被丢弃"

    # 确认目标值 > 1（因为 D/tau > 1 对超时任务）
    assert cost > 1.0, f"超时任务的目标值应 > 1，实际 {cost}"


# =====================================================================
# Test T5: 本地可行性诊断方法仍可用
# =====================================================================


def test_feasibility_methods_still_available():
    """_offload_feasible 和 _local_feasible 方法仍应存在（用于诊断）。"""
    scenario = _make_normal_scenario()
    model, _ = _build_model(scenario)

    assert hasattr(model, '_offload_feasible')
    assert hasattr(model, '_local_feasible')

    # 常规场景中，本地应可行
    result = model._local_feasible(0, 0)
    assert isinstance(result, bool)
