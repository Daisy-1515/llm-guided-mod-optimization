"""Phase④-S6 小规模 HS 集成测试 — 3 个体 × 2 代。

测试内容:
  T1 -- initialize_population 产出 3 个有效个体
  T2 -- sort + generate_new_population + 合并排序 完整循环
  T3 -- 2 代后最优评分非递增（最优不退化）
  T4 -- save_population 输出合法 JSON

LLM API 不可用时自动回退 default 目标函数，全程不依赖外部服务。
依赖: Gurobi 13.0+, edge_uav 包
"""

import json
import os
import tempfile

import pytest

pytest.importorskip("gurobipy")

from config.config import configPara
from edge_uav.model.evaluator import INVALID_OUTPUT_PENALTY
from edge_uav.scenario_generator import EdgeUavScenarioGenerator
from heuristics.hsFrame import HarmonySearchSolver
from heuristics.hsPopulation import hsPopulation
from heuristics.hsSorting import hsSorting


# =====================================================================
# Fixture
# =====================================================================

@pytest.fixture
def hs_bundle():
    """3 个体、2 代的 Edge UAV HS 配置。"""
    config = configPara(None, None)
    config.popSize = 3
    config.iteration = 2
    gen = EdgeUavScenarioGenerator()
    scenario = gen.getScenarioInfo(config)
    for task in scenario.tasks.values():
        task.tau = 200.0
        task.f_local = 1e6
    return config, scenario


# =====================================================================
# T1 -- initialize_population 产出有效个体
# =====================================================================

def test_t1_initialize_population(hs_bundle):
    """initialize_population 应返回 popsize 个有效 promptHistory。"""
    config, scenario = hs_bundle
    pop = hsPopulation(config, scenario, individual_type="edge_uav")
    individuals = pop.initialize_population()

    assert len(individuals) == config.popSize
    for ph in individuals:
        assert isinstance(ph, dict)
        assert ph["evaluation_score"] is not None
        assert ph["evaluation_score"] > 0
        assert ph["evaluation_score"] < INVALID_OUTPUT_PENALTY
        assert "0" in ph["simulation_steps"]


# =====================================================================
# T2 -- sort + generate_new + 合并排序
# =====================================================================

def test_t2_sort_generate_merge(hs_bundle):
    """完整的 sort → generate → merge → sort 循环应不报错。"""
    config, scenario = hs_bundle
    pop = hsPopulation(config, scenario, individual_type="edge_uav")
    sorter = hsSorting()

    # 初始化
    individuals = pop.initialize_population()
    sorted_pop = sorter.sort_population(individuals, config.popSize)
    assert len(sorted_pop) == config.popSize

    # 生成新一代
    new_pop = pop.generate_new_population(sorted_pop)
    assert len(new_pop) == config.popSize

    # 合并排序
    combined = sorted_pop + new_pop
    final_pop = sorter.sort_population(combined, config.popSize)
    assert len(final_pop) == config.popSize

    # 升序验证
    scores = [ph["evaluation_score"] for ph in final_pop]
    assert scores == sorted(scores)


# =====================================================================
# T3 -- 2 代后最优不退化
# =====================================================================

def test_t3_best_score_non_degrading(hs_bundle):
    """经过 2 代后，最优个体评分应 <= 初始最优。"""
    config, scenario = hs_bundle
    pop = hsPopulation(config, scenario, individual_type="edge_uav")
    sorter = hsSorting()

    sorted_pop = sorter.sort_population(pop.initialize_population(), config.popSize)
    best_init = sorted_pop[0]["evaluation_score"]

    for _ in range(config.iteration - 1):
        new_pop = pop.generate_new_population(sorted_pop)
        combined = sorted_pop + new_pop
        sorted_pop = sorter.sort_population(combined, config.popSize)

    best_final = sorted_pop[0]["evaluation_score"]
    assert best_final <= best_init


# =====================================================================
# T4 -- save_population 输出合法 JSON
# =====================================================================

def test_t4_save_population_json(hs_bundle, tmp_path, monkeypatch):
    """HarmonySearchSolver.save_population 应输出可解析的 JSON。"""
    config, scenario = hs_bundle

    # 将 discussion 目录重定向到临时目录
    monkeypatch.chdir(tmp_path)

    solver = HarmonySearchSolver(config, scenario, individual_type="edge_uav")
    pop_mgr = solver.pop
    individuals = pop_mgr.initialize_population()
    sorted_pop = solver.sort.sort_population(individuals, config.popSize)

    solver.save_population(sorted_pop, 0)

    json_path = tmp_path / solver.out_dir / "population_result_0.json"
    assert json_path.exists()

    with open(json_path) as f:
        data = json.load(f)
    assert isinstance(data, list)
    assert len(data) == config.popSize
