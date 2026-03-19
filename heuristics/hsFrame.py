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
import json
import os 
class HarmonySearchSolver:
    """
    @class HarmonySearchSolver
    @brief Manages the prompt evolution framework.
    """
    def __init__(self, configPara, scenarioInfo, individual_type="multi_call"):
        print("Harmony Search Solver Initialized")
        self.popsize = configPara.popSize
        self.max_generations = configPara.iteration

        self.pop = hsPopulation(configPara, scenarioInfo, individual_type=individual_type)
        self.sort = hsSorting()

    def save_population(self, pop, iteration):
        os.makedirs("./discussion", exist_ok=True)
        filename = "./discussion/population_result_"+str(iteration)+".json"
        with open(filename, 'w') as f:
            json.dump(pop, f, indent=4)
    
    def combine_population(self, pop1, pop2):
        return pop1+pop2

    def run(self):
        pop = self.pop.initialize_population()
        sortPop = self.sort.sort_population(pop, self.popsize)
        self.save_population(sortPop, 0)

        for gen in range(self.max_generations-1):
            newPop = self.pop.generate_new_population(sortPop)
            comPop = self.combine_population(sortPop, newPop)
            sortPop = self.sort.sort_population(comPop, self.popsize)
            self.save_population(sortPop, gen+1)

        print("Optimization complete")

# Example usage
if __name__ == "__main__":
    solver = HarmonySearchSolver()
    solver.run()