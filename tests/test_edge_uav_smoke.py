"""Phase④-S5 单个体 smoke test — LLM API 不可用时回退 default 目标函数。

测试矩阵:
  T1 -- get_init_ind() 返回有效 promptHistory（way1 → API 失败 → 回退 default obj）
  T2 -- sort_population 正确升序排列
  T3 -- generate_new_harmony() 能产出 way1/way2/way3/way4 全路由，且返回 scalar

依赖: Gurobi 13.0+, edge_uav 包
"""

import random

import pytest

pytest.importorskip("gurobipy")

from config.config import configPara
from edge_uav.model.evaluator import INVALID_OUTPUT_PENALTY
from edge_uav.scenario_generator import EdgeUavScenarioGenerator
from heuristics.hsPopulation import hsPopulation
from heuristics.hsSorting import hsSorting


# =====================================================================
# Fixture
# =====================================================================

@pytest.fixture
def edge_uav_bundle():
    """宽松 tau 场景 + Edge UAV 种群管理器。"""
    config = configPara(None, None)
    gen = EdgeUavScenarioGenerator()
    scenario = gen.getScenarioInfo(config)
    for task in scenario.tasks.values():
        task.tau = 200.0
        task.f_local = 1e6
    pop = hsPopulation(config, scenario, individual_type="edge_uav")
    return config, scenario, pop


# =====================================================================
# T1 -- get_init_ind 返回有效 promptHistory
# =====================================================================

def test_t1_get_init_ind_valid(edge_uav_bundle):
    """get_init_ind 应产出包含 evaluation_score 和 simulation_steps 的字典。"""
    _, _, pop = edge_uav_bundle
    ph = pop.get_init_ind()

    assert isinstance(ph, dict)
    assert "evaluation_score" in ph
    assert "simulation_steps" in ph

    score = ph["evaluation_score"]
    assert score is not None
    assert score > 0
    assert score < INVALID_OUTPUT_PENALTY

    # Edge UAV 只有 step "0"
    assert "0" in ph["simulation_steps"]
    step = ph["simulation_steps"]["0"]
    assert isinstance(step["task_info"], str)
    assert isinstance(step["uav_info"], str)


# =====================================================================
# T2 -- sort_population 正确升序排列
# =====================================================================

def test_t2_sort_population(edge_uav_bundle):
    """sort_population 应按 evaluation_score 升序返回前 popsize 个体。"""
    _, _, pop = edge_uav_bundle

    ph1 = pop.get_init_ind()
    ph2 = pop.get_init_ind()

    # 人为设置不同分数
    ph1["evaluation_score"] = 100.0
    ph2["evaluation_score"] = 50.0

    sorter = hsSorting()
    sorted_pop = sorter.sort_population([ph1, ph2], 2)

    assert len(sorted_pop) == 2
    assert sorted_pop[0]["evaluation_score"] <= sorted_pop[1]["evaluation_score"]
    assert sorted_pop[0]["evaluation_score"] == 50.0


# =====================================================================
# T3 -- generate_new_harmony 能产出 way4
# =====================================================================

def test_t3_generate_new_harmony_way4(edge_uav_bundle):
    """PAR 分支在 Edge UAV 模式下应能产出 way3 或 way4。"""
    _, _, pop = edge_uav_bundle

    # 构造最小种群（2 个体）用于 harmony 生成
    ph1 = pop.get_init_ind()
    ph2 = pop.get_init_ind()
    ph1["evaluation_score"] = 50.0
    ph2["evaluation_score"] = 100.0
    mini_pop = [ph1, ph2]

    # 多次采样，检查所有路由至少出现一次
    seen_ways = set()
    random.seed(42)
    for _ in range(200):
        p, w, parent_snapshot = pop.generate_new_harmony(mini_pop)
        # Edge UAV 返回 scalar（非 list）
        assert isinstance(w, str), f"Expected scalar way, got {type(w)}"
        assert not isinstance(p, list), f"Expected scalar parent, got list"
        # parent_snapshot 可以是 None（如果 BCD 禁用或初始化失败）
        assert parent_snapshot is None or hasattr(parent_snapshot, '__dict__'), f"Unexpected parent_snapshot type: {type(parent_snapshot)}"
        seen_ways.add(w)

    # way1（HMCR 外）、way2（PAR 外）、way3/way4（PAR 内）都应出现
    assert "way1" in seen_ways, f"way1 not seen in {seen_ways}"
    assert "way2" in seen_ways, f"way2 not seen in {seen_ways}"
    assert "way3" in seen_ways, f"way3 not seen in {seen_ways}"
    assert "way4" in seen_ways, f"way4 not seen in {seen_ways}"
