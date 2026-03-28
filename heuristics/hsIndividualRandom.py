"""Non-LLM objective generator for Edge-UAV HS baselines.

This module mirrors the hsIndividualEdgeUav interface but replaces LLM calls
with synthetic objective-code generation. It supports two baseline modes:

- ``parametric``: fixed objective structure with randomized weights.
- ``template``: small library of hand-written objective templates with weight
  mutations, used as a stronger no-LLM HS baseline.
"""

from __future__ import annotations

import json
import random
import re

from edge_uav.model.evaluator import INVALID_OUTPUT_PENALTY, evaluate_solution
from edge_uav.model.offloading import OffloadingModel
from edge_uav.model.precompute import (
    PrecomputeParams,
    make_initial_level2_snapshot,
    precompute_offloading_inputs,
)
from heuristics.hs_way_constants import (
    VALID_EDGE_UAV_WAYS,
    WAY_CROSS,
    WAY_MEMORY,
    WAY_PITCH,
    WAY_RANDOM,
)


_FORMAT_ERROR_SENTINEL = "Response format does not meet the requirements"
_OBJ_SUCCESS_MSG = "Your obj function is correct. Gurobi accepts your obj."
_META_RE = re.compile(
    r"# META: family=(?P<family>[a-z_]+) "
    r"alpha_scale=(?P<alpha>[0-9eE.+-]+) "
    r"gamma_scale=(?P<gamma>[0-9eE.+-]+) "
    r"offload_scale=(?P<offload>[0-9eE.+-]+)"
)
_TEMPLATE_FAMILIES = ("weighted_default", "split_delay", "urgency_bias")


class hsIndividualRandom:
    """Edge-UAV HS individual that samples objective code without LLM."""

    def __init__(self, configPara, scenario, *, shared_precompute=None):
        self.config = configPara
        self.scenario = scenario
        self.iter_idx = 0
        self.mode = getattr(configPara, "random_hs_mode", "parametric")

        if shared_precompute is not None:
            self.precompute_result = shared_precompute
        else:
            params = PrecomputeParams.from_config(configPara)
            snapshot = make_initial_level2_snapshot(scenario)
            self.precompute_result = precompute_offloading_inputs(
                scenario, params, snapshot
            )

        self.promptHistory = {
            "evaluation_score": None,
            "simulation_steps": {},
        }

    @staticmethod
    def _normalize_inputs(parent, way):
        if isinstance(parent, list):
            parent = parent[0] if parent else ""
        if isinstance(way, list):
            way = way[0] if way else WAY_RANDOM
        if parent is None:
            parent = ""
        if not way:
            way = WAY_RANDOM
        elif way != "default" and way not in VALID_EDGE_UAV_WAYS:
            raise ValueError(f"Unsupported edge_uav way: {way}")
        return parent, str(way)

    @staticmethod
    def _clamp_scale(value):
        return max(0.05, min(20.0, float(value)))

    @staticmethod
    def _sample_scale():
        return 10 ** random.uniform(-1.0, 1.0)

    @classmethod
    def _extract_parent_code(cls, parent):
        if isinstance(parent, dict):
            steps = parent.get("simulation_steps") or {}
            try:
                ordered = sorted(steps.keys(), key=lambda key: int(key), reverse=True)
            except (TypeError, ValueError):
                ordered = sorted(steps.keys(), reverse=True)
            for key in ordered:
                code = (steps.get(key) or {}).get("llm_response")
                if isinstance(code, str) and "def dynamic_obj_func" in code:
                    return code
            return ""
        if isinstance(parent, str):
            return parent
        return ""

    @classmethod
    def _extract_parent_meta(cls, parent):
        code = cls._extract_parent_code(parent)
        match = _META_RE.search(code)
        if not match:
            return None
        return {
            "family": match.group("family"),
            "alpha_scale": float(match.group("alpha")),
            "gamma_scale": float(match.group("gamma")),
            "offload_scale": float(match.group("offload")),
        }

    def _pick_family(self, parent_meta, way):
        if self.mode == "parametric":
            return "weighted_default"

        if parent_meta is None or way == WAY_RANDOM:
            return random.choice(_TEMPLATE_FAMILIES)
        if way == WAY_MEMORY:
            return parent_meta["family"]
        if way == WAY_PITCH:
            return random.choice(_TEMPLATE_FAMILIES)
        if way == WAY_CROSS:
            families = [family for family in _TEMPLATE_FAMILIES if family != parent_meta["family"]]
            return random.choice(families) if families else parent_meta["family"]
        return parent_meta["family"]

    def _pick_scales(self, parent, way):
        parent_meta = self._extract_parent_meta(parent)
        family = self._pick_family(parent_meta, way)

        if parent_meta is None or way == WAY_RANDOM:
            alpha_scale = self._sample_scale()
            gamma_scale = self._sample_scale()
            offload_scale = self._sample_scale()
        else:
            span = {
                WAY_MEMORY: 0.15,
                WAY_PITCH: 0.35,
                WAY_CROSS: 0.50,
            }.get(way, 0.20)
            alpha_scale = parent_meta["alpha_scale"] * (10 ** random.uniform(-span, span))
            gamma_scale = parent_meta["gamma_scale"] * (10 ** random.uniform(-span, span))
            offload_scale = parent_meta["offload_scale"] * (10 ** random.uniform(-span, span))
            if way == WAY_CROSS:
                offload_scale = self._sample_scale()

        return {
            "family": family,
            "alpha_scale": self._clamp_scale(alpha_scale),
            "gamma_scale": self._clamp_scale(gamma_scale),
            "offload_scale": self._clamp_scale(offload_scale),
        }

    @staticmethod
    def _build_objective_code(family, alpha_scale, gamma_scale, offload_scale):
        header = (
            f"# META: family={family} alpha_scale={alpha_scale:.12g} "
            f"gamma_scale={gamma_scale:.12g} offload_scale={offload_scale:.12g}\n"
            "def dynamic_obj_func(self):\n"
        )

        if family == "split_delay":
            body = f"""\
    cost_local = gb.quicksum(
        self.D_hat_local[i][t] / self.task[i].tau * self.x_local[i, t]
        for i in self.taskList
        for t in self.timeList
        if self.task[i].active[t] and (i, t) in self.x_local
    )
    cost_offload = gb.quicksum(
        self.D_hat_offload[i][j][t] / self.task[i].tau * self.x_offload[i, j, t]
        for i in self.taskList
        for j in self.uavList
        for t in self.timeList
        if self.task[i].active[t] and (i, j, t) in self.x_offload
    )
    cost_energy = gb.quicksum(
        self.E_hat_comp[j][i][t] / self.uav[j].E_max * self.x_offload[i, j, t]
        for i in self.taskList
        for j in self.uavList
        for t in self.timeList
        if self.task[i].active[t] and (i, j, t) in self.x_offload
    )
    self.model.setObjective(
        {alpha_scale:.12g} * cost_local
        + {offload_scale:.12g} * cost_offload
        + {gamma_scale:.12g} * cost_energy,
        gb.GRB.MINIMIZE,
    )
"""
        elif family == "urgency_bias":
            body = f"""\
    cost_delay = gb.quicksum(
        self.D_hat_local[i][t] / (self.task[i].tau * self.task[i].tau) * self.x_local[i, t]
        for i in self.taskList
        for t in self.timeList
        if self.task[i].active[t] and (i, t) in self.x_local
    ) + gb.quicksum(
        self.D_hat_offload[i][j][t] / (self.task[i].tau * self.task[i].tau) * self.x_offload[i, j, t]
        for i in self.taskList
        for j in self.uavList
        for t in self.timeList
        if self.task[i].active[t] and (i, j, t) in self.x_offload
    )
    cost_energy = gb.quicksum(
        self.E_hat_comp[j][i][t] / self.uav[j].E_max * self.x_offload[i, j, t]
        for i in self.taskList
        for j in self.uavList
        for t in self.timeList
        if self.task[i].active[t] and (i, j, t) in self.x_offload
    )
    offload_count = gb.quicksum(
        self.x_offload[i, j, t]
        for i in self.taskList
        for j in self.uavList
        for t in self.timeList
        if self.task[i].active[t] and (i, j, t) in self.x_offload
    )
    self.model.setObjective(
        {alpha_scale:.12g} * cost_delay
        + {gamma_scale:.12g} * cost_energy
        + {offload_scale:.12g} * offload_count,
        gb.GRB.MINIMIZE,
    )
"""
        else:
            body = f"""\
    cost_delay = gb.quicksum(
        self.D_hat_local[i][t] / self.task[i].tau * self.x_local[i, t]
        for i in self.taskList
        for t in self.timeList
        if self.task[i].active[t] and (i, t) in self.x_local
    ) + gb.quicksum(
        self.D_hat_offload[i][j][t] / self.task[i].tau * self.x_offload[i, j, t]
        for i in self.taskList
        for j in self.uavList
        for t in self.timeList
        if self.task[i].active[t] and (i, j, t) in self.x_offload
    )
    cost_energy = gb.quicksum(
        self.E_hat_comp[j][i][t] / self.uav[j].E_max * self.x_offload[i, j, t]
        for i in self.taskList
        for j in self.uavList
        for t in self.timeList
        if self.task[i].active[t] and (i, j, t) in self.x_offload
    )
    self.model.setObjective(
        {alpha_scale:.12g} * cost_delay + {gamma_scale:.12g} * cost_energy,
        gb.GRB.MINIMIZE,
    )
"""

        return header + body

    def runOptModel(self, parent, way):
        parent, way = self._normalize_inputs(parent, way)
        meta = self._pick_scales(parent, way)
        code = self._build_objective_code(**meta)

        full_info = {
            "llm_response": json.dumps({"obj_code": code}),
            "raw_llm_response": None,
            "response_format": "",
            "feasible": False,
            "solver_cost": float(INVALID_OUTPUT_PENALTY),
            "used_default_obj": False,
            "llm_status": "synthetic",
            "llm_error": None,
            "generator": "random_hs",
            **meta,
        }

        score = float(INVALID_OUTPUT_PENALTY)
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
                dynamic_obj_func=code,
            )
            feasible, cost = model.solveProblem()
            outputs = model.getOutputs()
            score = evaluate_solution(outputs, self.precompute_result, self.scenario)
            full_info["feasible"] = bool(feasible)
            full_info["solver_cost"] = float(cost)
            full_info["response_format"] = model.error_message or ""
            if model.error_message != _OBJ_SUCCESS_MSG:
                full_info["used_default_obj"] = True
                full_info["llm_status"] = "fallback"
            else:
                full_info["llm_status"] = "ok"
        except Exception as exc:
            full_info["used_default_obj"] = True
            full_info["llm_status"] = "solver_error"
            full_info["llm_error"] = str(exc)
            full_info["response_format"] = _FORMAT_ERROR_SENTINEL

        self.promptHistory["evaluation_score"] = float(score)
        self.promptHistory["simulation_steps"]["0"] = full_info
