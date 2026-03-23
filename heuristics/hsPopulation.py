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

    def _make_individual(self):
        """创建个体实例，edge_uav 模式下传入共享预计算结果。"""
        if self._is_edge_uav:
            return self.IndividualClass(
                self.config, self.scenario,
                shared_precompute=self._shared_precompute,
            )
        return self.IndividualClass(self.config, self.scenario)

    def get_init_ind(self):

        ind = self._make_individual()
        if self._is_edge_uav:
            ind.runOptModel("", WAY_RANDOM)
        else:
            ind.runOptModel([""]*self.steps, [WAY_RANDOM] * self.steps)
        return ind.promptHistory

    def get_new_ind(self, pop):

        ind = self._make_individual()
        p, way = self.generate_new_harmony(pop)
        # arrange prompt to get objective cost
        ind.runOptModel(p, way)

        return ind.promptHistory

    def generate_new_harmony(self, pop):
        p = []
        way = []
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
            return p[0], way[0]
        return p, way

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
