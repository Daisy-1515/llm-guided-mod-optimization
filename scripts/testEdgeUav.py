"""Edge UAV entry script, parallel to testAll.py.

Usage:
    .venv/Scripts/python scripts/testEdgeUav.py

Environment variable override:
    HS_POP_SIZE=1 HS_ITERATION=1 .venv/Scripts/python scripts/testEdgeUav.py
"""

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from config.config import configPara
from edge_uav.scenario_generator import EdgeUavScenarioGenerator
from heuristics.hsFrame import HarmonySearchSolver


def main():
    params = configPara(None, None)
    params.getConfigInfo()

    params.popSize = int(os.environ.get("HS_POP_SIZE", params.popSize))
    params.iteration = int(os.environ.get("HS_ITERATION", params.iteration))

    print(f"[testEdgeUav] model={params.llmModel}, endpoint={params.api_endpoint}")
    print(f"[testEdgeUav] popSize={params.popSize}, iteration={params.iteration}")

    if not params.api_key or not params.api_endpoint:
        raise RuntimeError(
            "LLM config missing. Check config/setting.cfg + config/env/.env"
        )

    gen = EdgeUavScenarioGenerator()
    scenario = gen.getScenarioInfo(params)

    hs = HarmonySearchSolver(params, scenario, individual_type="edge_uav")
    hs.pop.timeout = 600
    hs.run()


if __name__ == "__main__":
    main()
