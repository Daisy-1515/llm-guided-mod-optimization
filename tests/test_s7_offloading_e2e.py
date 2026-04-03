"""S7 端到端测试 — precompute -> OffloadingModel 全链路联调。

覆盖四个场景:
  Test A -- 退化路径: 默认参数, 全本地执行 (回归测试)
  Test B -- 卸载激活: 放宽 tau + 降低 f_local, 优化器选择卸载
  Test C -- 混合决策: 部分任务本地 + 部分卸载, 验证共存
  Test D -- 能耗驱动: alpha=0, gamma_w=1, 纯能耗目标强制全本地回退

依赖: Gurobi 13.0+, edge_uav 包, config 包
场景固定: seed=42, 10 tasks, 3 UAVs, 20 time slots
"""

import pytest

pytest.importorskip("gurobipy")

from config.config import configPara
from edge_uav.scenario_generator import EdgeUavScenarioGenerator
from edge_uav.model.precompute import (
    PrecomputeParams,
    make_initial_level2_snapshot,
    precompute_offloading_inputs,
)
from edge_uav.model.offloading import OffloadingModel


# =====================================================================
# Fixture
# =====================================================================

@pytest.fixture
def scenario_bundle():
    """默认场景 (seed=42): 每次调用生成新实例, 测试间互不影响。"""
    config = configPara(None, None)
    gen = EdgeUavScenarioGenerator()
    scenario = gen.getScenarioInfo(config)
    params = PrecomputeParams.from_config(config)
    return config, scenario, params


# =====================================================================
# Helpers
# =====================================================================

def _run_pipeline(scenario, params, *, alpha=1.0, gamma_w=1.0):
    """预计算 + Level-1 BLP 求解的便捷封装。

    Returns:
        (precompute_result, model, feasible, cost, outputs)
    """
    snap = make_initial_level2_snapshot(scenario)
    result = precompute_offloading_inputs(scenario, params, snap)
    model = OffloadingModel(
        tasks=scenario.tasks,
        uavs=scenario.uavs,
        time_list=scenario.time_slots,
        D_hat_local=result.D_hat_local,
        D_hat_offload=result.D_hat_offload,
        E_hat_comp=result.E_hat_comp,
        alpha=alpha,
        gamma_w=gamma_w,
    )
    feasible, cost = model.solveProblem()
    outputs = model.getOutputs()
    return result, model, feasible, cost, outputs


def _offloaded_triples(outputs):
    """从 outputs 提取所有被卸载的 (i, j, t) 三元组。"""
    return [
        (i, j, t)
        for t, slot in outputs.items()
        for j, task_ids in slot["offload"].items()
        for i in task_ids
    ]


def _local_count(outputs):
    """统计本地执行的任务-时隙对数。"""
    return sum(len(slot["local"]) for slot in outputs.values())


def _task_count(scenario):
    """统计场景中活跃 (i, t) 对数。"""
    return sum(
        1 for i, task in scenario.tasks.items()
        for t in scenario.time_slots
        if task.active.get(t, False)
    )


def _all_local_cost(result, scenario):
    """假设全本地执行时的归一化时延总成本 (alpha=1)，对所有活跃 (i,t) 求和。"""
    return sum(
        result.D_hat_local[i][t] / scenario.tasks[i].tau
        for i, task in scenario.tasks.items()
        for t in scenario.time_slots
        if task.active.get(t, False)
    )


# =====================================================================
# Test A -- 退化路径 (默认参数, 全本地执行)
# =====================================================================

def test_a_baseline_all_local(scenario_bundle):
    """默认参数下 tau 偏紧 (0.5-2s), 无可卸载候选, 全部本地。

    断言:
      A1. 求解可行
      A2. 总成本 > 0
      A3. 所有活跃任务分配到本地
      A4. 无卸载发生
    """
    _config, scenario, params = scenario_bundle
    result, _model, feasible, cost, outputs = _run_pipeline(scenario, params)

    # A1
    assert feasible, "should be feasible with all-local fallback"
    # A2
    assert cost > 0, f"cost should be positive, got {cost}"
    # A2.5: 退化路径原因 — 无可卸载候选 (tau 偏紧, offload 全不可行)
    assert result.diagnostics["offload_feasible_ratio"] == 0.0, \
        f"degenerate path: offload_feasible_ratio should be 0, " \
        f"got {result.diagnostics['offload_feasible_ratio']}"
    # A3
    n_tasks = _task_count(scenario)
    n_local = _local_count(outputs)
    assert n_local == n_tasks, f"expected {n_tasks} local, got {n_local}"
    # A4
    offloaded = _offloaded_triples(outputs)
    assert len(offloaded) == 0, f"expected 0 offloaded, got {len(offloaded)}"


# =====================================================================
# Test B -- 卸载激活 (放宽 tau + 降低 f_local)
# =====================================================================

def test_b_offloading_activates(scenario_bundle):
    """tau=200 + f_local=1e6 使卸载可行且更优。

    断言:
      B1. 求解可行
      B2. 预计算阶段存在可卸载候选 (offload_feasible_ratio > 0)
      B3. Gurobi 实际选择了卸载 (至少 1 个)
      B4. 所有被选中的卸载对满足 deadline (D_offload <= tau)
      B5. 优化后总成本 < 全本地基线成本
    """
    _config, scenario, params = scenario_bundle
    for task in scenario.tasks.values():
        task.tau = 200.0
        task.f_local = 1e6

    result, _model, feasible, cost, outputs = _run_pipeline(scenario, params)

    # B1
    assert feasible, "should be feasible with relaxed tau"
    # B2
    assert result.diagnostics["offload_feasible_ratio"] > 0, \
        "offload_feasible_ratio should be > 0"
    assert result.diagnostics["deadline_feasible_pairs"] > 0, \
        "deadline_feasible_pairs should be > 0"
    # B3
    offloaded = _offloaded_triples(outputs)
    assert len(offloaded) > 0, "at least one task should be offloaded"
    # B4: 仅断言卸载决策 (本地无硬性 deadline 约束)
    for i, j, t in offloaded:
        assert result.D_hat_offload[i][j][t] <= scenario.tasks[i].tau, (
            f"offloaded ({i},{j},{t}): "
            f"D={result.D_hat_offload[i][j][t]:.2f} > tau={scenario.tasks[i].tau}"
        )
    # B5
    baseline = _all_local_cost(result, scenario)
    assert cost < baseline, \
        f"optimized {cost:.4f} should be < all-local baseline {baseline:.4f}"


# =====================================================================
# Test C -- 混合决策 (部分本地 + 部分卸载)
# =====================================================================

def test_c_mixed_decisions(scenario_bundle):
    """前半任务 f_local=1e9 (本地优), 后半 f_local=1e6 (卸载优)。

    断言:
      C1. 求解可行
      C2. 本地执行和卸载执行同时存在
      C3. 总分配数 == 活跃对数 (无遗漏)
    """
    _config, scenario, params = scenario_bundle
    task_ids = sorted(scenario.tasks.keys())
    mid = len(task_ids) // 2

    for idx, i in enumerate(task_ids):
        scenario.tasks[i].tau = 200.0
        if idx < mid:
            scenario.tasks[i].f_local = 1e9   # 本地时延小, 本地优
        else:
            scenario.tasks[i].f_local = 1e6    # 本地时延大, 卸载优

    result, _model, feasible, cost, outputs = _run_pipeline(scenario, params)

    # C1
    assert feasible, "mixed scenario should be feasible"
    # C2
    n_local = _local_count(outputs)
    offloaded = _offloaded_triples(outputs)
    assert n_local > 0, "should have at least one local decision"
    assert len(offloaded) > 0, "should have at least one offload decision"
    # C3
    n_tasks = _task_count(scenario)
    assert n_local + len(offloaded) == n_tasks, \
        f"total {n_local + len(offloaded)} != tasks {n_tasks}"


# =====================================================================
# Test D -- 能耗驱动回退 (alpha=0, gamma_w=1)
# =====================================================================

def test_d_energy_weight_all_local(scenario_bundle):
    """纯能耗目标: alpha=0 消除时延项, 本地无边缘能耗 -> 全本地最优。

    断言:
      D1. 求解可行
      D2. 无卸载发生 (全本地)
      D3. 目标值 == 0 (本地执行不产生边缘能耗)
    """
    _config, scenario, params = scenario_bundle
    for task in scenario.tasks.values():
        task.tau = 200.0
        task.f_local = 1e6

    result, _model, feasible, cost, outputs = _run_pipeline(
        scenario, params, alpha=0.0, gamma_w=1.0,
    )

    # D1
    assert feasible, "should be feasible"
    # D2
    offloaded = _offloaded_triples(outputs)
    assert len(offloaded) == 0, \
        f"with alpha=0 gamma_w=1, should be all-local, got {len(offloaded)} offloaded"
    # D3
    assert cost == pytest.approx(0.0, abs=1e-6), \
        f"all-local with alpha=0 should give cost~0, got {cost}"
