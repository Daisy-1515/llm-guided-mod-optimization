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
from edge_uav.prompt.mod_prompt import EdgeUavModPrompts
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

    def __init__(self, configPara, scenario):
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

        # 预计算（一次性完成）
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
        return parent, str(way)

    def _synthesize_llm_response(self):
        """构造符合消费方期望的合成 JSON 字符串。"""
        return json.dumps({"obj_code": _EDGE_UAV_DEFAULT_OBJ})

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
        }

    def getNewPrompt(self, parent, way):
        """按 way 路由生成 prompt 并调用 LLM，返回 (response_text, full_info)。"""
        task_info, uav_info = self.format_scenario_info()
        full_info = self._make_default_full_info(task_info, uav_info)

        if way == "default":
            return full_info["llm_response"], full_info

        # LLM 路由
        if way == "way1":
            prompt_text = self.prompt.get_prompt_way1(
                self.iter_idx, task_info, uav_info,
            )
        elif way == "way2":
            prompt_text = self.prompt.get_prompt_way2(
                self.iter_idx, task_info, uav_info, parent,
            )
        elif way == "way3":
            prompt_text = self.prompt.get_prompt_way3(
                self.iter_idx, task_info, uav_info, parent,
            )
        elif way == "way4":
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
            return full_info["llm_response"], full_info

        full_info["raw_llm_response"] = raw_response
        full_info["llm_response"] = raw_response
        full_info["used_default_obj"] = False
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
        is_default = way not in {"way1", "way2", "way3", "way4"}

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

        # 3) 求解 Level-1 BLP
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

        try:
            feasible, cost = model.solveProblem()
            outputs = model.getOutputs()
            score = evaluate_solution(
                outputs, self.precompute_result, self.scenario,
            )
        except Exception as exc:
            print(f"[hsIndividualEdgeUav] solver exception: {exc}")
            feasible, cost, score = False, -1.0, float(INVALID_OUTPUT_PENALTY)

        # 4) 填充求解结果
        if extract_failed:
            # P1-2: 消费方 shrink_token_size 依赖此精确哨兵跳过提取
            full_info["response_format"] = self._FORMAT_ERROR_SENTINEL
        else:
            full_info["response_format"] = (
                model.error_message or "None Obj. Using default obj."
            )
        full_info["feasible"] = bool(feasible)
        full_info["solver_cost"] = float(cost)

        # P2-1 fix: 只有 solver 明确确认"Your obj function is correct"才算自定义成功
        if not full_info["used_default_obj"] and func is not None:
            if model.error_message != self._OBJ_SUCCESS_MSG:
                full_info["used_default_obj"] = True

        # 5) 记录到 promptHistory
        self.promptHistory["evaluation_score"] = float(score)
        self.promptHistory["simulation_steps"]["0"] = full_info
