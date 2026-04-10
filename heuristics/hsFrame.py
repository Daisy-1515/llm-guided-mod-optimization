"""
* 文件: hsFrame.py
* 作者: Yi 
*
* 创建日期: 2025/01/27
"""
"""
@package hsFrame.py
@brief 此模块处理进化求解器的框架。

@依赖项
- heuristics.hsPopulation
- heuristics.hsSorting / heuristics.hsDiversitySorting
"""
from heuristics.hsPopulation import hsPopulation
from heuristics.hsSorting import hsSorting, hsDedupSorting, hsDiversitySorting
import datetime
import json
import os


class HarmonySearchSolver:
    """
    @class HarmonySearchSolver
    @brief 管理提示词 (Prompt) 进化框架。
    """
    def __init__(self, configPara, scenarioInfo, individual_type="multi_call"):
        self.popsize = configPara.popSize
        self.max_generations = configPara.iteration

        # B1: run_id 归档 — 每次运行写入独立子目录
        self.run_id = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        self.out_dir = os.path.join("discussion", self.run_id)
        os.makedirs(self.out_dir, exist_ok=True)

        self.pop = hsPopulation(configPara, scenarioInfo, individual_type=individual_type)
        self.sort = hsDedupSorting(max_same_score=2)
        self.evaluation_history = []
        self.generation_history = []
        print(f"[HS] Solver initialized  run_id={self.run_id}  out={self.out_dir}")

    @staticmethod
    def _json_default(obj):
        from dataclasses import asdict, is_dataclass
        if is_dataclass(obj):
            return asdict(obj)
        raise TypeError(f"Object of type {type(obj).__name__} is not JSON serializable")

    def save_population(self, pop, iteration):
        os.makedirs(self.out_dir, exist_ok=True)
        filename = os.path.join(self.out_dir, f"population_result_{iteration}.json")
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(pop, f, indent=4, default=self._json_default, ensure_ascii=False)
    
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
        self.evaluation_history.append({"generation": 0, "individuals": pop})
        sortPop = self.sort.sort_population(pop, self.popsize)
        self.generation_history.append({"generation": 0, "survivors": sortPop})
        self.save_population(sortPop, 0)
        self._summarize_gen("Gen 0", sortPop)

        for gen in range(self.max_generations - 1):
            gen_num = gen + 1
            print(f"[HS] Gen {gen_num}: evaluating {self.popsize} individuals ...")
            newPop = self.pop.generate_new_population(sortPop)
            self.evaluation_history.append(
                {"generation": gen_num, "individuals": newPop}
            )
            comPop = self.combine_population(sortPop, newPop)
            sortPop = self.sort.sort_population(comPop, self.popsize)
            self.generation_history.append(
                {"generation": gen_num, "survivors": sortPop}
            )
            self.save_population(sortPop, gen_num)
            self._summarize_gen(f"Gen {gen_num}", sortPop)

        # B3: 首跑统计摘要 + 保存最终种群
        best_score = sortPop[0]["evaluation_score"] if sortPop else None
        print(f"[HS] Optimization complete  out={self.out_dir}  best_score={best_score}")

        # Phase⑥ Step4: 保存最终种群供后续访问
        self.final_population = sortPop
        return sortPop

# 示例用法
if __name__ == "__main__":
    solver = HarmonySearchSolver()
    solver.run()
