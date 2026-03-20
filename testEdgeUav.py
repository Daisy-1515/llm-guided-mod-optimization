"""Edge UAV 入口脚本 — 与 testAll.py 平行。

用法:
    .venv/Scripts/python testEdgeUav.py

环境变量覆盖（用于 D2/D3 阶梯预飞）:
    HS_POP_SIZE=1 HS_ITERATION=1 .venv/Scripts/python testEdgeUav.py
"""

import os

from config.config import configPara
from edge_uav.scenario_generator import EdgeUavScenarioGenerator
from heuristics.hsFrame import HarmonySearchSolver

if __name__ == "__main__":
    params = configPara(None, None)
    params.getConfigInfo()

    # 试跑参数覆盖（默认值 → 环境变量覆盖）
    params.popSize = 3
    params.iteration = 3
    params.popSize = int(os.environ.get("HS_POP_SIZE", params.popSize))
    params.iteration = int(os.environ.get("HS_ITERATION", params.iteration))

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
    hs.pop.timeout = 600  # 给 LLM 120s×3 retries 足够的 executor 等待时间
    hs.run()
