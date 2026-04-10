"""
edge_uav/prompt/traj_prompt.py

Level-2b 轨迹优化目标函数的 LLM Prompt 生成器。

与 Level-1 (L1) 不同：
  - L1: LLM 生成 Gurobi BLP 目标函数（整数决策变量）
  - L2b: LLM 生成 CVXPY 轨迹目标权重策略（连续决策变量）

LLM 生成的代码通过修改 obj_comm_surrogate / obj_propulsion 的
线性组合权重，引导 UAV 轨迹在通信质量与飞行能耗之间找到更好的平衡点。
"""

import json


_TRAJ_DEFAULT_CODE = (
    "# Default: equal weighting\n"
    "dynamic_traj_objective = alpha * obj_comm_surrogate + lambda_w * obj_propulsion + obj_slack"
)


class TrajectoryPrompts:
    """L2b 轨迹优化 LLM Prompt 生成器。

    Parameters
    ----------
    scenario_stats : dict
        场景统计信息，包含：
          - N_act: int  活跃卸载对数（L1 决定）
          - N_fly: int  UAV 移动段数 = n_uavs × (T-1)
          - n_uavs: int
          - n_tasks_active: int
          - alpha: float  当前时延权重（来自 config）
          - lambda_w: float  当前飞行能耗权重（来自 config）
    """

    def __init__(self, scenario_stats: dict):
        self._stats = scenario_stats

    # ------------------------------------------------------------------
    # 公共接口
    # ------------------------------------------------------------------

    def get_prompt(self, way: str, best_traj_code: str | None = None) -> str:
        """按 way 类型生成 L2b prompt。

        Parameters
        ----------
        way : str
            "way1" / "way2" / "way3"（其余回退到 way1）
        best_traj_code : str | None
            当前最优个体的 traj_obj_code（way2/3 使用）
        """
        if way == "way2" and best_traj_code:
            return self._prompt_way2(best_traj_code)
        if way == "way3" and best_traj_code:
            return self._prompt_way3(best_traj_code)
        return self._prompt_way1()

    # ------------------------------------------------------------------
    # 内部实现
    # ------------------------------------------------------------------

    def _header(self) -> str:
        s = self._stats
        return (
            "=== Edge-UAV Level-2b Trajectory Optimization ===\n\n"
            "## Background\n"
            "You are designing the objective function for a UAV trajectory optimizer.\n"
            "The optimizer uses Successive Convex Approximation (SCA) to find UAV positions\n"
            "over T time slots that minimize a weighted combination of:\n"
            "  1. Communication delay  — how long it takes to upload/download task data\n"
            "     (UAVs closer to their assigned tasks → lower delay)\n"
            "  2. Propulsion energy    — energy spent flying the UAVs\n"
            "     (UAVs moving more → higher energy)\n\n"
            "## Pre-computed objective components (already normalized)\n"
            "These are CVXPY expressions. You MUST NOT call any CVXPY methods on them;\n"
            "only multiply them by positive Python float coefficients.\n\n"
            "  obj_comm_surrogate  : convex surrogate for total normalized communication delay\n"
            "                        (smaller → UAVs are closer to tasks → better offloading)\n"
            "  obj_propulsion      : total normalized propulsion energy across all UAVs\n"
            "                        (smaller → UAVs move less)\n"
            "  obj_slack           : constraint violation penalty (MUST always be included)\n\n"
            "## Available scalar parameters\n"
            f"  alpha     = {s.get('alpha', 1.0):.4g}   (delay weight from config)\n"
            f"  lambda_w  = {s.get('lambda_w', 1.0):.4g}   (propulsion weight from config)\n"
            f"  N_act     = {s.get('N_act', 0)}    (number of active offload pairs this BCD iter)\n"
            f"  N_fly     = {s.get('N_fly', 0)}    (number of UAV movement segments)\n"
            f"  n_uavs    = {s.get('n_uavs', 0)}\n"
            f"  n_tasks_active = {s.get('n_tasks_active', 0)}\n\n"
        )

    def _rules(self) -> str:
        return (
            "## Coding Rules (STRICT)\n"
            "1. Output ONLY a JSON object: {\"traj_obj_description\": \"...\", \"traj_obj_code\": \"...\"}\n"
            "2. traj_obj_code MUST assign `dynamic_traj_objective` (a CVXPY expression).\n"
            "3. Coefficients MUST be positive Python floats (ensures convexity).\n"
            "   VALID:   2.0 * alpha * obj_comm_surrogate\n"
            "   INVALID: -alpha * obj_comm_surrogate   ← negative breaks DCP\n"
            "4. You may use `import math` and math.* functions ONLY on scalar values,\n"
            "   NOT on CVXPY expressions.\n"
            "   VALID:   math.exp(0.5) * alpha * obj_comm_surrogate\n"
            "   INVALID: cp.exp(obj_comm_surrogate)   ← may not be DCP\n"
            "5. obj_slack MUST always appear with a positive coefficient (≥ 1.0).\n"
            "6. Do NOT import cvxpy or gurobipy. Do NOT define functions.\n"
            "7. Keep coefficients in [0.01, 100] to avoid numerical issues.\n\n"
            "## Example traj_obj_code\n"
            "```python\n"
            "import math\n"
            "# Emphasize communication for many active offloads\n"
            "w_comm = math.log1p(N_act / 5.0 + 1.0) * alpha\n"
            "dynamic_traj_objective = w_comm * obj_comm_surrogate + 0.3 * lambda_w * obj_propulsion + obj_slack\n"
            "```\n\n"
        )

    def _prompt_way1(self) -> str:
        return (
            self._header()
            + self._rules()
            + "## Your Task\n"
            "Design a COMPLETELY NEW weighting strategy for the trajectory objective.\n"
            "Consider:\n"
            "  - Should communication be weighted more when there are many active offloads?\n"
            "  - Should propulsion be weighted less to allow more aggressive positioning?\n"
            "  - Can scalar transforms (math.exp, math.log1p, math.sqrt) on N_act/N_fly\n"
            "    produce adaptive weights that work across different scenario conditions?\n\n"
            "Think creatively. The default simply uses alpha and lambda_w directly.\n"
            "Your goal is to find weights that make UAVs position themselves better\n"
            "relative to their assigned tasks, improving the final evaluation score.\n"
        )

    def _prompt_way2(self, best_traj_code: str) -> str:
        return (
            self._header()
            + self._rules()
            + "## Current Best Trajectory Objective\n"
            "The best-performing individual uses this traj_obj_code:\n\n"
            f"```python\n{best_traj_code}\n```\n\n"
            "## Your Task\n"
            "IMPROVE the existing strategy by making targeted adjustments:\n"
            "  - Fine-tune scalar coefficients (change by ±20-50%)\n"
            "  - Adjust how N_act or N_fly affect the weights\n"
            "  - Try a slightly different math transform (e.g., exp vs log1p)\n"
            "Keep at least 50% of the original structure. Output improved code.\n"
        )

    def _prompt_way3(self, best_traj_code: str) -> str:
        return (
            self._header()
            + self._rules()
            + "## Current Best Trajectory Objective (for reference only)\n"
            f"```python\n{best_traj_code}\n```\n\n"
            "## Your Task\n"
            "Design a STRUCTURALLY DIFFERENT weighting strategy. Change at least 2 aspects:\n"
            "  - Different mathematical transform (e.g., switch exp ↔ sqrt ↔ tanh)\n"
            "  - Different which parameter drives adaptation (N_act vs N_fly vs ratio)\n"
            "  - Different balance between comm vs propulsion emphasis\n"
            "Do NOT copy the reference code. Create a genuinely distinct approach.\n"
        )
