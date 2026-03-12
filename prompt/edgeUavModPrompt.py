"""
文件: edgeUavModPrompt.py

用于 Edge UAV 卸载提示词模板的进化策略。

继承 EdgeUavPrompts，并添加 Harmony Search 种群管理器使用的
四种变异/生成策略：

    way1 - 全新生成（完全新的目标函数）
    way2 - 基于最佳个体的改进（TODO：依赖 OffloadingModel）
    way3 - 基于最佳个体的结构重构（TODO：依赖 OffloadingModel）
    way4 - 资源感知生成（能量 + 负载均衡）
"""

from prompt.edgeUavPrompt import EdgeUavPrompts


class EdgeUavModPrompts(EdgeUavPrompts):
    """用于 Harmony Search 的提示词进化策略。

    用法
    -----
    >>> prompts = EdgeUavModPrompts(model_path="model/two_level/OffloadingModel.py")
    >>> prompts.set_scenario_info(tasks, uavs, time_slots)   # 场景生成后
    >>> text = prompts.get_prompt_way1(iter=3, task_info="...", uav_info="...")
    """

    def __init__(self, model_path):
        super().__init__(model_path)
        self._setup_template_components()

    # ------------------------------------------------------------------
    # 模板组装
    # ------------------------------------------------------------------
    def _setup_template_components(self):
        """从五个基础组件预先组装可复用的提示词块。"""

        self._scenario_block = (
            f"{self.prompt_scenario}\n\n"
            "Below is the system scale summary:\n"
            # "【中文注释】以下是系统规模摘要：\n"
            f"{self.prompt_static_info}\n\n"
            "Below is the Level-1 model information. "
            "Your goal is to replace the function [dynamic_obj_func(self)]:\n"
            # "【中文注释】以下是 Level-1 模型信息。你的目标是替换函数 [dynamic_obj_func(self)]：\n"
            f"{self.prompt_init_level1model}\n\n"
        )

        self._iteration_block = (
            "--- Iteration Context ---\n"
            # "【中文注释】--- 迭代上下文 ---\n"
            "This is the {iter}th optimization iteration.\n"
            # "【中文注释】这是第 {iter} 次优化迭代。\n"
            "{task_info}\n"
            "{uav_info}\n\n"
        )

        self._base_instruction = (
            "Given the above information:\n"
            # "【中文注释】基于以上信息：\n"
            "1. {objective_instruction}\n"
            "2. Implement it as a Python function following Gurobi format.\n"
            # "【中文注释】2. 按照 Gurobi 格式实现为 Python 函数。\n"
            f"{self.prompt_obj_format}\n"
            f"{self.prompt_cons_restriction}"
        )

    def refresh_scenario_block(self):
        """在 set_scenario_info() 更新静态信息后重建 _scenario_block。

        如果在 __init__ 之后调用 set_scenario_info()，必须执行本方法。
        """
        self._setup_template_components()

    # ------------------------------------------------------------------
    # 提示词构建器（内部）
    # ------------------------------------------------------------------
    def _build_core_prompt(self, context_block, instruction):
        """从场景上下文 + 迭代信息 + 指令组装完整提示词。

        参数
        ----------
        context_block : str
            场景上下文（通常是 self._scenario_block）。
        instruction : dict
            必须包含：
              - "iteration": {"iter": int}
              - "task_info": str
              - "uav_info": str
              - "objective_instruction": str
        """
        iter_text = self._iteration_block.format(
            iter=instruction["iteration"]["iter"],
            task_info=instruction.get("task_info", ""),
            uav_info=instruction.get("uav_info", ""),
        )
        instr_text = self._base_instruction.format(
            objective_instruction=instruction["objective_instruction"],
        )
        return f"{context_block}{iter_text}{instr_text}"

    def _build_inspirational_prompt(self, best_ind, instruction):
        """组装包含历史最佳个体参考的提示词。

        参数
        ----------
        best_ind : str or dict
            上一次运行中的最佳个体描述、代码与适应度。
        instruction : dict
            与 _build_core_prompt 相同结构，包含 "objective_instruction"。
        """
        iter_text = self._iteration_block.format(
            iter=instruction["iteration"]["iter"],
            task_info=instruction.get("task_info", ""),
            uav_info=instruction.get("uav_info", ""),
        )
        instr_text = self._base_instruction.format(
            objective_instruction=instruction["objective_instruction"],
        )
        return (
            f"{self._scenario_block}"
            "--- Previous Best Run ---\n"
            # "【中文注释】--- 先前最佳运行 ---\n"
            "Below is one of your previous runs that achieved a good cost score. "
            "Its description, objective code, and evaluated system cost are provided:\n"
            # "【中文注释】以下是一次取得较好成本分数的历史运行。提供了其描述、目标代码与评估后的系统成本：\n"
            f"{best_ind}\n\n"
            f"{iter_text}"
            f"{instr_text}"
        )

    # ------------------------------------------------------------------
    # 方式 1：全新生成
    # ------------------------------------------------------------------
    def get_prompt_way1(self, iter, task_info, uav_info):
        """生成用于创建全新目标函数的提示词。

        参数
        ----------
        iter : int
            当前 Harmony Search 迭代索引。
        task_info : str
            当前任务状态摘要（活跃任务、紧迫度等）。
        uav_info : str
            当前 UAV 状态摘要（位置、能量等）。
        """
        instruction = {
            "iteration": {"iter": iter},
            "task_info": task_info,
            "uav_info": uav_info,
            "objective_instruction": (
                "Please generate a **new objective function** for the Level-1 "
                "offloading assignment problem. Your objective should creatively "
                "balance task completion delay, edge computing energy, and assignment "
                "quality. Consider proximity, urgency, and load distribution.\n"
                # "【中文注释】请为 Level-1 卸载分配问题生成**新的目标函数**。"
                # "目标应在任务完成时延、边缘计算能耗与分配质量之间进行创新性平衡。"
                # "请考虑距离、紧迫度与负载分布。"
            ),
        }
        return self._build_core_prompt(self._scenario_block, instruction)

    # ------------------------------------------------------------------
    # 方式 2：基于最佳个体改进（TODO）
    # ------------------------------------------------------------------
    def get_prompt_way2(self, iter, task_info, uav_info, best_ind):
        """生成用于改进最佳目标函数的提示词。

        TODO: best_ind 的结构依赖 OffloadingModel，尚未实现。
        该方法为占位符 - 需在 OffloadingModel 可用且
        个体评估流程（hsIndividualMultiCall）完成适配后补全。

        参数
        ----------
        best_ind : str or dict
            上一代最佳个体。结构待定
            （将包含 obj_description, obj_code, fitness score）。
        """
        instruction = {
            "iteration": {"iter": iter},
            "task_info": task_info,
            "uav_info": uav_info,
            "objective_instruction": (
                "Develop an **improved objective function** based on the previous best run:\n"
                "a) Preserve approximately 50% of the original structure.\n"
                "b) Refine the weighting strategy - consider adjusting alpha/gamma_w balance.\n"
                "c) Add or improve penalty terms for deadline violations or load imbalance.\n"
                "d) Ensure all active-task gating rules are maintained.\n"
                # "【中文注释】基于先前最佳运行，设计**改进版目标函数**：\n"
                # "a) 保留约 50% 的原有结构。\n"
                # "b) 优化权重策略 - 考虑调整 alpha/gamma_w 的平衡。\n"
                # "c) 新增或改进截止期违约或负载不均衡的惩罚项。\n"
                # "d) 确保所有活跃任务过滤规则保持不变。"
            ),
        }
        return self._build_inspirational_prompt(best_ind, instruction)

    # ------------------------------------------------------------------
    # 方式 3：结构性重构（TODO）
    # ------------------------------------------------------------------
    def get_prompt_way3(self, iter, task_info, uav_info, best_ind):
        """生成用于根本性重构目标函数的提示词。

        TODO: 与 way2 相同，依赖 OffloadingModel。
        该方法为占位符。

        参数
        ----------
        best_ind : str or dict
            上一代最佳个体。结构待定。
        """
        instruction = {
            "iteration": {"iter": iter},
            "task_info": task_info,
            "uav_info": uav_info,
            "objective_instruction": (
                "**Reinvent the objective function** from scratch, inspired by "
                "the previous best run but with a fundamentally different approach:\n"
                "a) The overall goal is to minimize weighted system cost "
                "(delay + energy) as evaluated by the simulator.\n"
                "b) Try a completely different cost decomposition or weighting scheme.\n"
                "c) Consider creative strategies: QoS tiers, proximity clustering, "
                "energy-proportional assignment, or fairness-aware allocation.\n"
                "d) Maintain all variable naming and gating rules.\n"
                # "【中文注释】从零开始**重构目标函数**，参考先前最佳运行但采用本质不同的方法：\n"
                # "a) 总体目标是最小化模拟器评估的加权系统成本（时延 + 能耗）。\n"
                # "b) 尝试完全不同的成本分解或权重方案。\n"
                # "c) 可考虑 QoS 分层、距离聚类、能量比例分配或公平性分配等策略。\n"
                # "d) 保持所有变量命名与活跃任务筛选规则。"
            ),
        }
        return self._build_inspirational_prompt(best_ind, instruction)

    # ------------------------------------------------------------------
    # 方式 4：资源感知生成
    # ------------------------------------------------------------------
    def get_prompt_way4(self, iter, task_info, uav_info):
        """生成包含显式资源感知指导的提示词。

        该策略引导 LLM 关注 UAV 能量预算、算力上限与负载均衡 -
        这些方面在 way1 的泛化指令中可能被忽略。

        参数
        ----------
        iter : int
            当前 Harmony Search 迭代索引。
        task_info : str
            当前任务状态摘要。
        uav_info : str
            当前 UAV 状态摘要（必须包含能量信息）。
        """
        resource_guidance = (
            "--- Resource-Aware Guidance ---\n"
            # "【中文注释】--- 资源感知指导 ---\n"
            "Pay special attention to the following resource constraints:\n\n"
            # "【中文注释】请特别关注以下资源约束：\n\n"
            "1. **Energy Budget Sensitivity**:\n"
            # "【中文注释】1. **能量预算敏感性**：\n"
            "   - Each UAV has a finite energy budget (self.uav[j].E_max).\n"
            # "   【中文注释】每架 UAV 都有有限能量预算（self.uav[j].E_max）。\n"
            "   - Penalize assigning tasks to UAVs whose cumulative energy cost "
            "(sum of E_hat_comp[j][i][t] over assigned tasks) approaches E_max.\n"
            # "   【中文注释】对累计能耗接近 E_max 的 UAV 进行任务分配惩罚。\n"
            "   - Consider a per-UAV energy utilization ratio as a penalty factor.\n\n"
            # "   【中文注释】可将每架 UAV 的能量利用率作为惩罚因子。\n\n"

            "2. **Load Balancing**:\n"
            # "【中文注释】2. **负载均衡**：\n"
            "   - Avoid concentrating all tasks on a single UAV.\n"
            # "   【中文注释】避免将所有任务集中在单个 UAV 上。\n"
            "   - Add a linear load-balancing penalty to encourage even distribution.\n"
            # "   【中文注释】加入线性负载均衡惩罚，鼓励任务均匀分布。\n"
            "   - Example (linear per-UAV load): gb.quicksum(self.x_offload[i, j, t] "
            "for i in self.taskList for j in self.uavList for t in self.timeList "
            "if self.task[i].active[t])\n"
            # "   【中文注释】示例（线性 UAV 负载）：gb.quicksum(self.x_offload[i, j, t] ...)。\n"
            "   - For per-UAV quadratic penalties, define auxiliary variables in constraints; "
            "do NOT nest gb.quicksum.\n\n"
            # "   【中文注释】若使用每 UAV 二次惩罚，请在约束中引入辅助变量；禁止嵌套 gb.quicksum。\n\n"

            "3. **Deadline-Energy Tradeoff**:\n"
            # "【中文注释】3. **截止期-能耗权衡**：\n"
            "   - Urgent tasks (small tau) should prefer the nearest UAV even if "
            "it costs more energy.\n"
            # "   【中文注释】紧急任务（小 tau）应优先选择最近 UAV，即使能耗更高。\n"
            "   - Non-urgent tasks should prefer the UAV with the most remaining energy.\n\n"
            # "   【中文注释】非紧急任务应优先选择剩余能量最多的 UAV。\n\n"

            "4. **Future-Slot Reservation**:\n"
            # "【中文注释】4. **未来时隙预留**：\n"
            "   - If a UAV is heavily loaded in early time slots, reserve capacity "
            "for later slots by discouraging further assignment.\n"
            # "   【中文注释】若某 UAV 在早期时隙负载过重，应抑制继续分配以预留后续容量。\n"
        )

        instruction = {
            "iteration": {"iter": iter},
            "task_info": task_info,
            "uav_info": uav_info,
            "objective_instruction": (
                "Generate a **resource-aware objective function** that explicitly "
                "accounts for UAV energy budgets, compute capacity, and load balance. "
                "Follow the Resource-Aware Guidance provided above.\n"
                # "【中文注释】生成**资源感知型目标函数**，显式考虑 UAV 能量预算、算力上限与负载均衡。"
                # "请遵循上述资源感知指导。"
            ),
        }

        iter_text = self._iteration_block.format(
            iter=instruction["iteration"]["iter"],
            task_info=task_info,
            uav_info=uav_info,
        )
        instr_text = self._base_instruction.format(
            objective_instruction=instruction["objective_instruction"],
        )
        return (
            f"{self._scenario_block}"
            f"{resource_guidance}\n"
            f"{iter_text}"
            f"{instr_text}"
        )

