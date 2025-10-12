"""
* File: hsIndividual.py
* Author: Yi
*
* created on 2025/01/27
"""
"""
@package hsIndividual.py
@brief This module handles each complete run to generate a complete individual.

@dependencies
- prompt.modPrompt
- simulator.SimClass
- model.two_level.AssignmentModel
- model.two_level.SequencingModel
- llmAPI.llmInterface
"""

from llmAPI.llmInterface import InterfaceAPI
from prompt.modPrompt import modPrompts
import json
import re
import copy

class hsIndividual:
    """
    @class hsIndividual
    @brief Manages each complete run to generate a complete individual.
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
        prompt = self.prompt.get_prompt_way1(Idx, passengerInfo, taxiInfo)
        response = self.api.getResponse(prompt)

        return response

    def way2Run(self, Idx, passengerInfo, taxiInfo, p):
        prompt = self.prompt.get_prompt_way2(Idx, passengerInfo, taxiInfo, p)
        response = self.api.getResponse(prompt)

        return response

    def way3Run(self, Idx, passengerInfo, taxiInfo, p):
        prompt = self.prompt.get_prompt_way3(Idx, passengerInfo, taxiInfo, p)
        response = self.api.getResponse(prompt)

        return response

    def getNewPrompt(self, p, way, loopIdx, taxiInfo, passengerInfo):
        # convert taxiInfo and passengerInfo from dictionary to string
        taxi_str = self.convert_taxi_dict_to_str(taxiInfo)
        passenger_str = self.convert_passenger_dict_to_str(passengerInfo)
        if way == "way1":
            res = self.way1Run(loopIdx, passenger_str, taxi_str)
        if way == "way2":
            res = self.way2Run(loopIdx, passenger_str, taxi_str, p)
        if way == "way3":
            res = self.way3Run(loopIdx, passenger_str, taxi_str, p)

        resToSave = {"taxi_info":taxi_str,
                     "passenger_info": passenger_str,
                     "llm_response": res
                     }
        return res, resToSave

    def getInputStr(self, taxiInfo, passengerInfo):
        taxi_str = self.convert_taxi_dict_to_str(taxiInfo)
        passenger_str = self.convert_passenger_dict_to_str(passengerInfo)
        resToSave = {"taxi_info":taxi_str,
                     "passenger_info": passenger_str,
                     "llm_response": None
                     }

        return resToSave

    def convert_taxi_dict_to_str(self, taxi_dict: dict) -> str:
        """Convert taxi dictionary to human-readable string"""
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
        """Convert passenger dictionary to human-readable string"""
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
