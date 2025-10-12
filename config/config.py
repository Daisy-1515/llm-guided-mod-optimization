"""
* File: config.py
* Author: Yi 
*
* created on 2025/01/23
"""
"""
@package config.py
@brief This module retrieves basic config information.
"""

from configobj import ConfigObj
import os
from dotenv import load_dotenv

class configPara:
    def __init__(self, config_file, env_file):
        # llm
        self.llmPlatform = None
        self.llmModel = None
        self.api_endpoint = None
        self.api_key = None
        self.n_trial = 3
        self.temperature = 0.9
        
        self.config = ConfigObj(config_file)
        self.env = env_file
        
        # prompt
        self.mapPath = None
        self.modelPath = None

        # heuristics
        self.popSize = 3
        self.iteration = 5
        self.HMCR = 0.9
        self.PAR = 0.5
        
        # simulation
        self.runTime = 600
        self.interval = 300  
        self.taxiNum = 60
        self.passNum = 70
        self.city = "NYC"

        self.default_obj = """
def dynamic_obj_func(self): 
    cost1 = gb.quicksum(
            self.y[v, p] * max(self.taxi[v].arrival_time - self.passenger[p].arrTime, 0)
            for v in self.taxi.keys() for p in self.passenger.keys())
        
    cost2 = gb.quicksum(
        gb.quicksum(
            self.distMatrix[self.taxi[v].start_pos][self.passenger[p].origin] * self.y[v, p] 
            for p in self.passenger.keys()
        ) for v in self.taxi.keys()
    )
    
    cost3 = gb.quicksum(
        gb.quicksum(
            self.distMatrix[self.taxi[v].start_pos][self.passenger[p].destination] * self.y[v, p] 
            for p in self.passenger.keys()
        ) for v in self.taxi.keys()
    )
    
    cost4 = gb.quicksum(
        gb.quicksum(self.y[v, p] for p in self.passenger.keys()) * 
        gb.quicksum(self.y[v, p] for p in self.passenger.keys()) 
        for v in self.taxi.keys()
    )
    
    costs = [cost1, cost2, cost3, cost4]
    weights = [1, 1, 1, 100]
    self.model.setObjective(gb.quicksum(w * c for w, c in zip(costs, weights)), gb.GRB.MINIMIZE)
"""
        
    def get_default_obj(self):
        return self.default_obj
    
    def _parse_value(self, value, cast=None):
        """Clean string (remove inline comments/quotes) and apply casting if needed."""
        if value is None:
            return None
        value = str(value).split("#")[0].strip().strip('"').strip("'")
        if value == "":
            return None
        if cast:
            try:
                if cast == int:
                    return int(value)
                elif cast == float:
                    return float(value)
                elif cast == bool:
                    return value.lower() in ("true", "1", "yes", "on")
            except ValueError:
                print(" ValueError in config file. ")
                exit()
                
        return value

    def get_config_value(self, section, key, default=None, cast=None):
        """Safely get config value and apply optional type casting."""
        try:
            if section in self.config and key in self.config[section]:
                raw_val = self.config[section][key]
                return self._parse_value(raw_val, cast)
        except Exception as e:
            print(f"Error: {e}")
            exit()
            
        return default

    def getConfigInfo(self):
        """Load configuration values into class attributes."""
        # llm settings
        self.llmPlatform = self.get_config_value('llmSettings', 'platform', self.llmPlatform)
        self.llmModel = self.get_config_value('llmSettings', 'model', self.llmModel)
        
        # prompt settings
        self.mapPath = self.get_config_value('promptSettings', 'mapPath', self.mapPath)
        self.modelPath = self.get_config_value('promptSettings', 'modelPath', self.modelPath)

        # heuristic settings
        self.popSize = self.get_config_value('hsSettings', 'popSize', self.popSize, cast=int)
        self.iteration = self.get_config_value('hsSettings', 'iteration', self.iteration, cast=int)
        self.HMCR = self.get_config_value('hsSettings', 'HMCR', self.HMCR, cast=float)
        self.PAR = self.get_config_value('hsSettings', 'PAR', self.PAR, cast=float)
        
        # simulation settings
        self.runTime = self.get_config_value('simSettings', 'simulationTime', self.runTime, cast=int)
        self.taxiNum = self.get_config_value('simSettings', 'totalVehicleNum', self.taxiNum, cast=int)
        self.passNum = self.get_config_value('simSettings', 'totalPassNum', self.passNum, cast=int)
        self.city = self.get_config_value('simSettings', 'city', self.city)
        
        # then load environment variables
        self.getEnvInfo()

    def getEnvInfo(self):
        """Load API keys and endpoints from environment file."""
        if self.env:
            load_dotenv(self.env)
        else:
            print(" No environment file provided! ")

        # Platform-specific variable names
        platform_envs = {
            "HuggingFace": ("HUGGINGFACEHUB_API_TOKEN", "HUGGINGFACE_ENDPOINT"),
            "OpenAI": ("OPENAI_API_TOKEN", "OPENAI_ENDPOINT"),
            "DeepSeek": ("DEEPSEEK_API_TOKEN", "DEEPSEEK_ENDPOINT"),
            "Nvidia": ("NVIDIA_API_TOKEN", "NVIDIA_ENDPOINT"),
        }

        api_vars = platform_envs.get(self.llmPlatform, None)

        if api_vars:
            api_key_var, endpoint_var = api_vars
            self.api_key = os.getenv(api_key_var)
            self.api_endpoint = os.getenv(endpoint_var)
        else:
            print(f" Unknown or missing llmPlatform '{self.llmPlatform}' — cannot load API keys.")

        # Check for missing variables
        self._check_missing_fields(source="config file")


    def _check_missing_fields(self, source="configuration"):
        """Print reminder for missing configuration values."""
        for attr, value in self.__dict__.items():
            if attr.startswith("_") or attr in ("config", "env"):
                continue
            if value is None:
                print(f" Please fill in '{attr}' in the {source}.")
                
        """Remind if important API-related environment variables are missing."""
        if self.api_key is None:
            print(f" Please fill in API key for {self.llmPlatform} in your .env file.")
        if self.api_endpoint is None:
            print(f" Please fill in API endpoint for {self.llmPlatform} in your .env file.")
            
