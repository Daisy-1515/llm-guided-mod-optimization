"""
* 文件: hsIndividualMultiCall.py
* 作者: Yi 
*
* 创建日期: 2025/01/27
"""
"""
@package hsIndividualMultiCall.py
@brief 此模块处理生成带有多轮调用个体的每次完整运行。

@依赖项
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
    @brief 管理生成带有多轮调用个体的每次完整运行。
    """
    def __init__(self, configPara, scenario):
        super().__init__(configPara, scenario)
        self.optPara = 10

    def updatePromptHistorySimu(self, fullInfo, simuLoopIdx, level1ErrorMessage, func):
        """更新仿真步的提示词历史记录。"""
        self.promptHistory['simulation_steps'][str(simuLoopIdx)] = fullInfo
        if func:
            self.promptHistory['simulation_steps'][str(simuLoopIdx)]["response_format"] = level1ErrorMessage
        else:
            self.promptHistory['simulation_steps'][str(simuLoopIdx)]["response_format"] = "响应格式不符合要求"

    def runOptModel(self, parent, way):
        """运行优化模型（包含多轮次仿真与 LLM 调用）。"""
        def _callLevel1Model(taxi_list, passenger_list, func):
            """调用第一层：指派模型 (Assignment Model)。"""
            level1Model = assignmentModel(dist_matrix, wp_list, taxi_idxlist, dynamic_obj_func=func)
            level1Model.updateInputs(taxi_list, passenger_list)
            feasible, cost = level1Model.solveProblem()
            assignResult = level1Model.getOutputs()

            return feasible, cost, assignResult, level1Model.error_message


        def _callLevel2Model(taxi_list, passenger_list, key, vehTask, KOpt=False):
            """调用第二层：路径规划模型 (Sequencing Model)。"""
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
        # 开始仿真循环
        while loopIdx < self.steps or task_on_going>0:
            if loopIdx < self.steps:
                ###### 获取新一轮的乘客请求和出租车位置 #######################
                newly_coming = passenger_volume[loopIdx] if loopIdx in passenger_volume.keys() else {} # 本时间槽新来的乘客
                # 从仿真器获取未上车的乘客
                pre_unloaded_passenger = simEnv.get_unloaded_passenger()

                common_keys = set(newly_coming) & set(pre_unloaded_passenger)
                if common_keys:
                    print(f"错误: 发现重复的键: {common_keys}")
                    break

                passenger_list = {**newly_coming, **pre_unloaded_passenger}
                taxi_list = simEnv.get_state()

                ########## 发出提示词并获取 LLM 回复 ##############################
                newPrompt, fullInfo = self.getNewPrompt(parent[loopIdx], way[loopIdx], loopIdx, taxi_list, passenger_list)
                # 提取代码
                func = hsUtils.extract_code_hsIndiv(newPrompt)
                
                ###### 指派模型 - 第 1 层 #######################
                feasible, cost, assignResult, level1ErrorMessage = _callLevel1Model(taxi_list, passenger_list, func)
                self.updatePromptHistorySimu(fullInfo, loopIdx, level1ErrorMessage, func)
                
                ###### 路径规划模型 - 第 2 层 #######################
                cost2obj, cost2result = {}, {}

                for key, vehTask in assignResult.items():
                    res = None
                    if len(vehTask) > 0:
                        if len(vehTask) <= self.optPara:
                            cost, res = _callLevel2Model(taxi_list, passenger_list, key, vehTask)
                        if res is None or len(res) == 0:
                            # 尝试使用 K-Opt 启发式
                            cost, res = _callLevel2Model(taxi_list, passenger_list, key, vehTask, KOpt=True)
                        cost2obj[key], cost2result[key] = cost, res
                    else:
                        cost2obj[key], cost2result[key] = 0, []

                result[loopIdx] = [cost2obj, cost2result]
                # 更新仿真器的待执行指令
                simEnv.update_command(cost2result)

            ###### 发送指令到仿真器进行演进 #############
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
        self.promptHistory['evaluation_score'] = int(passDelay) # 所有乘客的总延迟（秒）
        print("***************** 仿真运行结束! **********************")
