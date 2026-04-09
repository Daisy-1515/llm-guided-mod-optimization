"""
文件: edge_uav/prompt/base_prompt.py

用于边缘 UAV 计算卸载优化的提示词模板。

该模块是一个独立的基类 - 不继承原项目的 basicPrompts。
所有五个提示词组件都为“边缘计算 + UAV”场景从零构建。
"""

from functools import lru_cache
from pathlib import Path


@lru_cache(maxsize=None)
def _read_model_source_cached(model_path: str) -> str:
    """读取模型源码并缓存，避免多个个体重复读磁盘。"""
    try:
        return Path(model_path).read_text(encoding="utf-8").strip()
    except FileNotFoundError:
        return (
            "[OffloadingModel source not yet available]\n"
            "The model file will be created at: " + model_path + "\n"
            "For now, refer to the structured explanation below."
        )
    except Exception as exc:
        return f"[Error reading model source: {exc}]"


class EdgeUavPrompts:
    """Edge UAV 任务卸载（Level 1 BLP）的基础提示词模板。

    五个提示词组件：
        1. prompt_scenario          - 系统概览与 LLM 任务描述
        2. prompt_static_info       - 运行期统计摘要（由 set_scenario_info 填充）
        3. prompt_init_level1model  - OffloadingModel 源码 + 结构化说明
        4. prompt_obj_format        - LLM 输出必须遵循的 JSON 格式
        5. prompt_cons_restriction  - Gurobi 编码规则与变量约束
    """

    def __init__(self, model_path):
        """
        参数
        ----------
        model_path : str
            OffloadingModel 源文件路径。其内容会嵌入提示词中，
            以便 LLM 了解模型结构。
        """
        self.model_path = model_path

        # ---- 构建五个核心提示词组件 ----
        self.prompt_scenario = self._build_scenario()
        self.prompt_static_info = self._build_static_info_placeholder()
        self.prompt_init_level1model = self._build_init_level1model()
        self.prompt_obj_format = self._build_obj_format()
        self.prompt_cons_restriction = self._build_cons_restriction()

    # ------------------------------------------------------------------
    # 1. 场景描述
    # ------------------------------------------------------------------
    def _build_scenario(self):
        return (
            "Act as an expert in Edge Computing and UAV trajectory optimization. "
            "You are designing the primary objective function for a two-level "
            "real-time computation offloading system.\n\n"
            # "【中文注释】请作为边缘计算与 UAV 轨迹优化领域的专家。"
            # "你正在为两层实时计算卸载系统设计一级主目标函数。\n\n"

            "1. **System Overview**:\n"
            # "【中文注释】1. 系统概览：\n"
            "   - Multiple UAVs fly over a service area, each carrying an edge computing server.\n"
            # "   【中文注释】多架 UAV 在服务区域上空飞行，每架携带边缘计算服务器。\n"
            "   - Ground terminal devices (TDs) generate computation tasks every time slot.\n"
            # "   【中文注释】地面终端设备（TD）在每个时隙生成计算任务。\n"
            "   - Each task can be executed locally on the TD, or offloaded to a nearby UAV for remote execution.\n"
            # "   【中文注释】每个任务可在本地 TD 执行，或卸载到附近 UAV 远程执行。\n"
            "   - The system operates in discrete time slots indexed by t.\n\n"
            # "   【中文注释】系统以离散时隙运行，时隙索引为 t。\n\n"

            "2. **Optimization Structure (Two-Level Decomposition)**:\n"
            # "【中文注释】2. 优化结构（两层分解）：\n"
            "   - **Level 1 (Your Task)**: Task offloading assignment - decide which tasks execute locally "
            "and which offload to which UAV. This is a Binary Linear Program (BLP) solved by Gurobi.\n"
            # "   【中文注释】**Level 1（你的任务）**：任务卸载分配 - 决定哪些任务本地执行，哪些卸载到哪架 UAV。"
            # "这是由 Gurobi 求解的二进制线性规划（BLP）。\n"
            "   - **Level 2 (Already Solved)**: Given fixed offloading decisions, jointly optimize "
            "UAV trajectories and CPU frequency allocation via BCD + SCA.\n"
            #"   【中文注释】**Level 2（已解决）**：在卸载决策固定时，使用 BCD + SCA 联合优化 UAV 轨迹与 CPU 频率分配。\n"
            "   - The two levels alternate iteratively (Block Coordinate Descent) until convergence.\n\n"
            #"   【中文注释】两层通过交替迭代（块坐标下降）直到收敛。\n\n"

            "3. **Your Task**:\n"
            #"【中文注释】3. 你的任务：\n"
            "   Design a novel Level-1 objective function that guides Gurobi to make "
            "good offloading decisions. Your objective is a *proxy* - it replaces the "
            "standard cost function to explore creative optimization strategies. "
            "The proxy objective should:\n"
            #"   【中文注释】设计一个新的 Level-1 目标函数，引导 Gurobi 做出良好的卸载决策。"
            #"你的目标是一个*代理* - 用于替换标准成本函数以探索创新优化策略。该代理目标应：\n"
            "   - Minimize a weighted combination of task completion delay and energy consumption.\n"
            #"   【中文注释】最小化任务完成时延与能耗的加权组合。\n"
            "   - Account for task urgency (deadline), UAV proximity, and load distribution.\n"
           # "   【中文注释】考虑任务紧迫度（截止期）、UAV 距离与负载分布。\n"
            "   - Be compatible with Gurobi's BLP formulation (linear in binary variables).\n\n"
            #"   【中文注释】与 Gurobi 的 BLP 形式兼容（对二进制变量线性）。\n\n"

            "4. **Key Requirements**:\n"
            #"【中文注释】4. 关键要求：\n"
            "   - Each task must be assigned exactly once within its active window "
            "(local or one UAV).\n"
           # "   【中文注释】每个时隙的所有任务必须分配（本地或某一 UAV）。\n"
            "   - Only active tasks (task[i].active[t] == True) should be included in summations.\n"
            #"   【中文注释】只有活跃任务（task[i].active[t] == True）可参与求和。\n"
            "   - The objective must be expressible using Gurobi linear expressions.\n"
            #"   【中文注释】目标必须能用 Gurobi 线性表达式表示。\n"
            "   - Precomputed constants (delays, energies) are available - no need to recompute them.\n"
            #"   【中文注释】预计算常量（时延、能耗）已提供 - 无需重新计算。"
        )

    # ------------------------------------------------------------------
    # 2. 静态信息（运行时由 set_scenario_info 填充）
    # ------------------------------------------------------------------
    def _build_static_info_placeholder(self):
        return (
            "=== System Scale ===\n"
            "Data not yet initialized. Call set_scenario_info() after scenario generation.\n"
            #"【中文注释】数据尚未初始化。请在场景生成后调用 set_scenario_info()。"
        )

    def set_scenario_info(self, tasks, uavs, time_slots):
        """用真实场景统计信息填充静态信息。

        在场景生成后、优化循环前调用一次。

        参数
        ----------
        tasks : dict
            {task_id: task_dataclass}，属性包括：D_l, D_r, F, tau, active。
        uavs : dict
            {uav_id: uav_dataclass}，属性包括：E_max, f_max, pos。
        time_slots : list
            时隙索引列表。
        """
        num_tasks = len(tasks)
        num_uavs = len(uavs)
        num_time = len(time_slots)

        def _stats(values):
            """返回 (min, max, mean)，并对空列表做安全处理。"""
            if not values:
                return "N/A", "N/A", "N/A"
            return min(values), max(values), sum(values) / len(values)

        tau_min, tau_max, tau_mean = _stats([t.tau for t in tasks.values()])
        data_min, data_max, data_mean = _stats([t.D_l + t.D_r for t in tasks.values()])
        e_min, e_max_val, e_mean = _stats([u.E_max for u in uavs.values()])
        f_min, f_max_val, f_mean = _stats([u.f_max for u in uavs.values()])

        # 活跃时间窗统计
        T_total = len(time_slots)
        window_lengths = [
            sum(1 for t in time_slots if task.active[t])
            for task in tasks.values()
        ]
        wl_min, wl_max, wl_mean = _stats(window_lengths)
        tight_threshold = max(1, T_total // 3)
        tight_count = sum(1 for wl in window_lengths if wl <= tight_threshold)
        tight_ratio = tight_count / len(window_lengths) if window_lengths else 0.0

        def _fmt(val, spec):
            return val if val == "N/A" else format(val, spec)

        self.prompt_static_info = (
            "=== System Scale ===\n"
            f"- Terminal devices (tasks): {num_tasks}\n"
            f"- UAVs (edge servers):     {num_uavs}\n"
            f"- Time slots:              {num_time}\n\n"
            #"【中文注释】系统规模：终端任务数 / UAV 数 / 时隙数。\n\n"

            "=== Task Statistics ===\n"
            f"- Deadline (tau): min={_fmt(tau_min, '.3f')}s, "
            f"max={_fmt(tau_max, '.3f')}s, mean={_fmt(tau_mean, '.3f')}s\n"
            f"- Total data size (D_l + D_r): min={_fmt(data_min, '.0f')} bits, "
            f"max={_fmt(data_max, '.0f')} bits, mean={_fmt(data_mean, '.0f')} bits\n"
            f"- Active window length: min={_fmt(wl_min, 'd') if wl_min != 'N/A' else 'N/A'} slots, "
            f"max={_fmt(wl_max, 'd') if wl_max != 'N/A' else 'N/A'} slots, "
            f"mean={_fmt(wl_mean, '.1f') if wl_mean != 'N/A' else 'N/A'} slots (T={T_total})\n"
            f"- Tight-window tasks (window ≤ {tight_threshold} slots): "
            f"{tight_ratio:.0%} of tasks\n\n"
            #"【中文注释】任务统计：截止期与数据规模的最小/最大/平均值。\n\n"

            "=== UAV Statistics ===\n"
            f"- Max energy (E_max): min={_fmt(e_min, '.1f')}J, "
            f"max={_fmt(e_max_val, '.1f')}J, mean={_fmt(e_mean, '.1f')}J\n"
            f"- Max CPU freq (f_max): min={_fmt(f_min, '.2e')} Hz, "
            f"max={_fmt(f_max_val, '.2e')} Hz, mean={_fmt(f_mean, '.2e')} Hz\n\n"
            #"【中文注释】UAV 统计：最大能量与最大 CPU 频率的最小/最大/平均值。\n\n"

            "Note: Full matrices are NOT shown to save tokens. "
            "Use the precomputed constants (D_hat_*, E_hat_*) directly in your objective.\n"
            #"【中文注释】为节省 token，不展示完整矩阵。请直接使用预计算常量（D_hat_*, E_hat_*）。"
        )

    # ------------------------------------------------------------------
    # 3. Level 1 模型定义
    # ------------------------------------------------------------------
    def _build_init_level1model(self):
        model_src = self._read_model_source()

        return (
            "=== OffloadingModel Source ===\n"
            f"{model_src}\n\n"
           # "【中文注释】以上为 OffloadingModel 源码。\n\n"
            "=== Model Structure ===\n"
            "- ComputeTask: dataclass with D_l (local data), D_r (remote data), "
            "F (CPU cycles), tau (deadline), active[t] (per-slot activity flag).\n"
            "- UAV: dataclass with E_max (energy budget), f_max (max CPU freq), "
            "pos (current position).\n"
            "- OffloadingModel: Gurobi-based Level-1 BLP. "
            "Your goal is to replace its objective function.\n\n"
            #"【中文注释】模型结构：任务与 UAV 数据类，以及基于 Gurobi 的 Level-1 BLP。"
            #"你的目标是替换其目标函数。\n\n"
            "=== Key Methods ===\n"
            "- setupVars: Creates binary variables x_local[i,t] and x_offload[i,j,t].\n"
            "- setupCons: Ensures each task is executed exactly once within its "
            "active window (local or one UAV).\n"
            "- setupObj: Configurable objective - you design a new one via dynamic_obj_func.\n\n"
            #"【中文注释】关键方法：变量创建、约束建立、目标函数构造。\n\n"
            "=== Precomputed Constants (available in self) ===\n"
            "- self.D_hat_local[i][t]:      local execution delay (seconds), scalar.\n"
            "- self.D_hat_offload[i][j][t]: remote offloading delay "
            "(upload + compute + download), scalar.\n"
            "- self.E_hat_comp[j][i][t]:    edge computing energy consumption (Joules), scalar.\n"
           # "【中文注释】可用预计算常量：本地/卸载时延与边缘计算能耗。\n"
        )

    def _read_model_source(self):
        """读取 OffloadingModel 源码并嵌入提示词。"""
        return _read_model_source_cached(str(self.model_path))

    # ------------------------------------------------------------------
    # 4. 输出格式
    # ------------------------------------------------------------------
    def _build_obj_format(self):
        # 说明：末尾使用 .replace() 转义大括号，避免后续 .format() 处理 JSON 时出错。
        raw = (
            "Generate response **EXACTLY AND MUST** in this JSON format:\n"
            '{"obj_description": "[Brief description of your objective strategy]",'
            '"obj_code": "def dynamic_obj_func(self):\n'
            '    print(\\"Creating dynamic objectives for Offloading Model\\")\n'
            '    # Define cost components (1-5 components)\n'
            '    cost1 = gb.quicksum(\n'
            '        self.D_hat_local[i][t] / self.task[i].tau\n'
            '        * self.x_local[i, t]\n'
            '        for i in self.taskList for t in self.timeList\n'
            '        if self.task[i].active[t]\n'
            '    )\n'
            '    cost2 = [Your Gurobi expression]\n'
            '    costs = [cost1, cost2]\n'
            '    weights = [w1, w2]  # Must match length of costs\n'
            '    objective = gb.quicksum(w*c for w, c in zip(costs, weights))\n'
            '    self.model.setObjective(objective, gb.GRB.MINIMIZE)"}\n'
            "\n"
            "Requirements:\n"
            "1. **NO EXPLANATIONS**: Only provide the JSON object - no markdown, no analysis.\n"
            #"【中文注释】1. **禁止解释**：仅输出 JSON 对象，不要 markdown 或分析。\n"
            "2. **Indentation**: Every line after `def` MUST start with exactly 4 spaces.\n"
            #"【中文注释】2. **缩进**：`def` 之后的每一行必须以 4 个空格开头。\n"
            "3. **Validation**: Test your code mentally for valid Python before responding.\n"
            #"【中文注释】3. **校验**：回复前请在脑中检查代码的 Python 有效性。\n"
            "4. JSON must contain exactly two keys: obj_description (string) and obj_code (code block)."
           # "\n【中文注释】4. JSON 必须且只能包含两个键：obj_description（字符串）和 obj_code（代码块）。"
            #"\n\n【中文注释】请严格按指定 JSON 格式输出。"
        )
        return raw.replace("{", "{{").replace("}", "}}")

    # ------------------------------------------------------------------
    # 5. 约束限制（Gurobi 编码规则）
    # ------------------------------------------------------------------
    def _build_cons_restriction(self):
        raw = (
            "5. Code implementation requirements:\n"
            "   - Number of cost components: 1 <= n <= 5.\n"
            "   - Weights list must match the length of costs list.\n"
            "   - Final objective must use: gb.quicksum(w*c for w, c in zip(costs, weights)).\n"
            #"【中文注释】5. 代码实现要求：成本项数量 1-5；weights 长度匹配 costs；目标使用指定求和形式。\n"

            "6. Variable naming (MUST use exactly):\n"
            "   - self.x_local[i, t]          (binary: 1 = execute locally)\n"
            "   - self.x_offload[i, j, t]     (binary: 1 = offload task i to UAV j at time t)\n"
            "     Index order: i=task, j=UAV, t=time slot. DO NOT swap.\n"
            "   - self.D_hat_local[i][t]       (precomputed local delay, scalar constant)\n"
            "   - self.D_hat_offload[i][j][t]  (precomputed remote delay, scalar constant)\n"
            "   - self.E_hat_comp[j][i][t]     (precomputed edge energy, scalar constant)\n"
            "   - self.task[i].tau             (deadline, scalar constant)\n"
            "   - self.task[i].active[t]       (Python bool - use in `if` guards)\n"
            "   - self.uav[j].E_max           (max energy budget, scalar constant)\n"
            "   - self.alpha                   (delay weight, scalar constant)\n"
            "   - self.gamma_w                 (energy weight, scalar constant)\n"
            "   - self.M                       (big-M constant for linearization)\n"
            #"【中文注释】6. 变量命名必须严格一致：本地/卸载变量、预计算常量、权重与大 M 常量。\n"

            "7. Active-task gating (CRITICAL):\n"
            "   - Every summation over tasks MUST filter by self.task[i].active[t].\n"
            "   - Use Python `if` inside generator: "
            "`gb.quicksum(... for i in self.taskList for t in self.timeList if self.task[i].active[t])`.\n"
            "   - NEVER sum over inactive tasks - they have no valid precomputed constants.\n"
            #"【中文注释】7. 活跃任务筛选（关键）：所有求和必须过滤 active[t]，禁止包含非活跃任务。\n"

            "8. Full time-slot summation:\n"
            "   - When computing per-task or per-UAV aggregates, always sum across ALL t in self.timeList.\n"
            "   - Combine with the active-task filter: "
            "`for i in self.taskList for t in self.timeList if self.task[i].active[t]`.\n"
            "   - Do NOT optimize for a single time slot unless explicitly instructed.\n"
           # "【中文注释】8. 全时隙求和：聚合时需覆盖全部 t，并结合 active[t] 过滤。\n"

            "9. Scale awareness:\n"
            "   - Delays are in seconds (typically 0.001 ~ 1.0 s).\n"
            "   - Energy is in Joules (typically 0.1 ~ 100 J).\n"
            "   - Use self.alpha and self.gamma_w to balance them, or normalize by "
            "self.task[i].tau and self.uav[j].E_max respectively.\n"
            #"【中文注释】9. 量纲意识：时延秒级、能量焦耳级，可用 alpha/gamma_w 平衡或归一化。\n"

            "10. Deadline awareness:\n"
            "   - Consider adding a soft penalty for tasks close to their deadline.\n"
            "   - Example: penalty = max(D_hat_offload[i][j][t] - task[i].tau, 0) "
            "(use Python max() since operands are constants).\n"
            #"【中文注释】10. 截止期意识：可加入软惩罚，如 max(D_hat_offload - tau, 0)。\n"

            "11. gb.quicksum rules:\n"
            "   a) NEVER nest gb.quicksum() inside another gb.quicksum().\n"
            "   b) Flatten multi-dimensional sums into a single gb.quicksum with multiple `for` clauses.\n"
            "      - Valid:   gb.quicksum(expr for i in ... for j in ... for t in ...)\n"
            "      - Invalid: gb.quicksum(gb.quicksum(...) for i in ...)\n"
            "   c) Do NOT use gb.quicksum for a single term - just use the expression directly.\n"
           # "【中文注释】11. gb.quicksum 规则：禁止嵌套；展开多维求和；单项不需要 quicksum。\n"

            "12. Expression function rules:\n"
            "   - Use gb.quicksum()/gb.max_()/gb.abs_() ONLY when the expression contains Gurobi variables.\n"
            "   - Use Python sum()/max()/abs() when working with pure constants (parameters).\n"
            "   - You may use `import math` and apply math.exp(), math.log(), math.log1p(), "
            "math.sqrt(), math.pow(), math.tanh() on PURE SCALAR CONSTANTS to create "
            "nonlinear coefficient transformations. The result is still a scalar, so "
            "multiplying it by a binary variable remains linear for Gurobi.\n"
            "   - Example: `math.exp(D_hat_offload[i][j][t] / task[i].tau) * x_offload[i, j, t]` "
            "is valid — exp() operates on a constant, producing a scalar coefficient.\n"
            #"【中文注释】12. 表达式函数：含变量用 gb.*，纯常量用 Python 内置函数或 math 模块。\n"

            "13. Quadratic term rules:\n"
            "   - For squared terms, use variable * variable directly.\n"
            "   - NEVER use Python list.append() with Gurobi expressions.\n"
           # "【中文注释】13. 二次项：直接用变量相乘，禁止用 list.append 组装 Gurobi 表达式。\n"

            "14. Conditional logic handling:\n"
            "   - NEVER use Python if/else on Gurobi variables/expressions.\n"
            "   - For conditional cost components that depend on binary variables, "
            "multiply by the binary variable directly (big-M linearization).\n"
            #"【中文注释】14. 条件逻辑：禁止对 Gurobi 变量用 if/else；条件项用二元变量乘法或大 M 线性化。\n"

            "15. Nonlinear handling:\n"
            "   - For products of two binary variables: create auxiliary variable + big-M constraints.\n"
            "   - All precomputed constants (D_hat_*, E_hat_*) are scalars - multiplying them "
            "by a binary variable is always linear.\n"
            #"【中文注释】15. 非线性处理：二元变量乘积需引入辅助变量+大 M；常量乘二元变量保持线性。\n"

            "16. Coefficient diversity — STRONGLY ENCOURAGED:\n"
            "   - Go beyond simple linear ratios (D/tau, E/E_max). Transform scalar constants "
            "with nonlinear functions to reshape the cost landscape:\n"
            "     * Exponential urgency:  math.exp(min(k * D_hat / tau, 3.0))  — k=1.0~2.0 recommended\n"
            "       (exp(3)≈20, exp(5)≈148, exp(10)≈22000 causes numerical instability)\n"
            "     * Logarithmic saturation:  math.log1p(E_hat / E_max)  — diminishing returns on energy cost\n"
            "     * Square-root smoothing:  math.sqrt(D_hat / tau)  — gentle sub-linear penalty\n"
            "     * Sigmoid-like focus:  math.tanh(k * (D_hat/tau - threshold))  — output in [-1,1], safe\n"
            "     * Power-law:  math.pow(D_hat / tau, p)  — p=1.5~3.0 recommended, avoid extreme values\n"
            "   - These all produce scalar coefficients, so `f(constant) * binary_var` is linear for Gurobi.\n"
            "   - Combine different transforms across cost components for richer trade-off surfaces.\n"
            "   - CRITICAL: Keep coefficients in [0.01, 100] range. Values outside [1e-6, 1e6] "
            "will cause Gurobi numerical issues and BCD solver failures.\n"
            #"【中文注释】16. 系数多样性（强烈建议）：用 exp/log/sqrt/tanh/pow 变换常数系数，丰富目标搜索空间。\n"
            "# 注意：exp 参数上限 3.0，pow 指数 1.5~3.0，系数范围 [0.01, 100]，避免数值爆炸。\n"

            "17. Time-window urgency — OPTIONAL but RECOMMENDED:\n"
            "   - Each task i has an active window: a contiguous set of time slots where it can be served.\n"
            "   - A task with a shorter active window is harder to schedule (fewer opportunities).\n"
            "   - You MAY scale per-task penalty terms by a window-tightness factor computed as pure Python:\n"
            "       window_size_i = sum(1 for t in self.timeList if self.task[i].active[t])  # scalar int\n"
            "       tightness_i   = len(self.timeList) / max(window_size_i, 1)               # scalar float\n"
            "   - Then multiply inside gb.quicksum, e.g.:\n"
            "       math.log1p(tightness_i) * D_hat_local[i][t] / task[i].tau * x_local[i,t]\n"
            "   - window_size_i and tightness_i are pure constants — Python arithmetic is safe here.\n"
            "   - The scenario statistics section shows the distribution of tight-window tasks.\n"
        )
        return raw.replace("{", "{{").replace("}", "}}")

    # ------------------------------------------------------------------
    # Getter 方法
    # ------------------------------------------------------------------
    def get_scenario(self):
        return self.prompt_scenario

    def get_static_info(self):
        return self.prompt_static_info

    def get_level1model(self):
        return self.prompt_init_level1model

    def get_obj_format(self):
        return self.prompt_obj_format

    def get_cons_restriction(self):
        return self.prompt_cons_restriction
