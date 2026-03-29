from script_common import load_config
from legacy_mod.scenarioGenerator import TaskGenerator
from heuristics.hsFrame import HarmonySearchSolver


def main():
    params = load_config("./config/setting.cfg", "./config/env/.env")

    scenario = TaskGenerator()
    scenario_info = scenario.getScenarioInfo(params)

    hs = HarmonySearchSolver(params, scenario_info)
    hs.run()


if __name__ == "__main__":
    main()
