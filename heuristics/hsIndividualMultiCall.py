"""
* File: hsIndividualMultiCall.py
* Author: Yi 
*
* created on 2025/01/27
"""
"""
@package hsIndividualMultiCall.py
@brief This module handles each complete run to generate a complete individual with multiple calls.

@dependencies
- simulator.SimClass
- model.two_level.AssignmentModel
- model.two_level.SequencingModel
- heuristics.hsIndividual
"""

from model.two_level.SequencingModel import sequencingModel, sequencingKOpt
from model.two_level.AssignmentModel import assignmentModel
from simulator.SimClass import SimEnvironment
from heuristics.hsIndividual import hsIndividual
import heuristics.hsUtils as hsUtils
import copy

class hsIndividualMultiCall(hsIndividual):
    """
    @class hsIndividualMultiCall
    @brief Manages each complete run to generate a complete individual with multiple calls.
    """
    def __init__(self, configPara, scenario):
        super().__init__(configPara, scenario)
        self.optPara = 10

    def updatePromptHistorySimu(self, fullInfo, simuLoopIdx, level1ErrorMessage, func):
        self.promptHistory['simulation_steps'][str(simuLoopIdx)] = fullInfo
        if func:
            self.promptHistory['simulation_steps'][str(simuLoopIdx)]["response_format"] = level1ErrorMessage
        else:
            self.promptHistory['simulation_steps'][str(simuLoopIdx)]["response_format"] = "Response format does not meet the requirements"

    def runOptModel(self, parent, way):
        def _callLevel1Model(taxi_list, passenger_list, func):
            level1Model = assignmentModel(dist_matrix, wp_list, taxi_idxlist, dynamic_obj_func=func)
            level1Model.updateInputs(taxi_list, passenger_list)
            feasible, cost = level1Model.solveProblem()
            assignResult = level1Model.getOutputs()

            return feasible, cost, assignResult, level1Model.error_message


        def _callLevel2Model(taxi_list, passenger_list, key, vehTask, KOpt=False):
            if not KOpt:
                level2Model = sequencingModel(dist_matrix, wp_list, taxi_list)
                level2Model.updateInputs(key, taxi_list[key], vehTask, passenger_list)
                feasible, cost = level2Model.solveProblem()
                res = level2Model.getOutputs()
            else:
                level2Model = sequencingKOpt(dist_matrix)
                level2Model.updateInputs(key, taxi_list[key], vehTask, passenger_list)
                cost = level2Model.solveProblem()
                res = level2Model.getOutputs()
            return cost, res


        scenarioTest = copy.deepcopy(self.scenario)
        passenger_volume, taxi_volume, taxi_idxlist, dist_matrix, wp_list = scenarioTest
        simEnv = SimEnvironment(taxi_volume, dist_matrix)

        result = dict()
        pre_unloaded_passenger = {}
        loopIdx = 0
        task_on_going = 1
        while loopIdx < self.steps or task_on_going>0:
            if loopIdx < self.steps:
                ###### Get passenger request and taxi location in new round #######################
                newly_coming = passenger_volume[loopIdx] if loopIdx in passenger_volume.keys() else {} # newly coming in this new time slot
                # get unload passenger from simulator
                pre_unloaded_passenger = simEnv.get_unloaded_passenger()

                common_keys = set(newly_coming) & set(pre_unloaded_passenger)
                if common_keys:
                    print(f"Error: Common keys found: {common_keys}")
                    break

                passenger_list = {**newly_coming, **pre_unloaded_passenger}
                taxi_list = simEnv.get_state()

            ########## Issume prompt ##############################
                newPrompt, fullInfo = self.getNewPrompt(parent[loopIdx], way[loopIdx], loopIdx, taxi_list, passenger_list)
                #func = self.getCode(newPrompt)
                func = hsUtils.extract_code_hsIndiv(newPrompt)
                ###### Assignment Model - Level1 #######################
                feasible, cost, assignResult, level1ErrorMessage = _callLevel1Model(taxi_list, passenger_list, func)
                self.updatePromptHistorySimu(fullInfo, loopIdx, level1ErrorMessage, func)
                ###### Sequencing Model - Level2 #######################
                cost2obj, cost2result = {}, {}

                for key, vehTask in assignResult.items():
                    res = None
                    if len(vehTask) > 0:
                        if len(vehTask) <= self.optPara:
                            cost, res = _callLevel2Model(taxi_list, passenger_list, key, vehTask)
                        if res is None or len(res) == 0:
                            cost, res = _callLevel2Model(taxi_list, passenger_list, key, vehTask, KOpt=True)
                        cost2obj[key], cost2result[key] = cost, res
                    else:
                        cost2obj[key], cost2result[key] = 0, []

                result[loopIdx] = [cost2obj, cost2result]
                simEnv.update_command(cost2result)

            ###### send command to simulator to evolve #############
            simStep = 0
            while simStep < self.interval:
                simEnv.sim_one_step()
                simStep += 1

            task_on_going = 0
            for key in simEnv.command.keys():
                task_on_going += len(simEnv.command[key])

            loopIdx += 1

        sceStr = f'{self.steps*self.interval}s_{len(passenger_volume)}pass_{len(taxi_volume)}taxi_'
        passDelay, travelTime, idleTime = simEnv.get_time_cost(sceStr)
        self.promptHistory['evaluation_score'] = int(passDelay) # total delay (all passengers) in second
        print("***************** Simulation run finished! **********************")
