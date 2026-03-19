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

from pathlib import Path

from configobj import ConfigObj
import os
from dotenv import load_dotenv

class configPara:
    def __init__(self, config_file, env_file):
        # 自动定位配置文件（支持 configPara(None, None) 的懒调用）
        repo_root = Path(__file__).resolve().parents[1]
        if config_file is None:
            config_file = str(repo_root / "config" / "setting.cfg")
        if env_file is None:
            env_file = str(repo_root / "config" / "env" / ".env")

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

        # ---- Edge UAV 参数（默认值，由 setting.cfg 覆盖）----

        # 物理环境
        self.delta = 1.0        # 时隙长度 (s)
        self.T = 20             # 总时隙数
        self.x_max = 1000.0     # 空域 x 边界 (m)
        self.y_max = 1000.0     # 空域 y 边界 (m)
        self.H = 100.0          # UAV 固定飞行高度 (m)
        self.N_0 = 1e-10        # 噪声功率 (W)
        self.d_U_safe = 50.0    # UAV 间安全距离 (m)

        # 通信
        self.B_up = 1e6         # 上行带宽 (Hz)
        self.B_down = 1e6       # 下行带宽 (Hz)
        self.P_i = 0.5          # TD 发射功率 (W)
        self.P_j = 1.0          # UAV 发射功率 (W)
        self.rho_0 = 1e-5       # 1m 参考信道增益

        # 能耗系数
        self.gamma_i = 1e-28    # TD 芯片能耗系数
        self.gamma_j = 1e-28    # 边缘节点芯片能耗系数

        # UAV 推进模型（公式18）
        self.v_U_max = 30.0     # 最大飞行速度 (m/s)
        self.v_tip = 120.0      # 桨尖速度 (m/s)
        self.eta_1 = 79.86      # 叶片剖面功率 (W)
        self.eta_2 = 88.63      # 诱导功率 (W)
        self.eta_3 = 0.0151     # 机身阻力比
        self.eta_4 = 0.0048     # 空气密度系数

        # 场景规模
        self.numTasks = 10      # 终端设备数
        self.numUAVs = 3        # UAV 数

        # UAV 硬件默认值
        self.E_max = 5000.0     # 能量预算 (J)
        self.f_max = 5e9        # 最大 CPU 频率 (Hz)

        # 任务生成参数
        self.D_l_min = 5e6              # 上行数据量下界 (bits)
        self.D_l_max = 5e7              # 上行数据量上界 (bits)
        self.D_r_min = 1e5              # 下行数据量下界 (bits)
        self.D_r_max = 1e6              # 下行数据量上界 (bits)
        self.F_min = 1e8                # CPU 周期数下界 (cycles)
        self.F_max = 5e9                # CPU 周期数上界 (cycles)
        self.tau_min = 0.5              # 截止时间下界 (s)
        self.tau_max = 2.0              # 截止时间上界 (s)
        self.f_local_default = 1e9      # 终端默认本地 CPU 频率 (Hz)
        self.active_mode = "contiguous_window"  # 活跃模式
        self.active_window_min = 5      # 活跃窗口最小长度（时隙数）
        self.active_window_max = 15     # 活跃窗口最大长度（时隙数）

        # 基站位置
        self.depot_x = 500.0            # 基站 x 坐标 (m)
        self.depot_y = 500.0            # 基站 y 坐标 (m)

        # 场景随机种子
        self.scenario_seed = 42

        # 优化权重
        self.alpha = 1.0        # 时延权重
        self.gamma_w = 1.0      # 计算能耗权重
        self.lambda_w = 1.0     # 飞行能耗权重

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

        # ---- Edge UAV 参数加载 ----

        # 物理环境
        self.delta = self.get_config_value('edgeUavEnv', 'delta', self.delta, cast=float)
        self.T = self.get_config_value('edgeUavEnv', 'T', self.T, cast=int)
        self.x_max = self.get_config_value('edgeUavEnv', 'x_max', self.x_max, cast=float)
        self.y_max = self.get_config_value('edgeUavEnv', 'y_max', self.y_max, cast=float)
        self.H = self.get_config_value('edgeUavEnv', 'H', self.H, cast=float)
        self.N_0 = self.get_config_value('edgeUavEnv', 'N_0', self.N_0, cast=float)
        self.d_U_safe = self.get_config_value('edgeUavEnv', 'd_U_safe', self.d_U_safe, cast=float)

        # 通信
        self.B_up = self.get_config_value('edgeUavComm', 'B_up', self.B_up, cast=float)
        self.B_down = self.get_config_value('edgeUavComm', 'B_down', self.B_down, cast=float)
        self.P_i = self.get_config_value('edgeUavComm', 'P_i', self.P_i, cast=float)
        self.P_j = self.get_config_value('edgeUavComm', 'P_j', self.P_j, cast=float)
        self.rho_0 = self.get_config_value('edgeUavComm', 'rho_0', self.rho_0, cast=float)

        # 能耗系数
        self.gamma_i = self.get_config_value('edgeUavEnergy', 'gamma_i', self.gamma_i, cast=float)
        self.gamma_j = self.get_config_value('edgeUavEnergy', 'gamma_j', self.gamma_j, cast=float)

        # 推进模型
        self.v_U_max = self.get_config_value('edgeUavProp', 'v_U_max', self.v_U_max, cast=float)
        self.v_tip = self.get_config_value('edgeUavProp', 'v_tip', self.v_tip, cast=float)
        self.eta_1 = self.get_config_value('edgeUavProp', 'eta_1', self.eta_1, cast=float)
        self.eta_2 = self.get_config_value('edgeUavProp', 'eta_2', self.eta_2, cast=float)
        self.eta_3 = self.get_config_value('edgeUavProp', 'eta_3', self.eta_3, cast=float)
        self.eta_4 = self.get_config_value('edgeUavProp', 'eta_4', self.eta_4, cast=float)

        # 场景规模
        self.numTasks = self.get_config_value('edgeUavScenario', 'numTasks', self.numTasks, cast=int)
        self.numUAVs = self.get_config_value('edgeUavScenario', 'numUAVs', self.numUAVs, cast=int)

        # UAV 硬件
        self.E_max = self.get_config_value('edgeUavHardware', 'E_max', self.E_max, cast=float)
        self.f_max = self.get_config_value('edgeUavHardware', 'f_max', self.f_max, cast=float)

        # 优化权重
        self.alpha = self.get_config_value('edgeUavWeights', 'alpha', self.alpha, cast=float)
        self.gamma_w = self.get_config_value('edgeUavWeights', 'gamma_w', self.gamma_w, cast=float)
        self.lambda_w = self.get_config_value('edgeUavWeights', 'lambda_w', self.lambda_w, cast=float)

        # 任务生成参数
        self.D_l_min = self.get_config_value('edgeUavTask', 'D_l_min', self.D_l_min, cast=float)
        self.D_l_max = self.get_config_value('edgeUavTask', 'D_l_max', self.D_l_max, cast=float)
        self.D_r_min = self.get_config_value('edgeUavTask', 'D_r_min', self.D_r_min, cast=float)
        self.D_r_max = self.get_config_value('edgeUavTask', 'D_r_max', self.D_r_max, cast=float)
        self.F_min = self.get_config_value('edgeUavTask', 'F_min', self.F_min, cast=float)
        self.F_max = self.get_config_value('edgeUavTask', 'F_max', self.F_max, cast=float)
        self.tau_min = self.get_config_value('edgeUavTask', 'tau_min', self.tau_min, cast=float)
        self.tau_max = self.get_config_value('edgeUavTask', 'tau_max', self.tau_max, cast=float)
        self.f_local_default = self.get_config_value('edgeUavTask', 'f_local_default', self.f_local_default, cast=float)
        self.active_mode = self.get_config_value('edgeUavTask', 'active_mode', self.active_mode)
        self.active_window_min = self.get_config_value('edgeUavTask', 'active_window_min', self.active_window_min, cast=int)
        self.active_window_max = self.get_config_value('edgeUavTask', 'active_window_max', self.active_window_max, cast=int)

        # 基站位置
        self.depot_x = self.get_config_value('edgeUavDepot', 'depot_x', self.depot_x, cast=float)
        self.depot_y = self.get_config_value('edgeUavDepot', 'depot_y', self.depot_y, cast=float)

        # 场景随机种子
        self.scenario_seed = self.get_config_value('edgeUavSeed', 'scenario_seed', self.scenario_seed, cast=int)

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
            
