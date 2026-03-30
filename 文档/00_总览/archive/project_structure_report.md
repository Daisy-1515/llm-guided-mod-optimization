---
⚠️ **归档文档** — 不再活跃维护

**状态**：存档于 archive/ 目录
**最后更新**：2026-03-初期
**理由**：项目结构分析报告，已被项目 CLAUDE.md 中的目录职责和最新架构结论取代
**当前参考**：[项目/CLAUDE.md](../../CLAUDE.md)

---

# llm-guided-mod-optimization 项目结构分析报告

## 项目概述
本项目（Hierarchical Optimization via LLM-Guided Objective Evolution for Mobility-on-Demand Systems）提出了一种将**大语言模型（LLM）与数学优化**相结合的动态分层系统，用于优化按需出行（Mobility-on-Demand, MOD）平台的运营。
其核心思想是使用 LLM 作为**元目标设计器**（Meta-Objective Designer），利用启发式算法（和声搜索 Harmony Search）不断进化 LLM 的 Prompt，并使用传统的数学优化求解器（如 Gurobi）在底层（如路由规划）解决严格的约束问题。

## 目录结构及核心模块分析

### 1. 根目录核心文件https://github.com/Daisy-1515/llm-guided-mod-optimization.git
*   **`testAll.py`**: 程序的**主入口**。它负责加载配置，生成任务场景（`TaskGenerator`），初始化并运行核心的启发式搜索求解器（`HarmonySearchSolver`）。
*   **`scenarioGenerator.py`**: **场景生成器**。负责基于给定的城市数据集（如 NYC、Chicago），生成出租车、乘客的初始状态，计算两地之间的行驶时间（距离矩阵），并管理这些数据的存取。
*   **`dataCommon.py`**: **基础数据结构定义**。统一定义了 `Taxi`（出租车）、`Passenger`（乘客）以及 `Task`（任务）这三个基于 `@dataclass` 逻辑的基础类，被广泛用于贯穿整个系统的数据传递。
*   **`dependencies.yml`**: Conda 虚拟环境配置依赖文件，指出该项目依赖于 `gurobipy`, `ortools`, `transformers` 等库。

### 2. 核心子模块
#### 2.1 `config` (配置模块)
*   提供项目的参数读取和配置管理（`config.py` 和 `setting.cfg`），并管理与大模型API通信相关的 `.env` 环境变量信息。

#### 2.2 `heuristics` (启发式搜索模块)
*   **基于和声搜索（Harmony Search）的进化算法框架**。
*   `hsFrame.py`: 进化算法框架的入口 (`HarmonySearchSolver`)。在主循环中，它负责初始化种群（提示词/目标函数的候选解），产生新种群，进行排序与环境选择，从而实现 LLM 提示词的迭代进化。
*   内部包含各种个体（hsIndividual）、种群（hsPopulation）及排序算法（hsSorting）的实现。

#### 2.3 `model` (数学优化模型模块)
*   **执行和约束底层逻辑的数学求解器**。
*   `milpModel.py`: 混合整数线性规划（MILP）的通用父类/基础模板（`generalModel`），封装了 Gurobi 的核心调用逻辑。
*   `two_level/`: 包含具象化的分层优化模型（如 `AssignmentModel.py`, `SequencingModel.py`），它们分别解决第一层（将乘客分配给不同的车辆）和第二层（为单车规划接送顺序的 TSP 操作）问题。

#### 2.4 `llmAPI` (大语言模型通信模块)
*   `llmInterface.py` / `llmInterface_huggingface.py`: 提供与不同 LLM API（如 HuggingFace 等）进行网络请求的封装，获取大语言模型设计的目标函数代码。

#### 2.5 `prompt` (提示词工程模块)
*   `basicPrompt.py` / `modPrompt.py`: 对 LLM 提示词模板的管理。它们规定了如何向 LLM 描述地图结构、OD矩阵、现有代码结构以及输出 Gurobi 代码的严格格式和避坑指南，以让 LLM 生成第一层分配问题的**动态目标函数（Objective function）**。

#### 2.6 `simulator` (模拟器模块)
*   `SimClass.py`: 项目的物理环境模拟器。它负责随着时间步推演，不断更新出租车的位置（闲置或前往接单）、乘客请求状态，计算系统总等待时间、总用时等统计指标，作为反馈发送给进化算法来评估大模型生成目标的性能。

### 3. 系统工作流总结
1.  **初始化阶段**：`testAll.py` 调用 `scenarioGenerator` 准备仿真场景数据。
2.  **主进化循环 (Heuristics)**：`HarmonySearchSolver` 开始种群迭代。
3.  **目标函数生成**：针对种群中的每个个体，`prompt` 模块构建特定上下文的 Prompt，通过 `llmAPI` 请求大模型，要求 LLM 输出符合 Gurobi 语法的目标函数代码。
4.  **数学优化 (Model)**：将 LLM 写的代码注入到 `two_level` 下的分配模型（AssignmentModel）中，让 Gurobi 在该自定义目标函数下求解当前的派单策略。
5.  **仿真验证 (Simulator)**：在 `SimClass` 中下发派单指令，推演虚拟环境一步，计算真实的业务指标（如乘客总等待时间等）。
6.  **迭代与评估**：收集仿真系统返回的真实评价指标（Fitness），在 `heuristics` 模块中执行选择操作保留优秀的“元目标/Prompt”，进入下一代替换不良个体，往复循环直至收敛。
