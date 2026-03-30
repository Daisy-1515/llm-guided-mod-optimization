---
⚠️ **归档文档** — 不再活跃维护

**状态**：存档于 archive/ 目录
**最后更新**：2026-03-24
**理由**：项目结构分析报告，已被 project_structure_report.md 和项目 CLAUDE.md 的最新结论取代
**当前参考**：[项目/CLAUDE.md](../../CLAUDE.md)、[INDEX.md](INDEX.md)

---

# 项目结构分析报告（中文）

## 1. 文档目标

本文档描述 `llm-guided-mod-optimization` 在 `2026-03-24` 的实际仓库结构，重点回答三个问题：

1. 现在仓库里有哪些主干模块。
2. 原始 MoD 主线和 Edge-UAV 主线分别落在哪些目录。
3. 哪些目录属于源码，哪些属于文档、测试、运行产物或本地工具元数据。

这是一份“现状结构文档”，不是历史演化记录。

---

## 2. 项目概述

项目名称：`Hierarchical Optimization via LLM-Guided Objective Evolution for Mobility-on-Demand Systems`

当前仓库已经演化为“双主线并存”的结构：

- `原始 MoD 主线`
  以 `testAll.py` 为入口，保留论文原始的 LLM + Harmony Search + 两层优化 + 仿真链路。
- `Edge-UAV 主线`
  以 `testEdgeUav.py` 为入口，围绕任务卸载、频率分配、推进能耗、轨迹优化等模块开展新的实现与测试。

因此，今天的仓库不再只是一个单一的 MoD 代码仓，而是：

- 一个保留原始 MoD 基线的研究仓库；
- 一个正在持续扩展的 Edge-UAV 求解与实验仓库；
- 一个带有较完整设计文档、测试文档、诊断文档和工作日记的研究工作区。

---

## 3. 顶层目录结构

下面的树只保留“项目相关目录”，省略 `.git/`、`.venv/`、`__pycache__/` 等缓存或工具细节。

```text
llm-guided-mod-optimization/
├── config/                    # 配置文件与环境变量
├── discussion/                # 运行结果归档
├── edge_uav/                  # Edge-UAV 任务卸载与联合优化主线
├── heuristics/                # Harmony Search 框架与个体/种群逻辑
├── image/                     # README / 文档配图
├── inputs/                    # 输入数据
├── instances/                 # 预设实例
├── llmAPI/                    # LLM 接口封装
├── logs/                      # 运行日志
├── model/                     # 原始 MoD 优化模型
├── prompt/                    # 原始 MoD Prompt 模块
├── resExample/                # 示例结果
├── simulator/                 # 原始 MoD 仿真器
├── tests/                     # Edge-UAV 单元与集成测试
├── 文档/                       # 总览、模型、实现、测试、审查、论文材料、日记
│
├── analyze_results.py         # 结果分析脚本
├── check_llm_api.py           # LLM 连通性检查脚本
├── dataCommon.py              # 原始 MoD 通用数据结构
├── dependencies.yml           # Conda 依赖定义
├── README.md                  # 渐进式披露入口
├── scenarioGenerator.py       # 原始 MoD 场景生成器
├── testAll.py                 # 原始 MoD 主入口
├── testEdgeUav.py             # Edge-UAV 主入口
└── LICENSE
```

---

## 4. 顶层文件职责

### 4.1 运行入口

- `testAll.py`
  原始 MoD 主线入口。
- `testEdgeUav.py`
  Edge-UAV 主线入口。

### 4.2 辅助脚本

- `check_llm_api.py`
  用于检查 LLM API 配置与连通性。
- `analyze_results.py`
  用于分析运行结果与试跑产物。

### 4.3 原始公共模块

- `scenarioGenerator.py`
  原始 MoD 场景生成器。
- `dataCommon.py`
  原始 MoD 的基础数据结构。

### 4.4 环境与说明

- `dependencies.yml`
  Conda 环境定义。
- `README.md`
  当前已按渐进式披露组织，作为新读者的总入口。

---

## 5. 关键目录分析

### 5.1 `config/`：配置层

当前内容：

```text
config/
├── env/
│   └── .env
├── config.py
├── firstLevelExample.py
└── setting.cfg
```

职责：

- 管理 LLM 平台、模型名、环境变量映射；
- 管理仿真参数、Harmony Search 参数、Edge-UAV 参数；
- 为原始 MoD 与 Edge-UAV 两条主线提供统一配置入口。

说明：

- `setting.cfg` 是主要配置文件；
- `config/env/.env` 存放 API Token 和 Endpoint；
- `config/config.py` 已不只是“旧版配置解析器”，而是当前项目的核心配置桥接层。

### 5.2 `heuristics/`：和声搜索与个体执行层

当前文件：

```text
heuristics/
├── hsFrame.py
├── hsIndividual.py
├── hsIndividualEdgeUav.py
├── hsIndividualMultiCall.py
├── hsPopulation.py
├── hsSorting.py
├── hsUtils.py
└── hs_way_constants.py
```

职责：

- 提供 Harmony Search 外层进化框架；
- 管理种群、个体、排序与新解生成；
- 同时支持原始 MoD 个体与 Edge-UAV 个体。

结构变化要点：

- 旧文档只覆盖了 `hsIndividual.py / hsIndividualMultiCall.py`；
- 当前结构中 `hsIndividualEdgeUav.py` 已成为 Edge-UAV 主线的关键桥接模块；
- `hs_way_constants.py` 是后续清理中抽出的常量文件，属于较新的结构整理结果。

### 5.3 `llmAPI/`：模型接口层

当前文件：

```text
llmAPI/
├── llmInterface.py
├── llmInterface_huggingface.py
└── __init__.py
```

职责：

- 根据配置路由到具体的 LLM 调用实现；
- 当前实际代码主路径仍以 `HuggingFace` 兼容 OpenAI Chat Completions 风格接口为主；
- 为 Harmony Search 中的目标函数生成提供统一入口。

### 5.4 `prompt/`：原始 MoD Prompt 层

当前文件：

```text
prompt/
├── basicPrompt.py
└── modPrompt.py
```

职责：

- 管理原始 MoD 主线中的 Prompt 模板；
- 引导 LLM 输出满足约束格式的目标函数代码。

说明：

- 这部分仍服务于原始 MoD 主线；
- Edge-UAV 的 Prompt 已独立拆到 `edge_uav/prompt/`。

### 5.5 `model/`：原始 MoD 优化模型层

当前文件：

```text
model/
├── milpModel.py
└── two_level/
    ├── AssignmentModel.py
    ├── AssignmentModel_googleOR.py
    └── SequencingModel.py
```

职责：

- 保留原始论文中的 MoD 优化模型；
- `AssignmentModel.py` 负责分配问题；
- `SequencingModel.py` 负责路径/顺序问题；
- `AssignmentModel_googleOR.py` 提供 OR-Tools 变体。

说明：

- 这一层没有被 Edge-UAV 改造替代，而是作为“原始主线”完整保留；
- 因此当前仓库结构的关键特征之一，就是 `model/` 与 `edge_uav/model/` 并行存在。

### 5.6 `simulator/`：原始 MoD 仿真层

当前文件：

```text
simulator/
└── SimClass.py
```

职责：

- 用于原始 MoD 主线的动态仿真与指标计算；
- 为 Harmony Search 的 fitness 评估提供真实反馈。

说明：

- Edge-UAV 主线目前主要走“一次性求解 + 评估”路径，不依赖这套动态仿真器。

---

## 6. `edge_uav/`：当前最活跃的新主线

这是旧版结构文档最缺失、但当前仓库最重要的部分。

当前结构：

```text
edge_uav/
├── data.py
├── scenario_generator.py
├── prompt/
│   ├── base_prompt.py
│   └── mod_prompt.py
└── model/
    ├── evaluator.py
    ├── offloading.py
    ├── precompute.py
    ├── propulsion.py
    ├── resource_alloc.py
    └── trajectory_opt.py
```

### 6.1 `edge_uav/data.py`

职责：

- 定义 Edge-UAV 问题中的核心数据结构；
- 承载任务、无人机、场景等对象。

### 6.2 `edge_uav/scenario_generator.py`

职责：

- 生成 Edge-UAV 专用场景；
- 与原始 `scenarioGenerator.py` 分离，避免两条主线互相污染。

### 6.3 `edge_uav/prompt/`

职责：

- 管理 Edge-UAV 主线中的 Prompt 基类与演化模板；
- 与原始 `prompt/` 并行存在，说明当前项目已经不是单一 Prompt 体系。

### 6.4 `edge_uav/model/`

当前模块职责如下：

- `offloading.py`
  一级卸载决策模型。
- `precompute.py`
  预计算层，负责物理量/约束预处理，是 Edge-UAV 的底层基础模块。
- `propulsion.py`
  推进与能耗相关计算。
- `resource_alloc.py`
  频率/资源分配子问题。
- `trajectory_opt.py`
  轨迹优化子问题，当前已实现 SCA 版本主体。
- `evaluator.py`
  统一评估层，将求解结果转换为可比较指标。

结构判断：

- `edge_uav/model/` 已经形成较完整的分块式求解架构；
- 这条主线具备从数据、场景、Prompt、预计算、求解、评估到测试的闭环。

---

## 7. `tests/`：测试层

当前测试文件：

```text
tests/
├── test_edge_uav_hs_integration.py
├── test_edge_uav_smoke.py
├── test_evaluator.py
├── test_hs_individual_edge_uav.py
├── test_precompute_physics.py
├── test_precompute_validate.py
├── test_propulsion.py
├── test_resource_alloc.py
├── test_s7_offloading_e2e.py
└── test_trajectory_opt.py
```

特征：

- 测试重心明确偏向 Edge-UAV 主线；
- 覆盖层次包括：
  - 纯物理函数；
  - 输入校验；
  - 单模块求解；
  - HS 集成；
  - 端到端流程；
  - smoke test。

这说明当前仓库结构已经从“只有研究原型代码”进化为“带测试护栏的研究代码库”。

---

## 8. `文档/`：文档层

当前文档分层：

```text
文档/
├── 00_总览
├── 10_模型与公式
├── 20_架构与实现
├── 30_测试与执行
├── 40_审查与诊断
├── 50_论文材料
├── 60_规划草案
└── 70_工作日记
```

职责划分：

- `00_总览`
  README 之外的结构入口、参数说明、导航。
- `10_模型与公式`
  数学模型、变量映射、两层解耦与凸性分析。
- `20_架构与实现`
  设计方案、实现计划、模块拆分文档。
- `30_测试与执行`
  试跑计划、测试计划。
- `40_审查与诊断`
  代码审查、安全审查、问题定位。
- `50_论文材料`
  论文章节草稿与原始参考材料。
- `60_规划草案`
  研究方向、规划分析、思路记录。
- `70_工作日记`
  按日期归档的工作记录。

这部分是当前项目的一大特点：文档已经形成“结构化知识库”，而不只是零散笔记。

---

## 9. 运行产物与辅助目录

### 9.1 `discussion/`

职责：

- 存放带时间戳的运行结果；
- 当前目录名形如 `20260320_124738/`；
- 已成为试跑、对比、复盘的结果归档层。

### 9.2 `logs/`

职责：

- 存放日志文件；
- 当前可见日志主要与试跑相关。

### 9.3 `resExample/`

职责：

- 保留历史示例结果；
- 偏向旧版/示例性质，不是当前主运行目录。

### 9.4 `image/`

职责：

- README 和文档中使用的图片资源。

---

## 10. 两条执行链路

### 10.1 原始 MoD 主线

```text
testAll.py
  -> config/
  -> scenarioGenerator.py
  -> heuristics/
  -> llmAPI/
  -> prompt/
  -> model/
  -> simulator/
  -> discussion/
```

特点：

- 以 LLM 生成目标函数为中心；
- 使用原始 `model/` 与 `simulator/`；
- 是论文原始主线与对照基线。

### 10.2 Edge-UAV 主线

```text
testEdgeUav.py
  -> config/
  -> edge_uav/data.py
  -> edge_uav/scenario_generator.py
  -> edge_uav/prompt/
  -> heuristics/hsIndividualEdgeUav.py
  -> edge_uav/model/
  -> tests/
  -> discussion/ / logs/
```

特点：

- 以联合卸载、资源分配、轨迹优化为核心；
- 正在持续扩展；
- 测试、文档、诊断工作都主要围绕这条主线展开。

---

## 11. 相比旧版结构文档的变化

旧版结构分析存在以下失真：

1. 只描述了原始 MoD 结构，完全遗漏 `edge_uav/`。
2. 没有反映 `tests/` 已成为稳定的测试层。
3. 没有反映 `文档/` 已按类别重组。
4. 没有反映 `testEdgeUav.py`、`check_llm_api.py`、`analyze_results.py` 等新入口脚本。
5. 没有区分“源码目录”和“结果目录/工具目录/本地环境目录”。

因此，今天理解这个仓库时，必须用“双主线 + 文档层 + 测试层 + 运行产物层”的结构视角，而不是早期单主线视角。

---

## 12. 结论

当前仓库的最准确描述是：

- `model/ + simulator/ + prompt/ + llmAPI/` 保留原始 MoD 主线；
- `edge_uav/ + tests/ + 文档/` 构成当前最活跃的研究与实现主线；
- `heuristics/` 和 `config/` 充当两条主线之间的共享基础设施；
- `discussion/`、`logs/`、`resExample/` 承担结果与运行记录的归档职责。

如果后续还要继续维护结构文档，建议优先遵循这个分层：

1. 顶层入口层；
2. 原始 MoD 主线；
3. Edge-UAV 主线；
4. 测试层；
5. 文档层；
6. 运行产物层。

---

文档更新时间：2026-03-24
