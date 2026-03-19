"""Edge UAV 入口脚本 — 与 testAll.py 平行。

用法:
    .venv/Scripts/python testEdgeUav.py
"""

from config.config import configPara
from edge_uav.scenario_generator import EdgeUavScenarioGenerator
from heuristics.hsFrame import HarmonySearchSolver

if __name__ == "__main__":
    params = configPara(None, None)

    gen = EdgeUavScenarioGenerator()
    scenario = gen.getScenarioInfo(params)

    # 放宽 tau 确保默认参数下 BLP 可行
    for task in scenario.tasks.values():
        task.tau = 200.0
        task.f_local = 1e6

    hs = HarmonySearchSolver(params, scenario, individual_type="edge_uav")
    hs.run()
