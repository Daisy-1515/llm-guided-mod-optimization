"""
* File: hsPopulation.py
* Author: Yi
*
* created on 2025/01/27
"""
"""
@package hsPopulation.py
@brief This module handles the population updates of evolutionary solver.

@dependencies
- heuristics.hsIndividual
- heuristics.hsIndividualMultiCall
"""
import random
from joblib import Parallel, delayed
from concurrent.futures import ThreadPoolExecutor, as_completed
from heuristics.hsIndividual import hsIndividual
from heuristics.hsIndividualMultiCall import hsIndividualMultiCall
import heuristics.hsUtils as hsUtils
from heuristics.hs_way_constants import WAY_CROSS, WAY_MEMORY, WAY_PITCH, WAY_RANDOM

class hsPopulation:
    """
    @class hsPopulation
    @brief Manages the the population updates of evolutionary solver.
    """
    def __init__(self, configPara, scenario, timeout = 300, individual_type = "multi_call"):

        self.config = configPara
        self.scenario = scenario
        self.popsize = int(configPara.popSize)
        self.HMCR = configPara.HMCR  # Harmony Memory Considering Rate
        self.PAR = configPara.PAR   # Pitch Adjusting Rate

        # Individual class routing
        if individual_type == "multi_call":
            self.IndividualClass = hsIndividualMultiCall
        elif individual_type == "edge_uav":
            from heuristics.hsIndividualEdgeUav import hsIndividualEdgeUav
            self.IndividualClass = hsIndividualEdgeUav
        else:
            raise ValueError(f"Unsupported individual_type: {individual_type}")
        self._is_edge_uav = (individual_type == "edge_uav")

        # Edge UAV: 预计算一次，共享给所有个体（只读，线程安全）
        self._shared_precompute = None
        if self._is_edge_uav:
            from edge_uav.model.precompute import (
                PrecomputeParams,
                make_initial_level2_snapshot,
                precompute_offloading_inputs,
            )
            params = PrecomputeParams.from_config(configPara)
            snapshot = make_initial_level2_snapshot(scenario)
            self._shared_precompute = precompute_offloading_inputs(
                scenario, params, snapshot,
            )

        self.num_threads = configPara.popSize
        self.interval = configPara.interval
        self.steps = 1 if self._is_edge_uav else int(configPara.runTime / self.interval)
        self.timeout = timeout

        # Phase⑥ Step4: 热启动快照（用于 BCD 循环）
        self._best_snapshot = None  # 跨代传递的最优快照

    def _run_parallel(self, fn, *args):
        """并行执行 fn(*args) popsize 次，收集结果。"""
        with ThreadPoolExecutor(max_workers=self.num_threads) as executor:
            futures = [executor.submit(fn, *args) for _ in range(self.popsize)]
            return [
                future.result()
                for future in as_completed(futures, timeout=self.timeout)
            ]

    def initialize_population(self):
        try:
            return self._run_parallel(self.get_init_ind)
        except Exception as e:
            raise RuntimeError(f"initialize_population failed: {e}") from e

    def generate_new_population(self, pop):
        try:
            return self._run_parallel(self.get_new_ind, pop)
        except Exception as e:
            raise RuntimeError(f"generate_new_population failed: {e}") from e

    def _make_individual(self, parent_snapshot=None):
        """创建个体实例，edge_uav 模式下传入共享预计算结果和热启动快照。

        Args:
            parent_snapshot: 来自前代的最优快照（用于热启动）
        """
        if self._is_edge_uav:
            ind = self.IndividualClass(
                self.config, self.scenario,
                shared_precompute=self._shared_precompute,
            )
            # Phase⑥ Step4: 附加父快照用于 BCD 热启动
            if parent_snapshot is not None:
                ind._parent_snapshot = parent_snapshot
            return ind
        return self.IndividualClass(self.config, self.scenario)

    def _extract_parent_snapshot(self, parent_individual_prompt_history):
        """从父代个体的 promptHistory 中提取最优快照，用于下一代 BCD 热启动。

        Args:
            parent_individual_prompt_history: 父代个体返回的 promptHistory 字典

        Returns:
            Level2Snapshot 或 None
            - 若 BCD 启用且成功，返回 optimal_snapshot（用于热启动）
            - 若 BCD 未启用或失败，返回 None（降级至默认初始化）
        """
        try:
            # 遍历 simulation_steps，找到 bcd_meta
            sim_steps = parent_individual_prompt_history.get("simulation_steps", {})
            for step_key in sim_steps:
                step_data = sim_steps[step_key]
                bcd_meta = step_data.get("bcd_meta", {})

                if bcd_meta and "optimal_snapshot" in bcd_meta:
                    optimal_snapshot = bcd_meta["optimal_snapshot"]
                    # 保护性深拷贝，防止父代修改影响本代
                    from copy import deepcopy
                    return deepcopy(optimal_snapshot)

            # BCD 未启用或无快照，返回 None（触发默认初始化）
            return None
        except Exception as e:
            # 快照提取失败，降级至默认初始化
            print(f"[hsPopulation] _extract_parent_snapshot failed: {e}, using default initialization")
            return None

    def get_init_ind(self):

        ind = self._make_individual()
        if self._is_edge_uav:
            ind.runOptModel("", WAY_RANDOM)
        else:
            ind.runOptModel([""]*self.steps, [WAY_RANDOM] * self.steps)
        return ind.promptHistory

    def get_new_ind(self, pop):

        p, way, parent_snapshot = self.generate_new_harmony(pop)

        # Phase⑥ Step4: 如果有父代快照，传递用于 BCD 热启动
        ind = self._make_individual(parent_snapshot=parent_snapshot)

        # arrange prompt to get objective cost
        ind.runOptModel(p, way)

        return ind.promptHistory

    def generate_new_harmony(self, pop):
        """生成新和弦，返回 (prompt, way, parent_snapshot)。

        Phase⑥ Step4: 支持热启动快照传递
        """
        p = []
        way = []
        parent_snapshot = None  # Phase⑥ Step4: 热启动快照
        rd = max(int(self.popsize / 2), 0)

        for t in range(self.steps):
            if random.random() >= self.HMCR:
                # Random generation
                p.append("")
                way.append(WAY_RANDOM)
            else:
                # Memory consideration
                idx = random.randint(0, rd - 1) if rd > 2 else 0
                print(f"[Harmony] step {t:02d}: selected individual idx={idx}, popsize={self.popsize})")
                ind = pop[idx]

                # Phase⑥ Step4: 从父代提取最优快照（用于 BCD 热启动）
                if self._is_edge_uav and t == 0:  # Edge UAV 只有 single step
                    parent_snapshot = self._extract_parent_snapshot(ind)

                parent = self.shrink_token_size(ind)
                if random.random() > self.PAR:
                    # prompt way 2
                    p.append(parent)
                    way.append(WAY_MEMORY)
                else:
                    # Pitch adjustment: Edge UAV may sample way4
                    p.append(parent)
                    if self._is_edge_uav:
                        way.append(random.choice([WAY_PITCH, WAY_CROSS]))
                    else:
                        way.append(WAY_PITCH)

        # Edge UAV: single step → unwrap to scalar
        if self._is_edge_uav:
            return p[0], way[0], parent_snapshot
        return p, way, parent_snapshot

    def shrink_token_size(self, p):
        shrinked_p = {}
        shrinked_p['evaluation_score'] = p['evaluation_score']
        shrinked_p['simulation_steps'] = {}

        try:
            for key in p['simulation_steps'].keys():

                shrinked_p['simulation_steps'][key] = {}

                obj_code = " "
                llm_response_str = p['simulation_steps'][key]['llm_response']
                if p['simulation_steps'][key]['response_format'] != "Response format does not meet the requirements" and not llm_response_str.startswith("Model too busy"):
                    #obj_code = self.extract_obj_code(llm_response_str)
                    obj_code = hsUtils.extract_code_hsPopulation(llm_response_str)

                shrinked_p['simulation_steps'][key]['llm_response'] = obj_code
                shrinked_p['simulation_steps'][key]['response_format'] = p['simulation_steps'][key]['response_format'] 

        except Exception as e:
            raise RuntimeError(f"shrink_token_size failed: {e}\n{shrinked_p}") from e

        return shrinked_p
