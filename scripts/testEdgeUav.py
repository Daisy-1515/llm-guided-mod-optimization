"""Edge UAV 入口脚本，功能与 testAll.py 对应。

用法:
    .venv/Scripts/python scripts/testEdgeUav.py

环境变量覆盖 (Override):
    HS_POP_SIZE=1 HS_ITERATION=1 .venv/Scripts/python scripts/testEdgeUav.py
"""

import os
from script_common import load_config, make_edge_uav_scenario, make_edge_uav_solver


def main():
    # 加载基础配置（包括 LLM、算法参数、场景参数等）
    params = load_config()

    # 通过环境变量覆盖和更新 HS 算法的核心参数，便于快速实验
    params.popSize = int(os.environ.get("HS_POP_SIZE", params.popSize))
    params.iteration = int(os.environ.get("HS_ITERATION", params.iteration))

    print(f"[testEdgeUav] model={params.llmModel}, endpoint={params.api_endpoint}")
    print(f"[testEdgeUav] popSize={params.popSize}, iteration={params.iteration}")

    # 检查 LLM API 相关的关键配置是否完整
    if not params.api_key or not params.api_endpoint:
        raise RuntimeError(
            "LLM 配置缺失。请检查 config/setting.cfg 以及 config/env/.env 文件"
        )

    # 根据配置构造 Edge UAV 仿真场景实例
    scenario = make_edge_uav_scenario(params)

    # 初始化 Harmony Search (HS) 求解器（针对 Edge UAV 定制的个体类型）并开始运行
    hs = make_edge_uav_solver(params, scenario)
    hs.run()


if __name__ == "__main__":
    main()