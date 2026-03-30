"""
* 文件: hsIndividual.py
* 作者: Yi
*
* 创建日期: 2025/01/27
"""
"""
@package hsIndividual.py
@brief 此模块处理生成完整个体的每次完整运行。

@依赖项
- prompt.modPrompt
- simulator.SimClass
- model.two_level.AssignmentModel
- model.two_level.SequencingModel
- llmAPI.llmInterface
"""

from llmAPI.llmInterface import InterfaceAPI
from prompt.modPrompt import modPrompts
from heuristics.hs_way_constants import WAY_MEMORY, WAY_PITCH, WAY_RANDOM
import json
import re
import copy

class hsIndividual:
    """
    @class hsIndividual
    @brief 管理生成完整个体的每次完整运行。
    """
    def __init__(self, configPara, scenario):

        self.prompt = modPrompts(configPara.mapPath, configPara.modelPath)
        self.api = InterfaceAPI(configPara)
        self.scenario = scenario
        self.interval = configPara.interval
        self.steps = int(configPara.runTime / self.interval)
        self.latest_func = configPara.get_default_obj()
        self.promptHistory = {
            'simulation_steps':{},
            'evaluation_score':None}

    def way1Run(self, Idx, passengerInfo, taxiInfo):
        """方式1运行 (通常为随机/初始)。"""
        prompt = self.prompt.get_prompt_way1(Idx, passengerInfo, taxiInfo)
        response = self.api.getResponse(prompt)

        return response

    def way2Run(self, Idx, passengerInfo, taxiInfo, p):
        """方式2运行 (记忆考虑)。"""
        prompt = self.prompt.get_prompt_way2(Idx, passengerInfo, taxiInfo, p)
        response = self.api.getResponse(prompt)

        return response

    def way3Run(self, Idx, passengerInfo, taxiInfo, p):
        """方式3运行 (音调调节)。"""
        prompt = self.prompt.get_prompt_way3(Idx, passengerInfo, taxiInfo, p)
        response = self.api.getResponse(prompt)

        return response

    def getNewPrompt(self, p, way, loopIdx, taxiInfo, passengerInfo):
        """根据选定的和弦搜索方式生成新提示词。"""
        # 将出租车信息和乘客信息从字典转换为字符串
        taxi_str = self.convert_taxi_dict_to_str(taxiInfo)
        passenger_str = self.convert_passenger_dict_to_str(passengerInfo)
        if way == WAY_RANDOM:
            res = self.way1Run(loopIdx, passenger_str, taxi_str)
        elif way == WAY_MEMORY:
            res = self.way2Run(loopIdx, passenger_str, taxi_str, p)
        elif way == WAY_PITCH:
            res = self.way3Run(loopIdx, passenger_str, taxi_str, p)
        else:
            raise ValueError(f"不支持的经典 HS 方式: {way}")

        resToSave = {"taxi_info":taxi_str,
                     "passenger_info": passenger_str,
                     "llm_response": res
                     }
        return res, resToSave

    def getInputStr(self, taxiInfo, passengerInfo):
        """获取输入字符串。"""
        taxi_str = self.convert_taxi_dict_to_str(taxiInfo)
        passenger_str = self.convert_passenger_dict_to_str(passengerInfo)
        resToSave = {"taxi_info":taxi_str,
                     "passenger_info": passenger_str,
                     "llm_response": None
                     }

        return resToSave

    def convert_taxi_dict_to_str(self, taxi_dict: dict) -> str:
        """将出租车字典转换为人类可读的字符串。"""
        if not taxi_dict:
            return "No taxis available"

        entries = []
        for idx, taxi in taxi_dict.items():
            entries.append(
                f"Taxi {taxi.index}: "
                f"start_pos={taxi.start_pos}, "
                f"arrival_time={taxi.arrival_time}s"
            )
        return "\n".join(entries)

    def convert_passenger_dict_to_str(self, passenger_dict: dict) -> str:
        """将乘客字典转换为人类可读的字符串。"""
        if not passenger_dict:
            return "No passengers waiting"

        entries = []
        for idx, passenger in passenger_dict.items():
            entries.append(
                f"Passenger {passenger.index}: "
                f"origin={passenger.origin} destination={passenger.destination}, "
                f"arrTime={passenger.arrTime}s"
            )
        return "\n".join(entries)
