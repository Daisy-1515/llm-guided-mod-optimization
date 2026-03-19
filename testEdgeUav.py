"""Edge UAV 入口脚本 — 与 testAll.py 平行。

用法:
    .venv/Scripts/python testEdgeUav.py
"""

from config.config import configPara
from edge_uav.scenario_generator import EdgeUavScenarioGenerator
from heuristics.hsFrame import HarmonySearchSolver

if __name__ == "__main__":
    params = configPara(None, None)
    params.getConfigInfo()

    # 试跑参数覆盖
    params.popSize = 3
    params.iteration = 3

    # 启动前诊断
    print(f"[testEdgeUav] model={params.llmModel}, endpoint={params.api_endpoint}")
    print(f"[testEdgeUav] popSize={params.popSize}, iteration={params.iteration}")

    if not params.api_key or not params.api_endpoint:
        raise RuntimeError(
            "LLM config missing. Check config/setting.cfg + config/env/.env"
        )

    gen = EdgeUavScenarioGenerator()
    scenario = gen.getScenarioInfo(params)

    # 放宽 tau 确保默认参数下 BLP 可行
    for task in scenario.tasks.values():
        task.tau = 200.0
        task.f_local = 1e6

    hs = HarmonySearchSolver(params, scenario, individual_type="edge_uav")
    hs.run()
