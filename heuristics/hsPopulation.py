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
import sys

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

        self.num_threads = configPara.popSize
        self.interval = configPara.interval
        self.steps = 1 if self._is_edge_uav else int(configPara.runTime / self.interval)
        self.timeout = timeout

    def initialize_population(self):
        results = []
        try:
            with ThreadPoolExecutor(max_workers=self.num_threads) as executor:
                # Submit tasks to the thread pool
                futures = [executor.submit(self.get_init_ind) for _ in range(self.popsize)]
                results = [future.result() for future in as_completed(futures)]
        except Exception as e:
            print(f"Error: {e}")
            print("Parallel time out .")
            sys.exit(0)

        return results

    def generate_new_population(self, pop):
        results = []
        print("******************start new iteration***********************")

        try:
            with ThreadPoolExecutor(max_workers=self.num_threads) as executor:
                # Submit tasks to the thread pool
                futures = [executor.submit(self.get_new_ind, pop) for _ in range(self.popsize)]
                results = [future.result() for future in as_completed(futures)]
        except Exception as e:
            print(f"Error: {e}")
            print("Parallel time out .")
            sys.exit(0)

        return results

    def get_init_ind(self):

        ind = self.IndividualClass(self.config, self.scenario)
        if self._is_edge_uav:
            ind.runOptModel("", "way1")
        else:
            ind.runOptModel([""]*self.steps, ["way1"] * self.steps)
        return ind.promptHistory

    def get_new_ind(self, pop):

        ind = self.IndividualClass(self.config, self.scenario)
        p, way = self.generate_new_harmony(pop)
        # arrange prompt to get objective cost
        print("******************start new run***********************")
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
                way.append("way1")
            else:
                # Memory consideration
                idx = random.randint(0, rd - 1) if rd > 2 else 0
                print(f"[Harmony] step {t:02d}: selected individual idx={idx}, popsize={self.popsize})")
                ind = pop[idx] 
                parent = self.shrink_token_size(ind)
                if random.random() > self.PAR:
                    # prompt way 2
                    p.append(parent)
                    way.append("way2")
                else:
                    # Pitch adjustment: Edge UAV may sample way4
                    p.append(parent)
                    if self._is_edge_uav:
                        way.append(random.choice(["way3", "way4"]))
                    else:
                        way.append("way3")

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
            print(f"Error: {e}")
            print(f"{shrinked_p}")
            sys.exit(0)

        return shrinked_p
