"""hsIndividualEdgeUav 测试 — Phase④-S2 验收。

测试矩阵:
  T1 -- runOptModel("", "default"): score > 0 且 < INVALID_OUTPUT_PENALTY
  T2 -- shrink_token_size 兼容性: 不崩溃 + "def dynamic_obj_func" 保留
  T3 -- format_scenario_info: 返回 (str, str) 含关键字段

依赖: Gurobi 13.0+, edge_uav 包, config 包
"""

import json

import pytest

pytest.importorskip("gurobipy")

from config.config import configPara
from edge_uav.model.evaluator import INVALID_OUTPUT_PENALTY
from edge_uav.scenario_generator import EdgeUavScenarioGenerator
from heuristics.hsIndividualEdgeUav import hsIndividualEdgeUav
from heuristics.hsPopulation import hsPopulation


# =====================================================================
# Fixture
# =====================================================================

@pytest.fixture
def scenario_bundle():
    """宽松 tau 场景，确保 BLP 可行。"""
    config = configPara(None, None)
    gen = EdgeUavScenarioGenerator()
    scenario = gen.getScenarioInfo(config)
    # 放宽 tau 确保可行
    for task in scenario.tasks.values():
        task.tau = 200.0
        task.f_local = 1e6
    return config, scenario


# =====================================================================
# T1 -- runOptModel default: score 有效
# =====================================================================

def test_t1_default_run_valid_score(scenario_bundle):
    """default 路由（无 LLM）应产出有效评分和完整 promptHistory。"""
    config, scenario = scenario_bundle
    ind = hsIndividualEdgeUav(config, scenario)
    ind.runOptModel("", "default")

    ph = ind.promptHistory
    score = ph["evaluation_score"]

    # 评分有效
    assert score is not None
    assert score > 0, f"score should be > 0, got {score}"
    assert score < INVALID_OUTPUT_PENALTY, f"score should be < penalty, got {score}"

    # simulation_steps 结构完整
    step = ph["simulation_steps"]["0"]
    assert isinstance(step["task_info"], str)
    assert isinstance(step["uav_info"], str)
    assert step["feasible"] is True
    assert step["used_default_obj"] is True
    assert step["raw_llm_response"] is None

    # llm_response 可 json.loads 且含 obj_code
    parsed = json.loads(step["llm_response"])
    assert "obj_code" in parsed
    assert "def dynamic_obj_func" in parsed["obj_code"]


# =====================================================================
# T2 -- shrink_token_size 兼容性
# =====================================================================

def test_t2_shrink_token_size_compatible(scenario_bundle):
    """shrink_token_size 处理后应保留 evaluation_score 和有效代码。"""
    config, scenario = scenario_bundle
    ind = hsIndividualEdgeUav(config, scenario)
    ind.runOptModel("", "default")

    pop = hsPopulation(config, scenario)
    shrinked = pop.shrink_token_size(ind.promptHistory)

    # evaluation_score 保留
    assert shrinked["evaluation_score"] == ind.promptHistory["evaluation_score"]

    # shrink 后 llm_response 应含 "def dynamic_obj_func"
    step = shrinked["simulation_steps"]["0"]
    assert "def dynamic_obj_func" in step["llm_response"]

    # response_format 保留
    assert isinstance(step["response_format"], str)
    assert step["response_format"] != ""


# =====================================================================
# T3 -- format_scenario_info 内容检查
# =====================================================================

def test_t3_format_scenario_info(scenario_bundle):
    """format_scenario_info 应返回包含关键信息的字符串对。"""
    config, scenario = scenario_bundle
    ind = hsIndividualEdgeUav(config, scenario)

    task_info, uav_info = ind.format_scenario_info()

    assert isinstance(task_info, str)
    assert isinstance(uav_info, str)

    # 关键字段存在
    assert "Task" in task_info
    assert "active_slots" in task_info
    assert "UAV" in uav_info
    assert "E_max" in uav_info
