"""
* File: modPrompt.py
* Author: Yi
*
* created on 2025/02/03
"""

"""
@package modPrompt.py
@brief This module handles the prompts.

@dependencies
- prompt.basicPrompt
"""

from prompt.basicPrompt import basicPrompts

class modPrompts(basicPrompts):
    """
    @class modPrompts
    @brief Manages prompts under different ways.
    """
    def __init__(self, mapPath, modelPath, enableMemory=False, enableFuture=False):
        super().__init__(mapPath, modelPath, enableMemory, enableFuture)
        self._setup_template_components()
        
    def _setup_template_components(self):
        # Base template components
        if self.llmHasMemory == True:
            self._scenario_block = ()
        else:
            self._scenario_block = (
                f"{self.prompt_scenario}\n"
                "Below is the static map information:"
                f"{self.prompt_static_map_info}\n"
                #f"{self.prompt_data_format}\n"
                "Below is the level 1 model information, your goal is to change function [dynamic_obj_func(self)]:"
                f"{self.prompt_init_level1model}\n\n"
            )
        
        self._iteration_block = (
            "This time is the {iter}th calculation in the current simulation run.\n"
            #"{passenger_info}\n"
            #"{taxi_info}\n\n"
        )
        
        if self.llmHasFuture == True:
            self._base_instruction = (
                "Given the above information:\n"
                "1. {objective_instruction}\n"
                "2. Implement it as a Python function following Gurobi format.\n"
                f"{self.prompt_future_impacts}\n"
                f"{self.prompt_obj_format}"
                f"{self.prompt_cons_restriction}"
                )
        else:
            self._base_instruction = (
                "Given the above information:\n"
                "1. {objective_instruction}\n"
                "2. Implement it as a Python function following Gurobi format.\n"
                f"{self.prompt_obj_format}"
                f"{self.prompt_cons_restriction}"
                )
        

    def _build_core_prompt(self, context_blocks, instruction):
        objective_value = "Please generate a **new objective** for first-level assignment problem"
        return (
            f"{context_blocks}"
            f"{self._iteration_block.format(**instruction['iteration'])}"
            f"{self._base_instruction.format(objective_instruction = objective_value)}"
        )

    def get_prompt_way1(self, iter, passenger_info, taxi_info):
        
        instruction={
                "iteration": {
                    "iter": iter,
                    "passenger_info": passenger_info,
                    "taxi_info": taxi_info
                }
            }
        
        return self._build_core_prompt(self._scenario_block, instruction)

    def get_prompt_way2(self, iter, passenger_info, taxi_info, best_ind):
        
        instruction={
                "iteration": {
                    "iter": iter,
                    "passenger_info": passenger_info,
                    "taxi_info": taxi_info
                },
                "objective": (
                    "Develop an **improved objective** function by:\n"
                    "a) Not only consider taxi passenger/locations, but their arrival time\n" 
                    "b) Modifying weighting strategy, may utilize idle taxis more\n"
                    "c) Preserving 50% original structure of the previous run\n"
                )
            }
        return self._build_inspirational_prompt(best_ind, instruction)

    def get_prompt_way3(self, iter, passenger_info, taxi_info, best_ind):

        instruction={
                "iteration": {
                    "iter": iter,
                    "passenger_info": passenger_info,
                    "taxi_info": taxi_info
                },
                "objective":(
                    "**Reinvent the objective function** from the previous run:\n"
                    "a) The goal is to design a first-level objective serving a sum of minimized passenger waiting time at second level\n" 
                    "b) Dynamic weight adaptation, utilize idle taxis more\n"
                    "c) Consider both current and future taxi/passenger locations, and current and potential future taxi arrival time\n"
                )
            }
        return self._build_inspirational_prompt(best_ind, instruction)

    def _build_inspirational_prompt(self, best_ind, instruction):
        return (
            f"{self._scenario_block}"
            "This is one of your previous run evaluating with a good cost."
            f"The description, objective code, and evaluated second-level cost are provided in {best_ind}\n\n"
            f"{self._iteration_block.format(**instruction['iteration'])}"
            f"{self._base_instruction.format(objective_instruction=instruction['objective'])}"
        )