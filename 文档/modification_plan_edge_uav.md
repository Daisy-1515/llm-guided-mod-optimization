# 项目改造计划：边缘服务器卸载 + 无人机轨迹规划

## 问题场景转换

### 原场景（Mobility-on-Demand）
- 出租车接送乘客
- 2D路网距离矩阵
- 车辆容量约束
- 最小化等待时间和行驶距离

### 新场景（Edge Computing + UAV）
- 无人机执行计算任务卸载
- 3D空间轨迹规划
- 电池/载重/计算资源约束
- 最小化任务延迟、能耗、通信成本

---

## 需要修改的核心模块

### 1. 数据结构层 (`dataCommon.py`)

**必须修改：**

```python
# 原有类
class Taxi:          → class UAV (无人机)
class Passenger:     → class ComputeTask (计算任务)
class Task:          → class OffloadingTask (卸载任务)

# 新增类
class EdgeServer:    # 边缘服务器
    - server_id
    - position (x, y, z)
    - cpu_capacity
    - memory_capacity
    - bandwidth
    - current_load

class UAV:           # 无人机
    - uav_id
    - position (x, y, z)
    - battery_level
    - max_battery
    - speed
    - communication_range
    - payload_capacity

class ComputeTask:   # 计算任务
    - task_id
    - data_size
    - cpu_requirement
    - deadline
    - priority
    - source_location
```

**修改原因：** 实体属性完全不同，需要重新定义

---

### 2. 场景生成器 (`scenarioGenerator.py`)

**必须修改：**

```python
class TaskGenerator:
    # 原功能：生成出租车和乘客
    # 新功能：生成无人机、边缘服务器、计算任务

    def generate_uavs(self, num_uavs):
        # 生成无人机初始位置、电池状态

    def generate_edge_servers(self, num_servers):
        # 生成边缘服务器位置和资源配置

    def generate_compute_tasks(self, num_tasks):
        # 生成计算任务（数据量、CPU需求、截止时间）

    def generate_3d_space(self):
        # 定义3D空间范围和障碍物
```

**修改原因：** 场景元素完全不同

---

### 3. 优化模型层 (`model/`)

**必须修改：**

**`milpModel.py` - 基础模型改造**
```python
class generalModel:
    # 原变量：y[v,p] (车辆v服务乘客p)
    # 新变量：
    # - x[u,t,s] (无人机u将任务t卸载到服务器s)
    # - route[u,t1,t2] (无人机u从任务t1飞到t2)
    # - battery[u,t] (无人机u在时刻t的电池)
    # - server_load[s,t] (服务器s在时刻t的负载)
```

**新增约束：**
1. 电池约束：飞行能耗 ≤ 电池容量
2. 通信约束：无人机与服务器距离 ≤ 通信范围
3. 计算资源约束：服务器负载 ≤ 容量
4. 任务截止时间约束
5. 3D空间轨迹连续性约束

**`model/two_level/` 改造**
- `AssignmentModel.py` → `TaskOffloadingModel.py`
  - 决策：哪个任务卸载到哪个服务器
- `SequencingModel.py` → `TrajectoryPlanningModel.py`
  - 决策：无人机3D飞行轨迹

**修改原因：** 决策变量、约束条件、优化目标完全不同

---

### 4. 仿真环境 (`simulator/SimClass.py`)

**必须修改：**

```python
class SimEnvironment:
    # 原功能：模拟出租车接送乘客
    # 新功能：模拟无人机飞行、任务卸载、服务器处理

    def __init__(self, uavs, edge_servers, tasks, space_config):
        self.uavs = uavs
        self.edge_servers = edge_servers
        self.tasks = tasks
        self.current_time = 0
        
    def update_uav_position(self, uav_id, new_position):
        # 更新无人机3D位置
        
    def calculate_flight_energy(self, distance, speed):
        # 计算飞行能耗
        
    def offload_task(self, uav_id, task_id, server_id):
        # 执行任务卸载
        
    def check_communication_feasibility(self, uav_pos, server_pos):
        # 检查通信可行性
        
    def update_server_load(self, server_id, task):
        # 更新服务器负载
```

**新增性能指标：**
- 任务完成率
- 平均任务延迟
- 总能耗
- 服务器利用率
- 通信成本

**修改原因：** 仿真逻辑完全不同

---

### 5. 提示工程 (`prompt/`)

**需要修改：**

**`modPrompt.py` → `edgeUavPrompt.py`**

原提示内容需要完全重写：

```python
# 原提示：关于出租车调度、乘客等待时间
# 新提示：关于边缘计算、无人机能耗、任务卸载

示例新提示：
"""
你是一个边缘计算和无人机系统的优化专家。
当前场景：
- {num_uavs}架无人机
- {num_servers}个边缘服务器
- {num_tasks}个计算任务

请设计一个目标函数，平衡以下因素：
1. 任务完成延迟（deadline violations）
2. 无人机飞行能耗
3. 服务器负载均衡
4. 通信成本

目标函数应该是Python代码，使用Gurobi语法...
"""
```

**修改原因：** 领域知识完全不同，需要新的提示模板

---

### 6. 配置文件 (`config/`)

**需要修改：**

**`config.py` - 默认目标函数**
```python
self.default_obj = """
def dynamic_obj_func(self): 
    # 任务延迟惩罚
    cost1 = gb.quicksum(
        self.x[u, t, s] * max(self.task[t].deadline - completion_time, 0)
        for u in self.uavs for t in self.tasks for s in self.servers
    )
    
    # 飞行能耗
    cost2 = gb.quicksum(
        self.route[u, t1, t2] * energy_consumption(distance_3d)
        for u in self.uavs for t1 in self.tasks for t2 in self.tasks
    )
    
    # 服务器负载均衡
    cost3 = gb.quicksum(
        (self.server_load[s] - avg_load) ** 2
        for s in self.servers
    )
    
    # 通信成本
    cost4 = gb.quicksum(
        self.x[u, t, s] * communication_cost(uav_pos, server_pos)
        for u in self.uavs for t in self.tasks for s in self.servers
    )
    
    weights = [1, 0.5, 0.3, 0.2]
    self.model.setObjective(gb.quicksum(w * c for w, c in zip(costs, weights)), gb.GRB.MINIMIZE)
"""
```

**`setting.cfg` 新增参数**
```ini
[simSettings]
simulationTime = 600
totalUAVNum = 10
totalServerNum = 5
totalTaskNum = 50
spaceSize = 1000  # 3D空间大小（米）
communicationRange = 200  # 通信范围（米）
uavBattery = 5000  # 电池容量（mAh）
```

**修改原因：** 参数和默认目标函数需要适配新场景

---

### 7. 输入数据 (`inputs/`)

**需要修改：**

**原数据：**
- 城市路网距离矩阵
- 出租车起点
- 乘客上下车点

**新数据：**
```
inputs/
├── 3d_space_config.json      # 3D空间配置
│   ├── space_bounds: [x_min, x_max, y_min, y_max, z_min, z_max]
│   ├── obstacles: [(x,y,z,radius), ...]
│   └── no_fly_zones: [...]
│
├── edge_servers.csv           # 边缘服务器配置
│   ├── server_id, x, y, z, cpu_capacity, memory, bandwidth
│
├── uav_specs.json             # 无人机规格
│   ├── max_speed, battery_capacity, communication_range
│   └── energy_model: {hover, forward_flight, ...}
│
└── task_distribution.json     # 任务分布模式
    ├── arrival_rate
    ├── task_size_distribution
    └── deadline_distribution
```

**修改原因：** 数据类型完全不同

---

### 8. 启发式算法 (`heuristics/`)

**可以保留，但需要调整适应度函数：**

```python
# hsIndividual.py 中的评估函数需要修改

class hsIndividual:
    def evaluate_fitness(self):
        # 原逻辑：优化 → 仿真 → 计算等待时间
        # 新逻辑：优化 → 仿真 → 计算延迟+能耗+负载
        
        # 1. 将LLM生成的目标函数注入优化模型
        # 2. 求解任务卸载和轨迹规划问题
        # 3. 在仿真环境中执行方案
        # 4. 计算综合性能指标
        
        fitness = (
            alpha * task_completion_rate +
            beta * avg_delay +
            gamma * total_energy +
            delta * server_utilization
        )
        return fitness
```

**修改原因：** 适应度计算逻辑需要适配新指标

---

## 不需要修改的模块

### 1. LLM接口层 (`llmAPI/`)
**可以保持不变**
- 工厂模式和API调用逻辑通用
- 只需要修改传入的提示内容
- 平台支持（HuggingFace/OpenAI等）无需改动

### 2. 和声搜索框架 (`heuristics/hsFrame.py`, `hsSorting.py`)
**可以保持不变**
- 进化算法框架是通用的
- 种群管理、排序、选择逻辑无需改动
- HMCR、PAR参数机制保持不变

### 3. 主入口 (`testAll.py`)
**基本保持不变**
- 整体流程：配置 → 场景生成 → 和声搜索 → 保存结果
- 只需要确保调用的是新的数据结构和模型

---

## 修改优先级和工作量评估

### 高优先级（必须修改）
1. **数据结构** (`dataCommon.py`) - 工作量：★★☆☆☆
   - 定义UAV、EdgeServer、ComputeTask类
   - 相对简单，主要是属性定义

2. **场景生成** (`scenarioGenerator.py`) - 工作量：★★★☆☆
   - 生成无人机、服务器、任务
   - 需要合理的参数分布

3. **优化模型** (`model/milpModel.py`, `two_level/`) - 工作量：★★★★★
   - 最复杂的部分
   - 需要重新建模决策变量、约束、目标
   - 3D轨迹规划比2D路径复杂

4. **仿真环境** (`simulator/SimClass.py`) - 工作量：★★★★☆
   - 需要模拟3D飞行、能耗、通信
   - 逻辑较复杂

5. **提示工程** (`prompt/modPrompt.py`) - 工作量：★★☆☆☆
   - 重写提示模板
   - 需要领域知识

### 中优先级（建议修改）
6. **配置文件** (`config/config.py`) - 工作量：★★☆☆☆
   - 更新默认目标函数
   - 添加新参数

7. **输入数据** (`inputs/`) - 工作量：★★★☆☆
   - 准备新的数据集
   - 3D空间配置、服务器位置等

### 低优先级（可选）
8. **适应度评估** (`heuristics/hsIndividual.py`) - 工作量：★★☆☆☆
   - 调整性能指标计算

---

## 实施步骤建议

### 阶段1：数据层改造（1-2天）
1. 修改 `dataCommon.py`
   - 定义UAV、EdgeServer、ComputeTask类
   - 添加3D坐标、电池、计算资源等属性
2. 准备测试数据
   - 创建小规模测试场景（3无人机、2服务器、5任务）

### 阶段2：场景生成（2-3天）
1. 改造 `scenarioGenerator.py`
   - 实现无人机、服务器、任务生成逻辑
   - 定义3D空间范围
2. 准备输入数据文件
   - 服务器位置配置
   - 任务分布参数

### 阶段3：优化模型（5-7天）
1. 修改 `model/milpModel.py`
   - 定义新的决策变量（卸载决策、轨迹）
   - 实现电池、通信、资源约束
2. 改造 `model/two_level/`
   - TaskOffloadingModel：任务分配
   - TrajectoryPlanningModel：3D轨迹规划
3. 测试模型可解性

### 阶段4：仿真环境（3-4天）
1. 重写 `simulator/SimClass.py`
   - 3D位置更新
   - 能耗计算
   - 通信可行性检查
   - 服务器负载管理
2. 定义新的性能指标

### 阶段5：提示和配置（1-2天）
1. 修改 `prompt/modPrompt.py`
   - 编写边缘计算领域提示
2. 更新 `config/config.py`
   - 新的默认目标函数
   - 新的配置参数

### 阶段6：集成测试（2-3天）
1. 端到端测试
2. 调试和优化
3. 验证LLM生成的目标函数质量

**总工作量估计：15-22天**

---

## 技术挑战和解决方案

### 挑战1：3D轨迹规划复杂度
**问题：** 3D空间的轨迹规划比2D路径规划复杂得多
**解决方案：**
- 使用分层优化：先决定卸载决策，再规划轨迹
- 考虑使用A*或RRT*算法预处理可行路径
- 简化模型：离散化时间和空间

### 挑战2：能耗模型
**问题：** 无人机能耗与速度、加速度、载重相关，非线性
**解决方案：**
- 使用分段线性化近似
- 参考文献中的能耗模型（如悬停、前飞、爬升）
- 初期可以简化为距离×能耗系数

### 挑战3：通信约束
**问题：** 无人机与服务器的通信受距离限制
**解决方案：**
- 添加大M约束：只有在通信范围内才能卸载
- 考虑中继通信（如果有多个服务器）

### 挑战4：实时性要求
**问题：** 任务有截止时间，需要快速求解
**解决方案：**
- 设置Gurobi求解时间限制
- 使用启发式初始解
- 考虑滚动时域优化（Receding Horizon）

---

## 关键数学模型示例

### 任务卸载决策模型

**决策变量：**
```
x[u,t,s] ∈ {0,1}  # 无人机u将任务t卸载到服务器s
y[u,t] ∈ {0,1}    # 无人机u负责任务t
```

**约束条件：**
```
1. 每个任务最多分配给一个无人机：
   Σ_u y[u,t] ≤ 1, ∀t

2. 每个任务最多卸载到一个服务器：
   Σ_s x[u,t,s] = y[u,t], ∀u,t

3. 服务器容量约束：
   Σ_u Σ_t (x[u,t,s] * task[t].cpu_req) ≤ server[s].capacity, ∀s

4. 通信距离约束：
   x[u,t,s] = 1 → distance(uav[u], server[s]) ≤ comm_range

5. 电池约束：
   Σ_t (y[u,t] * flight_energy[u,t]) ≤ battery[u], ∀u
```

---

### 3D轨迹规划模型

**决策变量：**
```
pos[u,t,dim] ∈ ℝ  # 无人机u在时刻t的位置（dim=x,y,z）
v[u,t,dim] ∈ ℝ    # 速度
```

**约束条件：**
```
1. 位置连续性：
   pos[u,t+1] = pos[u,t] + v[u,t] * Δt

2. 速度限制：
   ||v[u,t]|| ≤ v_max

3. 避障约束：
   distance(pos[u,t], obstacle) ≥ safe_distance

4. 任务位置约束：
   如果y[u,t]=1，则pos[u,task_time]需要在任务位置附近
```

---

## 参考文献和资源

### 边缘计算卸载
1. "Computation Offloading in Multi-Access Edge Computing" (IEEE Survey)
2. "Energy-Efficient Computation Offloading in Mobile Edge Computing"

### 无人机轨迹规划
1. "UAV Trajectory Optimization for Data Collection" (IEEE TWC)
2. "Energy-Efficient UAV Communication with Trajectory Optimization"

### 能耗模型
1. "Energy Model for UAV Communications" (IEEE TCOM)
2. 典型参数：悬停功率~100W，前飞功率~50-150W

---

## 总结

### 核心修改模块（7个）
1. ✅ `dataCommon.py` - 数据结构
2. ✅ `scenarioGenerator.py` - 场景生成
3. ✅ `model/milpModel.py` + `two_level/` - 优化模型
4. ✅ `simulator/SimClass.py` - 仿真环境
5. ✅ `prompt/modPrompt.py` - 提示工程
6. ✅ `config/config.py` - 配置文件
7. ✅ `inputs/` - 输入数据

### 保持不变模块（3个）
1. ✅ `llmAPI/` - LLM接口
2. ✅ `heuristics/hsFrame.py` - 和声搜索框架
3. ✅ `testAll.py` - 主入口（基本不变）

### 关键成功因素
- 优化模型的正确建模（最关键）
- 能耗和通信模型的合理简化
- LLM提示的领域适配
- 仿真环境的准确性

**预计工作量：15-22天**
**技术难度：★★★★☆**

---

**文档生成时间：** 2026-03-08

