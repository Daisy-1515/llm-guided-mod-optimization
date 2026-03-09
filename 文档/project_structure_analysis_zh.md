# 项目结构分析报告

## 项目概略

**项目名称：** LLM 引导的按需出行 (Mobility-on-Demand) 优化
**代码库：** llm-guided-mod-optimization
**用途：** 这是一个分层优化系统，旨在将大语言模型 (LLM) 与数学优化相结合，用于按需出行平台（如网约车服务）。

**核心创新：** 采用混合 LLM-优化器框架：
- **LLM 作为元目标设计器：** 负责演化战略性优化目标。
- **数学优化器作为约束执行器：** 负责确保方案的数学可行性。
- **和声搜索 (Harmony Search) 启发式算法作为 Prompt 演化器：** 负责迭代优化 LLM 的提示词。

**研究背景：** 发表于 NeurIPS 2025。

---

## 目录结构

```
llm-guided-mod-optimization/
├── config/                    # 配置管理
│   ├── env/                   # 环境变量（包含 API 密钥）
│   │   └── .env
│   ├── config.py              # 配置解析器
│   ├── firstLevelExample.py   # 配置示例
│   └── setting.cfg            # 主配置文件
│
├── heuristics/                # 和声搜索算法实现
│   ├── hsFrame.py             # 主进化框架
│   ├── hsPopulation.py        # 种群管理
│   ├── hsIndividual.py        # 个体解表示
│   ├── hsIndividualMultiCall.py  # 多次调用变体
│   ├── hsSorting.py           # 种群排序策略
│   └── hsUtils.py             # 实用工具函数
│
├── llmAPI/                    # LLM 接口层
│   ├── llmInterface.py        # LLM 平台工厂模式封装
│   └── llmInterface_huggingface.py  # HuggingFace 平台实现
│
├── model/                     # 优化模型
│   ├── milpModel.py           # 基础 MILP 模型（基于 Gurobi）
│   └── two_level/             # 两级优化
│       ├── AssignmentModel.py        # 车辆-乘客分配模型
│       ├── AssignmentModel_googleOR.py  # Google OR-Tools 变体版本
│       └── SequencingModel.py        # 路径排序优化
│
├── prompt/                    # 提示词工程
│   ├── basicPrompt.py         # 基础提示词模板
│   └── modPrompt.py           # 按需出行 (MOD) 专用提示词
│
├── simulator/                 # 仿真环境
│   └── SimClass.py            # 动态系统仿真器
│
├── inputs/                    # 输入数据
│   ├── Chicago_WNC/           # 芝加哥数据集
│   └── downtown/              # 市中心数据集
│
├── instances/                 # 问题实例
│   ├── chicago/
│   └── downtown/
│
├── resExample/                # 结果示例
│   └── 900s_150pass_100taxi/  # 样本场景结果
│       ├── run1/              # 多次运行记录
│       ├── run2/
│       └── run3/
│
├── image/                     # 文档图片
├── dataCommon.py              # 通用数据结构
├── scenarioGenerator.py       # 场景生成器
├── testAll.py                 # 主程序入口
└── dependencies.yml           # Conda 环境规范文件
```

---

## 核心组件分析

### 1. 配置系统 (`config/`)
**用途：** 对所有系统参数进行集中式配置管理。
**关键文件：**
- `config.py` - 带有类型检查的主要配置解析器。
- `setting.cfg` - 用户可编辑的设置文件。
- `.env` - API 凭据和端点地址。

### 2. 启发式模块 (`heuristics/`)
**用途：** 实现用于 Prompt 演化的和声搜索算法。
**工作流程：**
1. 使用多样的目标函数初始化种群。
2. 在每一代中：
   - 通过和声存储库操作生成新解。
   - 合并新旧种群。
   - 按适应度排序并选择优胜者。

### 3. LLM 接口 (`llmAPI/`)
**用途：** 多 LLM 平台的抽象层。
**设计模式：** 工厂模式，支持通过配置文件动态切换平台（如 HuggingFace, OpenAI, DeepSeek, Nvidia）。

### 4. 优化模型 (`model/`)
**用途：** 用于车辆路由和分配的数学优化求解器。
- **AssignmentModel:** 决定哪辆车服务哪个乘客。
- **SequencingModel:** 确定取送乘客的最优顺序。

### 5. 仿真环境 (`simulator/`)
**用途：** 用于评估方案的动态系统仿真器。
**性能指标：** 计算总等待时间（乘客）、总行驶时间（车辆）以及总空闲时间（车辆）。

### 6. 提示词工程 (`prompt/`)
**用途：** 管理与 LLM 交互的提示词模板。
**策略：** 引导 LLM 生成能平衡多个竞争目标（如等待时间 vs 行驶距离）的目标函数。

---

## 技术工作流程摘要

1. **初始化：** 加载配置并生成测试场景（车队、请求、地图数据）。
2. **种群初始化：** LLM 生成 N 个不同的目标函数（Python 代码）。
3. **进化循环：**
   - **生成：** LLM 创建新的目标函数。
   - **评估：** 将代码注入 MILP 模型，调用 Gurobi 求解，然后在仿真器中测试性能。
   - **选择：** 根据仿真结果（适应度）保留性能最优的目标函数。
4. **终止：** 达到最大迭代次数后，输出学习到的最优策略。

---

## 依赖项分析
- **优化求解器：** `gurobipy` (商用，需授权), `ortools` (开源替代品)。
- **LLM 集成：** `transformers`, `tiktoken` 等。
- **数据处理：** `pandas`, `numpy`, `joblib`。

---

## 参考文献
- **论文：** [Hierarchical Optimization via LLM-Guided Objective Evolution for Mobility-on-Demand Systems](https://arxiv.org/pdf/2510.10644)
- **会议：** NeurIPS 2025
- **代码库：** https://github.com/yizhangele/llm-guided-mod-optimization

---
**报告生成日期：** 2026-03-08
