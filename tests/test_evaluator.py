"""EdgeUavEvaluator 测试 — 固定评估器的准确性与健壮性。

测试矩阵:
  T1 -- Test B outputs（混合卸载）: score > 0 且有限
  T2 -- 全本地 vs 混合卸载: all_local_score > mixed_score
  T3 -- Test D 独立性: solver alpha=0 → cost=0，但固定评估器 score > 0
  T4 -- 非法 outputs（缺失任务）: 返回 INVALID_OUTPUT_PENALTY

依赖: Gurobi 13.0+, edge_uav 包, config 包
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
from edge_uav.model.evaluator import evaluate_solution, INVALID_OUTPUT_PENALTY


# =====================================================================
# Fixture
# =====================================================================

@pytest.fixture
def scenario_bundle():
    """默认场景 (seed=42)。"""
    config = configPara(None, None)
    gen = EdgeUavScenarioGenerator()
    scenario = gen.getScenarioInfo(config)
    params = PrecomputeParams.from_config(config)
    return config, scenario, params


def _run_pipeline(scenario, params, *, alpha=1.0, gamma_w=1.0):
    """precompute + Level-1 BLP 求解。"""
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


def _make_all_local_outputs(scenario):
    """构造全本地 outputs：所有 active (i,t) 分配到 local。"""
    outputs = {}
    for t in scenario.time_slots:
        local_tasks = [
            i for i in scenario.tasks
            if scenario.tasks[i].active.get(t, False)
        ]
        outputs[t] = {
            "local": local_tasks,
            "offload": {j: [] for j in scenario.uavs},
        }
    return outputs


# =====================================================================
# T1 -- Test B outputs: score > 0 且有限
# =====================================================================

def test_t1_mixed_outputs_positive_score(scenario_bundle):
    """Test B 场景（tau=200, f_local=1e6）的优化解，评估分应 > 0 且有限。"""
    _config, scenario, params = scenario_bundle
    for task in scenario.tasks.values():
        task.tau = 200.0
        task.f_local = 1e6

    result, _model, feasible, _cost, outputs = _run_pipeline(scenario, params)
    assert feasible, "Test B should be feasible"

    score = evaluate_solution(outputs, result, scenario)
    assert score > 0, f"score should be positive, got {score}"
    assert score < INVALID_OUTPUT_PENALTY, f"score should be finite, got {score}"


# =====================================================================
# T2 -- 全本地 vs 混合卸载: all_local_score > mixed_score
# =====================================================================

def test_t2_all_local_worse_than_mixed(scenario_bundle):
    """全本地评分应高于（更差于）混合卸载评分。"""
    _config, scenario, params = scenario_bundle
    for task in scenario.tasks.values():
        task.tau = 200.0
        task.f_local = 1e6

    result, _model, feasible, _cost, mixed_outputs = _run_pipeline(scenario, params)
    assert feasible

    all_local_outputs = _make_all_local_outputs(scenario)

    mixed_score = evaluate_solution(mixed_outputs, result, scenario)
    all_local_score = evaluate_solution(all_local_outputs, result, scenario)

    assert all_local_score > mixed_score, (
        f"all_local ({all_local_score:.4f}) should be > "
        f"mixed ({mixed_score:.4f})"
    )


# =====================================================================
# T3 -- Test D 独立性: solver cost=0 但固定评估器 score > 0
# =====================================================================

def test_t3_evaluator_independent_of_solver_weights(scenario_bundle):
    """solver alpha=0 得到 cost~0（全本地无能耗），但固定评估器仍应 > 0。"""
    _config, scenario, params = scenario_bundle
    for task in scenario.tasks.values():
        task.tau = 200.0
        task.f_local = 1e6

    result, _model, feasible, cost, outputs = _run_pipeline(
        scenario, params, alpha=0.0, gamma_w=1.0,
    )
    assert feasible
    assert cost == pytest.approx(0.0, abs=1e-6), \
        f"solver cost should be ~0 with alpha=0, got {cost}"

    # 固定评估器用自己的权重(1,1)，不随 solver 漂移
    score = evaluate_solution(outputs, result, scenario)
    assert score > 0, (
        f"fixed evaluator should score > 0 even when solver cost=0, got {score}"
    )


# =====================================================================
# T4 -- 非法 outputs: 返回 INVALID_OUTPUT_PENALTY
# =====================================================================

def test_t4_invalid_outputs_penalty(scenario_bundle):
    """缺失活跃任务的 outputs 应返回大罚分。"""
    _config, scenario, params = scenario_bundle
    snap = make_initial_level2_snapshot(scenario)
    result = precompute_offloading_inputs(scenario, params, snap)

    # 构造一个空 outputs（所有 slot 都没分配任何任务）
    empty_outputs = {
        t: {"local": [], "offload": {j: [] for j in scenario.uavs}}
        for t in scenario.time_slots
    }

    score = evaluate_solution(empty_outputs, result, scenario)
    assert score == INVALID_OUTPUT_PENALTY, (
        f"empty outputs should get penalty {INVALID_OUTPUT_PENALTY}, got {score}"
    )


def test_t4b_missing_time_slot_penalty(scenario_bundle):
    """outputs 缺少时隙应返回大罚分。"""
    _config, scenario, params = scenario_bundle
    snap = make_initial_level2_snapshot(scenario)
    result = precompute_offloading_inputs(scenario, params, snap)

    # 完全空的 outputs
    score = evaluate_solution({}, result, scenario)
    assert score == INVALID_OUTPUT_PENALTY


# =====================================================================
# T5 -- 边界情况: 重复分配、类型错误、None 容器
# =====================================================================

def test_t5a_duplicate_assignment_penalty(scenario_bundle):
    """同一任务在同一时隙重复出现（local + offload）应返回大罚分。"""
    _config, scenario, params = scenario_bundle
    snap = make_initial_level2_snapshot(scenario)
    result = precompute_offloading_inputs(scenario, params, snap)

    # 找一个 active (i, t) 对
    active_i, active_t = None, None
    for i, task in scenario.tasks.items():
        for t in scenario.time_slots:
            if task.active.get(t, False):
                active_i, active_t = i, t
                break
        if active_i is not None:
            break

    # 构造 outputs：该任务同时在 local 和 offload 中
    first_uav = list(scenario.uavs.keys())[0]
    outputs = _make_all_local_outputs(scenario)
    outputs[active_t]["offload"][first_uav].append(active_i)

    score = evaluate_solution(outputs, result, scenario)
    assert score == INVALID_OUTPUT_PENALTY


def test_t5b_none_outputs_penalty(scenario_bundle):
    """outputs 为 None 或非 dict 应返回大罚分。"""
    _config, scenario, params = scenario_bundle
    snap = make_initial_level2_snapshot(scenario)
    result = precompute_offloading_inputs(scenario, params, snap)

    assert evaluate_solution(None, result, scenario) == INVALID_OUTPUT_PENALTY
    assert evaluate_solution("bad", result, scenario) == INVALID_OUTPUT_PENALTY
    assert evaluate_solution(42, result, scenario) == INVALID_OUTPUT_PENALTY


def test_t5c_inactive_assigned_penalty(scenario_bundle):
    """inactive 任务被分配应返回大罚分。"""
    _config, scenario, params = scenario_bundle
    snap = make_initial_level2_snapshot(scenario)
    result = precompute_offloading_inputs(scenario, params, snap)

    outputs = _make_all_local_outputs(scenario)

    # 找一个 inactive (i, t) 对，强行加入 local
    for i, task in scenario.tasks.items():
        for t in scenario.time_slots:
            if not task.active.get(t, False):
                outputs[t]["local"].append(i)
                score = evaluate_solution(outputs, result, scenario)
                assert score == INVALID_OUTPUT_PENALTY
                return

    pytest.skip("no inactive task-slot pair found")
