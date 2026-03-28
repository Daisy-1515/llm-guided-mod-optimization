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
from edge_uav.model.precompute import make_initial_level2_snapshot
from edge_uav.scenario_generator import EdgeUavScenarioGenerator
from edge_uav.model.bcd_loop import BCDResult
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


def test_t4_bcd_recomputes_precompute_for_scoring(scenario_bundle, monkeypatch):
    """BCD 路径评分应基于最终 snapshot 的重计算结果，而不是初始化 precompute。"""
    config, scenario = scenario_bundle
    config.use_bcd_loop = True

    ind = hsIndividualEdgeUav(config, scenario)
    initial_precompute = ind.precompute_result
    final_precompute = type(
        "FakePrecompute",
        (),
        {"diagnostics": {"offload_feasible_ratio": 0.5}},
    )()

    def fake_run_bcd_loop(**kwargs):
        outputs = {t: {"local": [], "offload": {j: [] for j in scenario.uavs}} for t in scenario.time_slots}
        return BCDResult(
            snapshot=make_initial_level2_snapshot(scenario),
            offloading_outputs=outputs,
            total_cost=12.34,
            bcd_iterations=2,
            converged=True,
            cost_history=[12.34, 12.34],
            solution_details={},
        )

    def fake_precompute_offloading_inputs(*args, **kwargs):
        return final_precompute

    captured = {}

    def fake_evaluate_solution(outputs, precompute_result, scenario_arg):
        captured["precompute_result"] = precompute_result
        assert scenario_arg is scenario
        return 7.89

    monkeypatch.setattr("heuristics.hsIndividualEdgeUav.run_bcd_loop", fake_run_bcd_loop)
    monkeypatch.setattr(
        "heuristics.hsIndividualEdgeUav.precompute_offloading_inputs",
        fake_precompute_offloading_inputs,
    )
    monkeypatch.setattr(
        "heuristics.hsIndividualEdgeUav.evaluate_solution",
        fake_evaluate_solution,
    )

    ind.runOptModel("", "default")

    assert captured["precompute_result"] is not initial_precompute
    assert ind.promptHistory["evaluation_score"] == pytest.approx(7.89)
    step = ind.promptHistory["simulation_steps"]["0"]
    assert step["final_precompute_diagnostics"]["offload_feasible_ratio"] == 0.5


def test_t5_bcd_logs_solver_status_consistently(scenario_bundle, monkeypatch):
    """BCD 成功路径应使用 BCDResult 携带的 solver 状态，而不是伪造默认目标日志。"""
    config, scenario = scenario_bundle
    config.use_bcd_loop = True

    ind = hsIndividualEdgeUav(config, scenario)

    def fake_run_bcd_loop(**kwargs):
        outputs = {
            t: {"local": [], "offload": {j: [] for j in scenario.uavs}}
            for t in scenario.time_slots
        }
        return BCDResult(
            snapshot=make_initial_level2_snapshot(scenario),
            offloading_outputs=outputs,
            total_cost=12.34,
            bcd_iterations=2,
            converged=True,
            cost_history=[12.34, 12.34],
            solution_details={},
            offloading_error_message="Your obj function is correct. Gurobi accepts your obj.",
            used_default_obj=False,
            objective_acceptance_status="accepted_custom_obj",
        )

    fake_precompute = type(
        "FakePrecompute",
        (),
        {"diagnostics": {"offload_feasible_ratio": 0.5}},
    )()

    monkeypatch.setattr("heuristics.hsIndividualEdgeUav.run_bcd_loop", fake_run_bcd_loop)
    monkeypatch.setattr(
        ind,
        "getNewPrompt",
        lambda parent, way: (
            '{"obj_code": "def dynamic_obj_func(self):\\n    return None"}',
            {
                "task_info": "task",
                "uav_info": "uav",
                "llm_response": '{"obj_code": "def dynamic_obj_func(self):\\n    return None"}',
                "raw_llm_response": '{"obj_code": "def dynamic_obj_func(self):\\n    return None"}',
                "response_format": "",
                "feasible": False,
                "solver_cost": float(INVALID_OUTPUT_PENALTY),
                "used_default_obj": False,
                "llm_status": "ok",
                "llm_error": None,
            },
        ),
    )
    monkeypatch.setattr(
        "heuristics.hsIndividualEdgeUav.precompute_offloading_inputs",
        lambda *args, **kwargs: fake_precompute,
    )
    monkeypatch.setattr(
        "heuristics.hsIndividualEdgeUav.evaluate_solution",
        lambda *args, **kwargs: 7.89,
    )
    monkeypatch.setattr(
        "heuristics.hsIndividualEdgeUav.extract_code_hsIndiv",
        lambda response: "def dynamic_obj_func(self):\n    return None",
    )

    ind.runOptModel("", "way1")

    step = ind.promptHistory["simulation_steps"]["0"]
    assert step["llm_status"] == "ok"
    assert step["used_default_obj"] is False
    assert step["response_format"] == "Your obj function is correct. Gurobi accepts your obj."
    assert step["bcd_meta"]["objective_acceptance_status"] == "accepted_custom_obj"
