---
⚠️ **归档文档** — 长期归档

**状态**：存档于 archive/ 目录
**最后更新**：2026-03-28
**理由**：原始参考文档，保留作为历史记录，不再维护
**当前参考**：[项目/CLAUDE.md](../../CLAUDE.md)

---

# LLM引导的按需出行优化系统 - 项目文档

## 项目概述

### 项目名称
**Hierarchical Optimization via LLM-Guided Objective Evolution for Mobility-on-Demand Systems**
（基于LLM引导目标演化的按需出行系统分层优化）

### 核心思想
本项目创新性地将**大语言模型（LLM）与数学优化**相结合，用于解决按需出行（Mobility-on-Demand）系统中的车辆调度优化问题。该方法通过分层架构，让LLM负责高层战略目标设计，而数学优化器负责底层约束求解。

### 研究背景
- **应用场景**：网约车、共享出行等按需交通服务
- **核心挑战**：如何在动态环境中平衡供需，优化车辆调度
- **创新点**：使用LLM动态演化优化目标函数，而非传统的固定目标

### 论文信息
- **会议**：NeurIPS 2025
- **论文链接**：https://arxiv.org/pdf/2510.10644
- **作者**：Yi Zhang, Yushen Long, Yun Ni, Liping Huang, Xiaohong Wang, Jun Liu

---

## 系统架构

### 三层混合架构

```
┌─────────────────────────────────────────┐
│   LLM层 (Meta-Objective Designer)       │
│   - 动态生成优化目标函数                 │
│   - 基于反馈调整策略                     │
└──────────────┬──────────────────────────┘
               │
┌──────────────▼──────────────────────────┐
│   启发式层 (Harmony Search)              │
│   - 演化LLM提示词                        │
│   - 种群管理与选择                       │
└──────────────┬──────────────────────────┘
               │
┌──────────────▼──────────────────────────┐
│   优化器层 (MILP Solver)                 │
│   - 求解车辆路径规划                     │
│   - 保证约束可行性                       │
└─────────────────────────────────────────┘
```

### 核心组件

1. **LLM作为元目标设计器**
   - 根据场景描述生成Python代码形式的目标函数
   - 动态调整优化策略（如权衡等待时间vs行驶距离）

2. **Harmony Search作为提示演化器**
   - 管理LLM生成的目标函数种群
   - 通过交叉、变异等操作演化提示词
   - 根据优化器反馈筛选优质目标

3. **数学优化器作为约束执行器**
   - 使用Gurobi求解MILP问题
   - 确保车辆分配满足时空约束
   - 提供可行性反馈给上层

---

## 项目结构

### 目录结构

```
llm-guided-mod-optimization/
├── config/                    # 配置文件
│   ├── config.py             # 配置参数管理
│   ├── setting.cfg           # 主配置文件
│   └── env/.env              # API密钥配置
├── llmAPI/                    # LLM接口
│   ├── llmInterface.py       # API工厂类
│   └── llmInterface_huggingface.py  # HuggingFace实现
├── heuristics/                # 启发式算法
│   ├── hsFrame.py            # Harmony Search框架
│   ├── hsPopulation.py       # 种群管理
│   ├── hsIndividual.py       # 个体（目标函数）
│   └── hsSorting.py          # 排序与选择
├── model/                     # 优化模型
│   ├── milpModel.py          # MILP基础模板
│   └── two_level/            # 两层模型
├── prompt/                    # 提示词模板
├── simulator/                 # 仿真器
├── inputs/                    # 输入数据（距离矩阵等）
├── instances/                 # 场景实例
├── resExample/                # 结果示例
├── scenarioGenerator.py       # 场景生成器
├── dataCommon.py             # 数据结构定义
├── testAll.py                # 主程序入口
└── dependencies.yml          # 依赖配置
```

### 核心模块说明

#### 1. 配置模块 (`config/`)
**config.py** - 配置参数管理类
- LLM设置：平台、模型、API密钥、温度参数
- 启发式参数：种群大小(popSize)、迭代次数(iteration)、HMCR、PAR
- 仿真参数：运行时间、车辆数、乘客数、城市选择
- 默认目标函数模板

#### 2. LLM接口模块 (`llmAPI/`)
**llmInterface.py** - 工厂模式的API接口
- 支持多平台扩展（HuggingFace、OpenAI、DeepSeek、Nvidia等）
- 自动根据配置选择对应的实现类
- 提供统一的`getResponse()`接口

#### 3. 启发式算法模块 (`heuristics/`)
**hsFrame.py** - Harmony Search主框架
- 初始化种群
- 迭代演化（生成新个体→合并→排序→选择）
- 保存每代结果到JSON

**hsPopulation.py** - 种群管理
- 调用LLM生成新目标函数
- 通过优化器评估适应度
- 实现Harmony Search的记忆选择和音调调整

**hsIndividual.py** - 个体表示
- 封装目标函数代码字符串
- 执行优化求解并返回目标值

#### 4. 优化模型模块 (`model/`)
**milpModel.py** - MILP基础模板
- 定义通用的模型初始化、变量、约束、目标框架
- 使用Gurobi求解器

#### 5. 场景生成模块
**scenarioGenerator.py** - 生成/加载仿真场景
- 加载乘客需求分布（起点、终点、到达时间）
- 加载车辆初始位置
- 生成距离矩阵

**dataCommon.py** - 数据结构定义
- Taxi类：车辆信息
- Passenger类：乘客信息


---

## 工作流程

### 整体流程

1. **初始化阶段**
   ```
   加载配置 → 生成场景 → 初始化Harmony Search
   ```

2. **种群初始化**
   ```
   LLM生成N个初始目标函数 → 优化器评估 → 排序选择
   ```

3. **迭代演化**
   ```
   for 每一代:
       根据HMCR从记忆库选择/随机生成
       根据PAR进行音调调整
       LLM生成新目标函数
       优化器评估新个体
       合并新旧种群并排序
       保留最优的N个个体
   ```

4. **结果输出**
   ```
   保存每代种群到JSON文件
   ```

### 关键算法：Harmony Search

**参数说明**：
- **popSize**: 种群大小（默认3）
- **iteration**: 迭代次数（默认5）
- **HMCR** (Harmony Memory Considering Rate): 从记忆库选择的概率（默认0.9）
- **PAR** (Pitch Adjustment Rate): 音调调整概率（默认0.5）

**演化策略**：
1. 以HMCR概率从历史最优目标函数中选择
2. 以PAR概率对选中的目标函数进行微调
3. 通过LLM生成新的目标函数变体
4. 评估并保留最优个体

---

## 安装与配置

### 环境要求
- Python 3.8+
- Conda（推荐）
- Gurobi许可证（学术用户可免费申请）

### 安装步骤

#### 1. 克隆仓库
```bash
git clone https://github.com/yizhangele/llm-guided-mod-optimization.git
cd llm-guided-mod-optimization
```

#### 2. 创建Conda环境
```bash
conda env create -f dependencies.yml
conda activate llm-guided-mod-optimization
```

#### 3. 安装Gurobi
- 访问 [Gurobi学术许可](https://www.gurobi.com/academia/academic-program-and-licenses/)
- 申请并安装学术许可证
- 验证安装：`python -c "import gurobipy"`

#### 4. 配置API密钥

创建 `config/env/.env` 文件：
```bash
# HuggingFace示例
HUGGINGFACEHUB_API_TOKEN=your_token_here
HUGGINGFACE_ENDPOINT=https://api-inference.huggingface.co/models/your_model

# OpenAI示例
OPENAI_API_TOKEN=your_token_here
OPENAI_ENDPOINT=https://api.openai.com/v1/chat/completions
```

#### 5. 配置参数

编辑 `config/setting.cfg`：
```ini
[llmSettings]
platform = HuggingFace
model = meta-llama/Llama-2-70b-chat-hf

[hsSettings]
popSize = 3
iteration = 5
HMCR = 0.9
PAR = 0.5

[simSettings]
simulationTime = 600
totalVehicleNum = 60
totalPassNum = 70
city = NYC
```


---

## 使用指南

### 快速开始

运行测试：
```bash
python scripts/testAll.py
```

### 程序执行流程

**testAll.py** 主程序：
```python
1. 加载配置参数（config.py）
2. 生成场景信息（scenarioGenerator.py）
3. 初始化Harmony Search求解器（hsFrame.py）
4. 运行优化迭代
5. 保存结果到 ./discussion/ 目录
```

### 输出结果

结果保存在 `./discussion/` 目录：
- `population_result_0.json`: 初始种群
- `population_result_1.json`: 第1代演化结果
- `population_result_N.json`: 第N代演化结果

**JSON格式示例**：
```json
[
  {
    "objective_code": "def dynamic_obj_func(self): ...",
    "fitness": 12345.67,
    "feasible": true
  }
]
```

### 数据准备

#### 场景实例文件
位置：`instances/downtown/` 或 `instances/chicago/`

需要的文件：
- `passenger_volume_70pass_60taxi_600s.csv`: 乘客需求
- `taxi_volume_70pass_60taxi_600s.csv`: 车辆信息

#### 输入数据文件
位置：`inputs/downtown/` 或 `inputs/Chicago_WNC/`

需要的文件：
- `peak_travel_time.csv`: 区域间行驶时间矩阵

---

## 技术细节

### LLM目标函数生成

**输入**：提示词（包含场景描述、约束说明、历史目标函数）

**输出**：Python函数代码
```python
def dynamic_obj_func(self):
    cost1 = gb.quicksum(...)  # 等待时间成本
    cost2 = gb.quicksum(...)  # 行驶距离成本
    cost3 = gb.quicksum(...)  # 其他成本
    weights = [w1, w2, w3]
    self.model.setObjective(
        gb.quicksum(w * c for w, c in zip(costs, weights)), 
        gb.GRB.MINIMIZE
    )
```

### 优化模型变量

**决策变量**：
- `y[v, p]`: 车辆v是否服务乘客p（二值变量）
- 其他辅助变量（时间、距离等）

**约束条件**：
- 每个乘客最多被一辆车服务
- 车辆容量约束
- 时间窗约束
- 路径连续性约束

### 适应度评估

1. 将LLM生成的目标函数代码注入优化模型
2. 调用Gurobi求解器
3. 返回目标值作为适应度
4. 如果不可行，返回惩罚值


---

## 扩展开发

### 添加新的LLM平台

在 `llmAPI/` 目录创建新文件 `llmInterface_yourplatform.py`：

```python
class InterfaceAPI_YourPlatform:
    def __init__(self, configInfo):
        self.api_key = configInfo.api_key
        self.api_endpoint = configInfo.api_endpoint
        self.llmModel = configInfo.llmModel
    
    def getResponse(self, prompt):
        # 实现API调用逻辑
        # 返回LLM生成的文本
        pass
```

然后在 `llmInterface.py` 的 `__new__` 方法中添加：
```python
if configInfo.llmPlatform == "YourPlatform":
    return InterfaceAPI_YourPlatform(configInfo)
```

### 修改优化模型

继承 `milpModel.py` 中的 `generalModel` 类：
```python
class CustomModel(generalModel):
    def setupVars(self):
        # 定义决策变量
        pass
    
    def setupCons(self):
        # 定义约束条件
        pass
    
    def setupObj(self):
        # 定义目标函数（可由LLM动态生成）
        pass
```

### 自定义启发式算法

修改 `heuristics/hsPopulation.py` 中的演化策略：
- `initialize_population()`: 初始化方法
- `generate_new_population()`: 生成新个体的逻辑
- 调整HMCR、PAR等参数

---

## 常见问题

### Q1: Gurobi许可证错误
**问题**：运行时提示 "No Gurobi license found"

**解决**：
1. 确认已安装Gurobi许可证
2. 运行 `gurobi_cl --license` 检查许可状态
3. 学术用户访问 https://www.gurobi.com/academia/ 申请免费许可

### Q2: LLM API调用失败
**问题**：API返回401或403错误

**解决**：
1. 检查 `.env` 文件中的API密钥是否正确
2. 确认API endpoint地址正确
3. 检查网络连接和代理设置

### Q3: 优化模型不可行
**问题**：Gurobi返回 INFEASIBLE 状态

**解决**：
1. 检查场景数据（车辆数是否足够）
2. 放宽时间窗约束
3. 检查LLM生成的目标函数是否合理

### Q4: 内存不足
**问题**：大规模场景下内存溢出

**解决**：
1. 减少种群大小（popSize）
2. 减少车辆/乘客数量
3. 使用更高效的数据结构


---

## 核心优势

### 1. 混合智能架构
- **LLM的语义理解能力** + **数学优化的精确求解**
- LLM负责创造性的目标设计，优化器保证可行性

### 2. 动态目标演化
- 传统方法：固定的手工设计目标函数
- 本方法：根据场景特征自适应演化目标

### 3. 可解释性
- LLM生成的目标函数是可读的Python代码
- 可以理解优化策略的演化过程

### 4. 可扩展性
- 支持多种LLM平台（HuggingFace、OpenAI等）
- 模块化设计，易于扩展新功能

---

## 性能指标

根据论文实验结果，本方法相比传统基线：
- 提升服务质量（减少乘客等待时间）
- 提高车辆利用率
- 在动态场景下表现更优

详细实验结果请参考论文：https://arxiv.org/pdf/2510.10644

---

## 依赖项

### Python包
```yaml
- transformers        # LLM接口
- tiktoken           # Token计数
- pandas             # 数据处理
- numpy              # 数值计算
- configobj          # 配置文件解析
- python-dotenv      # 环境变量管理
- joblib             # 并行处理
- requests           # HTTP请求
- gurobipy           # 优化求解器
- ortools            # 备用求解器
- sentence-transformers  # 文本嵌入
```

### 外部依赖
- **Gurobi**: 商业优化求解器（学术免费）
- **LLM API**: HuggingFace/OpenAI等平台的API访问

---

## 许可证

本项目采用 **MIT License**

**注意**：
- Gurobi需要单独的许可证
- 学术用户可申请免费学术许可
- 商业用户需购买商业许可

---

## 引用

如果本项目对您的研究有帮助，请引用：

```bibtex
@inproceedings{llm-guided-mod-optimization,
    title={Hierarchical Optimization via LLM-Guided Objective Evolution for Mobility-on-Demand Systems},
    author={Yi Zhang, Yushen Long, Yun Ni, Liping Huang, Xiaohong Wang, Jun Liu},
    booktitle={Conference on Neural Information Processing Systems (NeurIPS)},
    year={2025}
}
```

---

## 联系方式

- **GitHub**: https://github.com/yizhangele/llm-guided-mod-optimization
- **论文**: https://arxiv.org/pdf/2510.10644

---

## 更新日志

### 当前版本特性
- 支持HuggingFace平台LLM
- 实现Harmony Search演化算法
- 支持NYC和Chicago数据集
- 提供完整的配置管理系统

### 未来计划
- 支持更多LLM平台（OpenAI、Claude等）
- 优化大规模场景性能
- 添加可视化工具
- 支持实时动态调度

---

**文档生成时间**: 2026-03-09
**项目版本**: 基于NeurIPS 2025论文实现


