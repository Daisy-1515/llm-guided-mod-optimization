"""Edge UAV 单个体运行器 — Harmony Search 框架的 Edge UAV 桥接层。

鸭子类型兼容 hsPopulation：提供 runOptModel(parent, way) + promptHistory。

与原 hsIndividualMultiCall 的关键差异：
  - Edge UAV 只有 1 个 simulation step（step "0"），无多步仿真循环
  - 目标函数由 OffloadingModel（Level-1 BLP）求解
  - 评分由固定评估器 evaluate_solution 计算（非 objVal）
"""

from __future__ import annotations

import json
from pathlib import Path

from edge_uav.model.evaluator import INVALID_OUTPUT_PENALTY, evaluate_solution
from edge_uav.model.offloading import OffloadingModel
from edge_uav.model.precompute import (
    PrecomputeParams,
    make_initial_level2_snapshot,
    precompute_offloading_inputs,
)
from edge_uav.model.trajectory_opt import TrajectoryOptParams
from edge_uav.model.bcd_loop import run_bcd_loop, BCDResult
from edge_uav.prompt.mod_prompt import EdgeUavModPrompts
from heuristics.hs_way_constants import (
    VALID_EDGE_UAV_WAYS,
    WAY_CROSS,
    WAY_MEMORY,
    WAY_PITCH,
    WAY_RANDOM,
)
from heuristics.hsUtils import extract_code_hsIndiv


# ---------------------------------------------------------------------------
# 模块常量：默认目标函数代码
# ---------------------------------------------------------------------------
# Source: OffloadingModel.default_dynamic_obj_func (offloading.py:303)
# 函数名改为 dynamic_obj_func 以兼容 format_best_ind 的 "def dynamic_obj_func" 检查
_EDGE_UAV_DEFAULT_OBJ = """\
def dynamic_obj_func(self):
    cost1 = gb.quicksum(
        self.alpha * self.D_hat_local[i][t] / self.task[i].tau
        * self.x_local[i, t]
        for i in self.taskList
        for t in self.timeList
        if self.task[i].active[t] and (i, t) in self.x_local
    ) + gb.quicksum(
        self.alpha * self.D_hat_offload[i][j][t] / self.task[i].tau
        * self.x_offload[i, j, t]
        for i in self.taskList
        for j in self.uavList
        for t in self.timeList
        if self.task[i].active[t] and (i, j, t) in self.x_offload
    )

    cost2 = gb.quicksum(
        self.gamma_w * self.E_hat_comp[j][i][t] / self.uav[j].E_max
        * self.x_offload[i, j, t]
        for i in self.taskList
        for j in self.uavList
        for t in self.timeList
        if self.task[i].active[t] and (i, j, t) in self.x_offload
    )

    costs = [cost1, cost2]
    weights = [1, 1]
    self.model.setObjective(
        gb.quicksum(w * c for w, c in zip(costs, weights)),
        gb.GRB.MINIMIZE,
    )
"""


class hsIndividualEdgeUav:
    """Edge UAV 场景下的 Harmony Search 单个体。

    鸭子类型接口：
        - runOptModel(parent, way)  — 主入口
        - promptHistory             — 种群排序 / shrink / format_best_ind 读取
    """

    def __init__(self, configPara, scenario, *, shared_precompute=None):
        self.config = configPara
        self.scenario = scenario
        self.iter_idx = 0

        # Prompt 模板
        model_path = (
            Path(__file__).resolve().parents[1]
            / "edge_uav" / "model" / "offloading.py"
        )
        self.prompt = EdgeUavModPrompts(str(model_path))
        self.prompt.set_scenario_info(
            scenario.tasks, scenario.uavs, scenario.time_slots,
        )
        self.prompt.refresh_scenario_block()

        # 预计算：外部传入时直接引用（避免重复计算），否则自行计算
        if shared_precompute is not None:
            self.params = None
            self.snapshot = None
            self.precompute_result = shared_precompute
        else:
            self.params = PrecomputeParams.from_config(configPara)
            self.snapshot = make_initial_level2_snapshot(scenario)
            self.precompute_result = precompute_offloading_inputs(
                scenario, self.params, self.snapshot,
            )

        # LLM API（延迟初始化）
        self._api = None

        # 种群读取的核心字段
        self.promptHistory = {
            "evaluation_score": None,
            "simulation_steps": {},
        }

    # ------------------------------------------------------------------
    # 内部工具
    # ------------------------------------------------------------------

    def _ensure_api(self):
        """延迟导入并初始化 LLM API，避免测试时触发网络依赖。"""
        if self._api is None:
            from llmAPI.llmInterface import InterfaceAPI
            self._api = InterfaceAPI(self.config)
        return self._api

    @staticmethod
    def _normalize_inputs(parent, way):
        """将 hsPopulation 可能传入的 list 解包为 scalar。"""
        if isinstance(parent, list):
            parent = parent[0] if parent else ""
        if isinstance(way, list):
            way = way[0] if way else "default"
        if parent is None:
            parent = ""
        if not way:
            way = "default"
        elif way != "default" and way not in VALID_EDGE_UAV_WAYS:
            raise ValueError(f"不支持的 edge_uav 方式: {way}")
        return parent, str(way)

    def _synthesize_llm_response(self):
        """构造符合消费方期望的合成 JSON 字符串。"""
        return json.dumps({"obj_code": _EDGE_UAV_DEFAULT_OBJ})

    # ------------------------------------------------------------------
    # Phase⑥ Step4 BCD 循环集成：参数初始化助手方法
    # ------------------------------------------------------------------

    def _initialize_bcd_params(self):
        """初始化 BCD 循环所需的参数。

        处理 4 种参数组合情况：
          分支 A: shared_precompute=True (self.params=None)
          分支 B: shared_precompute=False (self.params 已设置)
          分支 C: 多代热启动 (self._parent_snapshot 可用)

        Returns:
            (PrecomputeParams, TrajectoryOptParams, Level2Snapshot)

        Raises:
            ValueError: 若配置无效或参数初始化失败
        """
        # Case A: shared_precompute=True，需要从 config 构造参数
        if self.params is None:
            try:
                params = PrecomputeParams.from_config(self.config)
            except Exception as e:
                raise ValueError(f"BCD param init: PrecomputeParams.from_config failed: {e}")
            initial_snapshot = make_initial_level2_snapshot(self.scenario)
        # Case B: shared_precompute=False，已有 self.params
        else:
            params = self.params
            # Case C: 检查是否有父代热启动快照
            if hasattr(self, '_parent_snapshot') and self._parent_snapshot is not None:
                initial_snapshot = self._parent_snapshot
            else:
                initial_snapshot = self.snapshot

        # 构造轨迹优化参数 (从 config 提取)
        traj_params = self._create_trajectory_opt_params()

        return params, traj_params, initial_snapshot

    def _create_trajectory_opt_params(self):
        """从 config 提取轨迹优化参数。

        Returns:
            TrajectoryOptParams 实例

        Raises:
            ValueError: 若配置缺少必要参数
        """
        required_attrs = ['eta_1', 'eta_2', 'eta_3', 'eta_4', 'v_tip']
        for attr in required_attrs:
            if not hasattr(self.config, attr):
                raise ValueError(
                    f"BCD trajectory params: config missing required attribute '{attr}'"
                )

        # 映射：config.v_traj_max → v_max
        v_max = float(
            getattr(
                self.config,
                'v_traj_max',
                getattr(self.config, 'v_U_max', getattr(self.config, 'v_max', 30.0)),
            )
        )

        # 映射：config.d_safe_traj → d_safe
        d_safe = float(getattr(self.config, 'd_safe_traj', getattr(self.config, 'd_safe', 5.0)))

        return TrajectoryOptParams(
            eta_1=float(self.config.eta_1),
            eta_2=float(self.config.eta_2),
            eta_3=float(self.config.eta_3),
            eta_4=float(self.config.eta_4),
            v_tip=float(self.config.v_tip),
            v_max=v_max,
            d_safe=d_safe,
        )

    def _adapt_bcd_result_to_legacy(self, bcd_result, offloading_outputs, precompute_result):
        """将 BCDResult 适配为遗留接口格式。

        输入：
            bcd_result: BCDResult 实例
            offloading_outputs: dict，Level-1 卸载决策
            precompute_result: PrecomputeResult

        返回：
            (feasible, cost, full_info_bcd_meta)

        其中 full_info_bcd_meta 包含：
            - bcd_converged: bool
            - bcd_iterations: int
            - bcd_cost_history: list[float]
            - solution_details: dict
            - optimal_snapshot: Level2Snapshot (用于下一代热启动)
        """
        feasible = bcd_result.converged
        cost = bcd_result.total_cost

        full_info_bcd_meta = {
            "bcd_converged": bool(bcd_result.converged),
            "bcd_iterations": int(bcd_result.bcd_iterations),
            "bcd_cost_history": list(bcd_result.cost_history),
            "solution_details": dict(bcd_result.solution_details) if bcd_result.solution_details else {},
            "optimal_snapshot": bcd_result.snapshot,  # Phase⑥ Step4 Day 2: 热启动快照
            "offloading_error_message": bcd_result.offloading_error_message,
            "used_default_obj": bool(bcd_result.used_default_obj),
            "objective_acceptance_status": bcd_result.objective_acceptance_status,
        }

        return feasible, cost, full_info_bcd_meta

    # ------------------------------------------------------------------
    # 场景信息格式化
    # ------------------------------------------------------------------

    def format_scenario_info(self):
        """返回 (task_info_str, uav_info_str) 供 prompt 模板使用。"""
        diag = self.precompute_result.diagnostics
        ratio = diag.get("offload_feasible_ratio", 0.0)

        task_lines = [
            "--- Task Info ---",
            f"active_task_slots={diag.get('active_task_slots', 'N/A')}",
            f"offload_feasible_ratio={ratio:.4f}",
        ]
        for i in sorted(self.scenario.tasks):
            t = self.scenario.tasks[i]
            active_cnt = sum(
                1 for s in self.scenario.time_slots if t.active.get(s, False)
            )
            task_lines.append(
                f"Task {i}: pos={t.pos}, tau={float(t.tau):.3f}, "
                f"F={float(t.F):.3e}, f_local={float(t.f_local):.3e}, "
                f"active_slots={active_cnt}"
            )

        uav_lines = ["--- UAV Info ---"]
        for j in sorted(self.scenario.uavs):
            u = self.scenario.uavs[j]
            uav_lines.append(
                f"UAV {j}: pos={u.pos}, pos_final={u.pos_final}, "
                f"E_max={float(u.E_max):.3f}, f_max={float(u.f_max):.3e}, "
                f"N_max={u.N_max}"
            )

        return "\n".join(task_lines), "\n".join(uav_lines)

    # ------------------------------------------------------------------
    # Prompt 生成
    # ------------------------------------------------------------------

    def _make_default_full_info(self, task_info, uav_info):
        """构造 default 路由（或异常回退）的 full_info 模板。"""
        return {
            "task_info": task_info,
            "uav_info": uav_info,
            "llm_response": self._synthesize_llm_response(),
            "raw_llm_response": None,
            "response_format": "",
            "feasible": False,
            "solver_cost": float(INVALID_OUTPUT_PENALTY),
            "used_default_obj": True,
            "llm_status": "default",
            "llm_error": None,
        }

    def getNewPrompt(self, parent, way):
        """按 way 路由生成 prompt 并调用 LLM，返回 (response_text, full_info)。"""
        task_info, uav_info = self.format_scenario_info()
        full_info = self._make_default_full_info(task_info, uav_info)

        if way == "default":
            return full_info["llm_response"], full_info

        # LLM 路由
        if way == WAY_RANDOM:
            prompt_text = self.prompt.get_prompt_way1(
                self.iter_idx, task_info, uav_info,
            )
        elif way == WAY_MEMORY:
            prompt_text = self.prompt.get_prompt_way2(
                self.iter_idx, task_info, uav_info, parent,
            )
        elif way == WAY_PITCH:
            prompt_text = self.prompt.get_prompt_way3(
                self.iter_idx, task_info, uav_info, parent,
            )
        elif way == WAY_CROSS:
            prompt_text = self.prompt.get_prompt_way4(
                self.iter_idx, task_info, uav_info,
            )
        else:
            return full_info["llm_response"], full_info

        # P1-3 fix: 保护 API 调用，异常时回退 default
        try:
            raw_response = str(self._ensure_api().getResponse(prompt_text))
        except Exception as exc:
            print(f"[hsIndividualEdgeUav] LLM API error: {exc}")
            full_info["llm_status"] = "api_error"
            full_info["llm_error"] = str(exc)
            return full_info["llm_response"], full_info

        full_info["raw_llm_response"] = raw_response
        full_info["llm_response"] = raw_response
        full_info["used_default_obj"] = False
        full_info["llm_status"] = "ok"
        return raw_response, full_info

    # ------------------------------------------------------------------
    # 主入口
    # ------------------------------------------------------------------

    # 消费方 shrink_token_size 依赖此精确字符串判断格式是否有效
    _FORMAT_ERROR_SENTINEL = "Response format does not meet the requirements"
    # 消费方 setupObj 成功时设置此精确字符串
    _OBJ_SUCCESS_MSG = "Your obj function is correct. Gurobi accepts your obj."

    def runOptModel(self, parent, way):
        """normalize → prompt → extract → solve → evaluate → record。"""
        parent, way = self._normalize_inputs(parent, way)
        is_default = way not in VALID_EDGE_UAV_WAYS

        # 1) 获取 prompt / LLM 回复
        response_text, full_info = self.getNewPrompt(parent, way)

        # 2) 提取目标函数代码
        func = None
        extract_failed = False
        if not is_default:
            extracted = extract_code_hsIndiv(response_text)
            # extract_code_hsIndiv 失败时返回 " "（空格）
            if isinstance(extracted, str) and extracted.strip():
                func = extracted
                # P1-1 fix: 规范化 llm_response 为 JSON（hsDiversitySorting 兼容）
                full_info["llm_response"] = json.dumps({"obj_code": extracted})
            else:
                # P1-2 fix: 提取失败 → 替换为合成 JSON + 哨兵值
                extract_failed = True
                full_info["llm_response"] = self._synthesize_llm_response()
                full_info["used_default_obj"] = True
                full_info["llm_status"] = "parse_error"
                full_info["llm_error"] = f"extract_code_hsIndiv returned empty for way={way}"

        # 3) 求解：使用 BCD 循环（Level 1+2a+2b）或降级至 Level 1
        bcd_enabled = getattr(self.config, 'use_bcd_loop', False)
        feasible, cost, score = False, -1.0, float(INVALID_OUTPUT_PENALTY)
        bcd_meta = {}

        if bcd_enabled:
            # Phase⑥ Step4：尝试 BCD 循环集成
            try:
                params, traj_params, initial_snapshot = self._initialize_bcd_params()
                bcd_result = run_bcd_loop(
                    scenario=self.scenario,
                    config=self.config,
                    params=params,
                    traj_params=traj_params,
                    dynamic_obj_func=func,
                    initial_snapshot=initial_snapshot,
                    max_bcd_iter=getattr(self.config, 'bcd_max_iter', 5),
                    eps_bcd=getattr(self.config, 'bcd_eps', 1e-3),
                    cost_rollback_delta=getattr(self.config, 'bcd_rollback_delta', 0.05),
                    max_rollbacks=getattr(self.config, 'bcd_max_rollbacks', 2),
                )
                # 适配返回值
                feasible, cost, bcd_meta = self._adapt_bcd_result_to_legacy(
                    bcd_result, bcd_result.offloading_outputs, self.precompute_result
                )
                # 在评分前，基于最终的 BCD 快照重新计算预计算张量。
                # 否则 evaluation_score 将仍与初始快照关联，从而掩盖 BCD 的优化效果。
                final_precompute_result = precompute_offloading_inputs(
                    self.scenario,
                    params,
                    bcd_result.snapshot,
                    mu=None,
                    active_only=True,
                )
                # 重新评分（使用 BCD 最优快照）
                score = evaluate_solution(
                    bcd_result.offloading_outputs,
                    final_precompute_result,
                    self.scenario,
                )
                full_info["bcd_enabled"] = True
                full_info["bcd_meta"] = bcd_meta
                full_info["final_precompute_diagnostics"] = (
                    final_precompute_result.diagnostics
                )
                full_info["response_format"] = (
                    bcd_result.offloading_error_message or "BCD 目标状态不可用"
                )
                full_info["used_default_obj"] = bool(bcd_result.used_default_obj)

            except Exception as bcd_exc:
                # BCD 失败：降级至 Level 1（保留异常记录）
                print(f"[hsIndividualEdgeUav] BCD loop failed: {bcd_exc}, falling back to Level 1")
                full_info["bcd_enabled"] = True
                full_info["bcd_error"] = str(bcd_exc)

                # Level 1 降级求解
                try:
                    model = OffloadingModel(
                        tasks=self.scenario.tasks,
                        uavs=self.scenario.uavs,
                        time_list=self.scenario.time_slots,
                        D_hat_local=self.precompute_result.D_hat_local,
                        D_hat_offload=self.precompute_result.D_hat_offload,
                        E_hat_comp=self.precompute_result.E_hat_comp,
                        alpha=getattr(self.config, "alpha", 1.0),
                        gamma_w=getattr(self.config, "gamma_w", 1.0),
                        dynamic_obj_func=func,
                    )
                    feasible, cost = model.solveProblem()
                    outputs = model.getOutputs()
                    score = evaluate_solution(
                        outputs, self.precompute_result, self.scenario,
                    )
                except Exception as fallback_exc:
                    print(f"[hsIndividualEdgeUav] Level 1 fallback also failed: {fallback_exc}")
                    feasible, cost, score = False, -1.0, float(INVALID_OUTPUT_PENALTY)
        else:
            # use_bcd_loop=False：仅 Level 1（原始逻辑）
            try:
                model = OffloadingModel(
                    tasks=self.scenario.tasks,
                    uavs=self.scenario.uavs,
                    time_list=self.scenario.time_slots,
                    D_hat_local=self.precompute_result.D_hat_local,
                    D_hat_offload=self.precompute_result.D_hat_offload,
                    E_hat_comp=self.precompute_result.E_hat_comp,
                    alpha=getattr(self.config, "alpha", 1.0),
                    gamma_w=getattr(self.config, "gamma_w", 1.0),
                    dynamic_obj_func=func,
                )
                feasible, cost = model.solveProblem()
                outputs = model.getOutputs()
                score = evaluate_solution(
                    outputs, self.precompute_result, self.scenario,
                )
                full_info["bcd_enabled"] = False
            except Exception as exc:
                print(f"[hsIndividualEdgeUav] Level 1 solver exception: {exc}")
                feasible, cost, score = False, -1.0, float(INVALID_OUTPUT_PENALTY)
                full_info["bcd_enabled"] = False

        # 4) 填充求解结果
        if extract_failed:
            # P1-2: 消费方 shrink_token_size 依赖此精确哨兵跳过提取
            full_info["response_format"] = self._FORMAT_ERROR_SENTINEL
        else:
            if bcd_enabled and not bcd_meta:
                # BCD 启用但已降级，show 原始错误信息
                full_info["response_format"] = "BCD fallback to Level 1"
            elif bcd_enabled and bcd_meta:
                # BCD 成功路径已经从 BCDResult 注入了真实的目标采用状态，
                # 这里不要再用不存在的本地 Level-1 model 覆盖掉它。
                pass
            else:
                # 原始 Level 1 响应格式
                full_info["response_format"] = (
                    model.error_message if 'model' in locals() and hasattr(model, 'error_message')
                    else "无目标函数。使用默认目标。"
                )
        full_info["feasible"] = bool(feasible)
        full_info["solver_cost"] = float(cost)

        # P2-1 fix: 只有 solver 明确确认"Your obj function is correct"才算自定义成功
        if not full_info["used_default_obj"] and func is not None:
            if 'model' in locals() and hasattr(model, 'error_message'):
                if model.error_message != self._OBJ_SUCCESS_MSG:
                    full_info["used_default_obj"] = True

        # 5) 记录到 promptHistory
        self.promptHistory["evaluation_score"] = float(score)
        self.promptHistory["simulation_steps"]["0"] = full_info
