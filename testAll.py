
from config.config import configPara
from scenarioGenerator import TaskGenerator
from heuristics.hsFrame import HarmonySearchSolver

if __name__ == "__main__":
    params = configPara("./config/setting.cfg",
                        "./config/env/.env")
    params.getConfigInfo()
    
    scenario = TaskGenerator()
    scenarioInfo = scenario.getScenarioInfo(params)
    
    hs = HarmonySearchSolver(params, scenarioInfo)
    hs.run()
    