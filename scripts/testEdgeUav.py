"""Edge UAV entry script, parallel to testAll.py.

Usage:
    .venv/Scripts/python scripts/testEdgeUav.py

Environment variable override:
    HS_POP_SIZE=1 HS_ITERATION=1 .venv/Scripts/python scripts/testEdgeUav.py
"""

import os
from script_common import load_config, make_edge_uav_scenario, make_edge_uav_solver


def main():
    params = load_config()

    params.popSize = int(os.environ.get("HS_POP_SIZE", params.popSize))
    params.iteration = int(os.environ.get("HS_ITERATION", params.iteration))

    print(f"[testEdgeUav] model={params.llmModel}, endpoint={params.api_endpoint}")
    print(f"[testEdgeUav] popSize={params.popSize}, iteration={params.iteration}")

    if not params.api_key or not params.api_endpoint:
        raise RuntimeError(
            "LLM config missing. Check config/setting.cfg + config/env/.env"
        )

    scenario = make_edge_uav_scenario(params)

    hs = make_edge_uav_solver(params, scenario)
    hs.run()


if __name__ == "__main__":
    main()
