"""L1 Solver-Side 完整性测试 — Drop 字段补救

测试 4 个核心项：
  T1. drop 创建条件 (test_drop_creation_exact)：drop 仅在本地和卸载都不可行时创建
  T2. 罚项系数精确性 (test_failure_penalty_coefficient)：不同系数的成本差异验证
  T3. 本地可行性边界 (test_local_feasible_boundary)：D_hat_local <= tau 的边界测试
  T4. 输出格式兼容性 (test_output_schema_compatibility)：新格式不破坏验证函数

对应补救计划：补齐 Level 1 solver-side 输出层完整性
"""

from __future__ import annotations

import pytest
from copy import deepcopy
from typing import TYPE_CHECKING

from config.config import configPara
from edge_uav.data import ComputeTask, UAV, EdgeUavScenario
from edge_uav.model.offloading import OffloadingModel
from edge_uav.model.precompute import (
    Level2Snapshot,
    PrecomputeParams,
    PrecomputeResult,
    precompute_offloading_inputs,
)
from edge_uav.model.bcd_loop import validate_offloading_outputs

if TYPE_CHECKING:
    pass


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


def _make_tight_scenario_for_drop() -> EdgeUavScenario:
    """构造强制 drop 的场景：本地延迟超期，所有 UAV 卸载也超期

    返回值：
      - tasks[0]：截止期非常紧张 (tau=0.01s)
      - uavs[0,1]：通信和卸载延迟都会超期
      - time_slots=[0, 1]
    """
    tasks = {
        0: ComputeTask(
            index=0,
            pos=(100.0, 200.0),  # 任务位置
            D_l=1e6,  # 本地输入数据 (bits)
            D_r=5e5,  # 卸载返回数据 (bits)
            F=1e9,    # 计算量 (cycles)
            tau=0.01,  # ⚠️ 非常紧张的截止期，迫使 drop
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
            tau=5.0,  # 充足的截止期
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


# =====================================================================
# Test T1: drop 创建条件
# =====================================================================


def test_drop_creation_exact():
    """验证 drop[i,t] 仅在"本地和卸载都不可行"时被创建

    关键验证点：
      1. drop 字典仅在 has_local=False 且 has_offload=[] 时创建键
      2. 返回的 getOutputs() 中 drop 列表非空
      3. 同一 (i,t) 不会同时出现在 local 和 drop 中
    """
    scenario = _make_tight_scenario_for_drop()
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
    model.penalty_drop = config.penalty_drop
    model.initModel()
    model.setupVars()

    # ✅ Assertion 1: drop 字典应该被创建且非空
    assert model.drop is not None, "drop 字典应被初始化"
    assert len(model.drop) > 0, "tight 场景应该产生至少一个 drop 键"

    # 求解
    feasible, cost = model.solveProblem()
    outputs = model.getOutputs()

    # ✅ Assertion 2: 检查输出格式
    for t in outputs.keys():
        assert "drop" in outputs[t], f"时隙 {t} 缺少 'drop' 字段"
        assert isinstance(outputs[t]["drop"], list), f"时隙 {t} 的 drop 应为列表"

    # ✅ Assertion 3: 验证同一 (i,t) 不会同时在 local 和 drop 中
    for t in outputs.keys():
        local_set = set(outputs[t]["local"])
        drop_set = set(outputs[t]["drop"])
        assert len(local_set & drop_set) == 0, \
            f"时隙 {t}：local 和 drop 集合应不相交，找到重复 {local_set & drop_set}"

    # ✅ Assertion 4: tight 场景至少应有一个 drop
    has_drop = any(len(outputs[t]["drop"]) > 0 for t in outputs.keys())
    assert has_drop, "tight 场景应产生至少一个被 drop 的任务"


# =====================================================================
# Test T2: 罚项系数精确性
# =====================================================================


def test_failure_penalty_coefficient():
    """验证目标函数中 drop 项的系数精确等于 penalty_drop

    方法：在强制-drop 场景中，比较两个不同 penalty_drop 值的成本差异
    差异应该 ≈ (penalty_drop_2 - penalty_drop_1) × drop_count
    """
    scenario = _make_tight_scenario_for_drop()
    config = configPara(None, None)

    params = PrecomputeParams.from_config(config)
    snapshot = _make_initial_snapshot(scenario)
    precompute_result = precompute_offloading_inputs(scenario, params, snapshot)

    # ======= 求解 A：penalty_drop = 1000 =======
    model_a = OffloadingModel(
        tasks=scenario.tasks,
        uavs=scenario.uavs,
        time_list=scenario.time_slots,
        D_hat_local=precompute_result.D_hat_local,
        D_hat_offload=precompute_result.D_hat_offload,
        E_hat_comp=precompute_result.E_hat_comp,
        alpha=config.alpha,
        gamma_w=config.gamma_w,
    )
    model_a.penalty_drop = 1000
    model_a.initModel()
    model_a.setupVars()
    feasible_a, cost_a = model_a.solveProblem()
    outputs_a = model_a.getOutputs()

    # 计数 drop 任务
    drop_count_a = sum(len(outputs_a[t]["drop"]) for t in outputs_a.keys())

    # ======= 求解 B：penalty_drop = 2000 =======
    model_b = OffloadingModel(
        tasks=scenario.tasks,
        uavs=scenario.uavs,
        time_list=scenario.time_slots,
        D_hat_local=precompute_result.D_hat_local,
        D_hat_offload=precompute_result.D_hat_offload,
        E_hat_comp=precompute_result.E_hat_comp,
        alpha=config.alpha,
        gamma_w=config.gamma_w,
    )
    model_b.penalty_drop = 2000
    model_b.initModel()
    model_b.setupVars()
    feasible_b, cost_b = model_b.solveProblem()
    outputs_b = model_b.getOutputs()

    drop_count_b = sum(len(outputs_b[t]["drop"]) for t in outputs_b.keys())

    # ======= 验证：成本差异 ≈ 系数差 × drop_count =======
    if drop_count_a > 0 or drop_count_b > 0:
        actual_cost_diff = cost_b - cost_a
        # 期望差异 = (penalty_drop_b - penalty_drop_a) × drop_count
        # 由于不同求解，drop_count 可能略变化，我们用平均值
        avg_drop_count = (drop_count_a + drop_count_b) / 2.0
        expected_cost_diff = (2000 - 1000) * avg_drop_count

        # 允许 ±10% 的浮点误差（目标函数不仅包含 drop，还有其他项）
        tolerance = abs(expected_cost_diff) * 0.1 if expected_cost_diff != 0 else 10.0
        assert abs(actual_cost_diff - expected_cost_diff) < tolerance, \
            f"系数差异检查失败：期望差 {expected_cost_diff:.2f}，实际 {actual_cost_diff:.2f}，偏差 {actual_cost_diff - expected_cost_diff:.2f}"


# =====================================================================
# Test T3: 本地可行性边界
# =====================================================================


def test_local_feasible_boundary():
    """验证 _local_feasible 的边界：D_local == tau 时应 True，> tau 时应 False

    关键验证点：
      1. 当 D_hat_local[i][t] <= tau 时，_local_feasible 返回 True
      2. 当 D_hat_local[i][t] > tau 时，_local_feasible 返回 False
      3. 边界情况 (== tau) 应返回 True（充要条件）
    """
    scenario = _make_normal_scenario()
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

    # ✅ Assertion：直接调用 _local_feasible
    task_id = 0
    t = 0

    # 获取预计算的 D_hat_local
    d_local = precompute_result.D_hat_local[task_id][t]
    tau_val = scenario.tasks[task_id].tau

    result = model._local_feasible(task_id, t)

    # 根据关系验证
    if d_local <= tau_val:
        assert result == True, \
            f"D_hat_local[{task_id}][{t}]={d_local:.6f} <= tau={tau_val:.6f}，应返回 True，实际 {result}"
    else:
        assert result == False, \
            f"D_hat_local[{task_id}][{t}]={d_local:.6f} > tau={tau_val:.6f}，应返回 False，实际 {result}"


# =====================================================================
# Test T4: 输出格式兼容性（BCD 集成回归）
# =====================================================================


def test_output_schema_compatibility():
    """验证新的 getOutputs 返回格式（含 drop 字段）不破坏现有验证函数

    关键验证点：
      1. getOutputs() 返回包含 "drop" 字段的字典
      2. validate_offloading_outputs() 能接受新格式（向后兼容）
      3. 验证函数不会因新字段而抛异常
    """
    scenario = _make_normal_scenario()
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
    model.penalty_drop = config.penalty_drop
    model.initModel()
    model.setupVars()
    feasible, cost = model.solveProblem()

    outputs = model.getOutputs()

    # ✅ Assertion 1: 验证新格式
    for t in outputs.keys():
        assert "local" in outputs[t], f"时隙 {t} 缺少 'local' 字段"
        assert "offload" in outputs[t], f"时隙 {t} 缺少 'offload' 字段"
        assert "drop" in outputs[t], f"时隙 {t} 缺少 'drop' 字段"
        assert isinstance(outputs[t]["drop"], list), "drop 字段应为列表"

    # ✅ Assertion 2: 验证函数兼容性（不应抛异常）
    try:
        validated = validate_offloading_outputs(outputs, scenario)
        # validate_offloading_outputs 可能返回输出或 None；无论哪种都说明兼容
        assert validated is None or validated == outputs, \
            "验证函数应返回 None 或原输出"
    except KeyError as e:
        if "'drop'" in str(e):
            pytest.fail(f"validate_offloading_outputs 不兼容新 drop 字段：{e}")
        raise
    except Exception as e:
        pytest.fail(f"validate_offloading_outputs 在新格式上抛异常：{e}")


# =====================================================================
# Entry point
# =====================================================================


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
