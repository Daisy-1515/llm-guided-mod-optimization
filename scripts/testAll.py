import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from config.config import configPara
from legacy_mod.scenarioGenerator import TaskGenerator
from heuristics.hsFrame import HarmonySearchSolver


def main():
    params = configPara("./config/setting.cfg", "./config/env/.env")
    params.getConfigInfo()

    scenario = TaskGenerator()
    scenario_info = scenario.getScenarioInfo(params)

    hs = HarmonySearchSolver(params, scenario_info)
    hs.run()


if __name__ == "__main__":
    main()
