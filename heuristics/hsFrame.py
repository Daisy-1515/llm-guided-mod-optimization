"""
* File: hsFrame.py
* Author: Yi 
*
* created on 2025/01/27
"""
"""
@package hsFrame.py
@brief This module handles the framework of evolutionary solver.

@dependencies
- heuristics.hsPopulation
- heuristics.hsSorting / heuristics.hsDiversitySorting
"""
from heuristics.hsPopulation import hsPopulation
from heuristics.hsSorting import hsSorting, hsDiversitySorting
import datetime
import json
import os


class HarmonySearchSolver:
    """
    @class HarmonySearchSolver
    @brief Manages the prompt evolution framework.
    """
    def __init__(self, configPara, scenarioInfo, individual_type="multi_call"):
        self.popsize = configPara.popSize
        self.max_generations = configPara.iteration

        # B1: run_id 归档 — 每次运行写入独立子目录
        self.run_id = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        self.out_dir = os.path.join("discussion", self.run_id)
        os.makedirs(self.out_dir, exist_ok=True)

        self.pop = hsPopulation(configPara, scenarioInfo, individual_type=individual_type)
        self.sort = hsSorting()
        print(f"[HS] Solver initialized  run_id={self.run_id}  out={self.out_dir}")

    def save_population(self, pop, iteration):
        os.makedirs(self.out_dir, exist_ok=True)
        filename = os.path.join(self.out_dir, f"population_result_{iteration}.json")
        with open(filename, 'w') as f:
            json.dump(pop, f, indent=4)
    
    def combine_population(self, pop1, pop2):
        return pop1+pop2

    def _summarize_gen(self, gen_label, pop):
        """B2: 打印一代个体的 LLM 状态统计。"""
        total = len(pop)
        ok = 0
        feasible = 0
        custom_obj_ok = 0
        for ind in pop:
            step = (ind.get("simulation_steps") or {}).get("0") or {}
            status = step.get("llm_status", "n/a")
            used_default = step.get("used_default_obj", True)
            is_feasible = step.get("feasible", False)
            if status == "ok":
                ok += 1
            if is_feasible:
                feasible += 1
            if status == "ok" and not used_default:
                custom_obj_ok += 1
        best = min((ind["evaluation_score"] for ind in pop), default=None)
        print(f"[HS] {gen_label} stats: {ok}/{total} ok, "
              f"{custom_obj_ok}/{total} custom_obj, "
              f"{feasible}/{total} feasible, best={best}")

    def run(self):
        print(f"[HS] Gen 0: evaluating {self.popsize} individuals ...")
        pop = self.pop.initialize_population()
        sortPop = self.sort.sort_population(pop, self.popsize)
        self.save_population(sortPop, 0)
        self._summarize_gen("Gen 0", sortPop)

        for gen in range(self.max_generations - 1):
            gen_num = gen + 1
            print(f"[HS] Gen {gen_num}: evaluating {self.popsize} individuals ...")
            newPop = self.pop.generate_new_population(sortPop)
            comPop = self.combine_population(sortPop, newPop)
            sortPop = self.sort.sort_population(comPop, self.popsize)
            self.save_population(sortPop, gen_num)
            self._summarize_gen(f"Gen {gen_num}", sortPop)

        # B3: 首跑统计摘要
        best_score = sortPop[0]["evaluation_score"] if sortPop else None
        print(f"[HS] Optimization complete  out={self.out_dir}  best_score={best_score}")

# Example usage
if __name__ == "__main__":
    solver = HarmonySearchSolver()
    solver.run()