# llm-guided-mod-optimization 项目 CLAUDE.md

## 项目概述

这个项目实现了**LLM引导的分层优化系统**，应用于按需出行（Mobility-on-Demand）系统，基于 NeurIPS 2025 论文。系统通过三层架构集成大语言模型与数学优化：
1. **Layer 1 (LLM)**: 动态生成目标函数代码
2. **Layer 2 (Harmony Search)**: 进化优化策略
3. **Layer 3 (Gurobi/Optimizer)**: 数学约束求解

## 当前状态（自动更新）

**更新时间**: 2026-03-25 16:15:52

### 项目进度
- **Phase Status**: 🟡 Phase⑥ in progress (Step1/2/3 in development)
- **Latest Commit**: dddde3c refactor: 改进 analyze_results.py 动态读取 HS 迭代数配置
- **Latest Run**: `discussion/20260325_152149/` (10 generations, S2/S3/S4 verified pass)

### 关键里程碑
- ✅ **Phase⑤** (2026-03-22): 全流程运行通过 (qwen3.5-plus, S1-S4 criteria all PASS)
- 🟡 **Phase⑥ Step3** (2026-03-25): 规划完成，设计 SOCP 修复方案（7步，25-26小时，待执行）
  - Step1 ✅ Propulsion: UAV 推进能耗模型
  - Step2 ✅ Resource Allocation: 凸优化频率/功率分配
  - Step3 🟡 Trajectory Optimization: 解决 DCP 非凸约束 → SOCP 改写 (详见 `plans/phase6-step3-socp-fix-plan.md`)
  - Step4 (待): HS + BCD 完整集成与验证

### LLM 配置
- **Model**: `qwen3.5-plus` (config/setting.cfg:7)
- **Platform**: HuggingFace factory (OpenAI-compatible endpoint)
- **Endpoint**: CloseAI (api.openai-proxy.org)
- **HS Parameters**: popSize=5, iteration=10

---

## 快速开始

### 环境配置

```bash
# 使用 uv（推荐，已配置）
uv sync

# 或使用 conda（原始方法）
conda env create -f dependencies.yml
conda activate llm-guided-mod-optimization
```

### 常用命令

```bash
# 运行 Edge UAV 完整管道
python testEdgeUav.py

# 运行原始 MoD 系统
python testAll.py

# 验证最新运行结果
python analyze_results.py --run-dir 20260325_152149/

# 运行全部测试（62 tests）
pytest tests/ -v
```

### LLM API 配置

**`config/setting.cfg`** — 选择平台和模型：
```ini
[llmSettings]
platform = HuggingFace      # Factory 路由（适配任何 OpenAI-compatible API）
model = qwen3.5-plus        # 代理上的模型 ID（qwen3.5-plus, deepseek-chat, gpt-4o 等）
```

**`config/env/.env`** — API 凭证（NOT 追踪 git）：
```env
HUGGINGFACE_ENDPOINT = "https://your-proxy-domain/v1"   # 自动追加 /chat/completions
HUGGINGFACEHUB_API_TOKEN = "sk-your-api-key"
```

**备注**:
- Factory 仅实现 HuggingFace 路由，但使用标准 OpenAI Chat Completions 格式 — 任何兼容的代理都能工作
- Response parser 支持 3 种格式：`<think>` 标签 (DeepSeek-R1)、直接 JSON、纯文本备选
- Endpoint 自动规范化：`/v1` → `/v1/chat/completions`
- 当前代理: CloseAI (`api.openai-proxy.org`)，当前模型: `qwen3.5-plus`（快速、稳定、推荐复杂提示词）

---

## 系统架构

### 三层分层结构

#### Layer 1: LLM 作为元目标设计器
- **位置**: `llmAPI/llmInterface.py`, `prompt/modPrompt.py`
- **角色**: 动态生成 Python 目标函数代码
- **输入**: 描述优化场景的提示模板
- **输出**: 可执行 Python 代码（定义代理目标函数）

#### Layer 2: Harmony Search 作为提示进化器
- **位置**: `heuristics/hsFrame.py`, `heuristics/hsPopulation.py`
- **角色**: 管理 LLM 生成目标的种群，使用三种变异策略（way1/way2/way3/way4）进化
- **关键文件**:
  - `hsFrame.py`: 主进化循环 (initialize → evaluate → evolve → select)
  - `hsPopulation.py`: 种群管理（并行线程执行）
  - `hsIndividualMultiCall.py`: 个体评估（运行完整优化 + 仿真）
  - `hsSorting.py`: 基于适应度的选择

#### Layer 3: 优化器作为约束执行器
- **位置**: `model/two_level/`, `simulator/`
- **角色**: 用数学严谨性解决操作决策
- **组件**:
  - **Level 1 (Assignment)**: `AssignmentModel.py` — 任务分配二次规划 (BLP)
    - **关键**: LLM 目标通过 `exec()` 注入，替换标准目标
  - **Level 2 (Sequencing)**: `SequencingModel.py` — 路径/路线序列优化
  - **Simulator**: `SimClass.py` — 评估真实系统性能（HS 适应度）

### 关键执行流

```
testEdgeUav.py / testAll.py
  ↓
1. 加载配置 (setting.cfg + .env)
  ↓
2. 生成场景 (scenarioGenerator.py / edge_uav/scenario_generator.py)
  ↓
3. 运行 Harmony Search (hsFrame.py)
     ↓
     For each generation:
       ↓
       For each individual in population (hsPopulation.py):
         ↓
         a. LLM 生成目标函数代码
         ↓
         b. 运行优化循环 (hsIndividualMultiCall.py / hsIndividualEdgeUav.py):
            - Level 1: Assignment with LLM objective → Gurobi
            - Level 2: Sequencing → optimization
            - Simulator: 评估真实代价
         ↓
         c. 返回适应度分数
       ↓
       按适应度排序种群
       ↓
       生成新种群 (mutation/crossover)
  ↓
4. 输出最优解到 ./discussion/
```

---

## Edge UAV 系统（Phase④-⑤ 完成，Phase⑥ 进行中）

### 问题定义

**目标问题**: 从移动设备到无人机挂载边缘服务器的计算任务卸载，结合联合轨迹规划。

### 数学模型（详见 `文档/公式.md`）

**优化变量**:
- `x_{i,i}^t, x_{i,j}^t`: 二进制卸载决策（本地 vs 远程）
- `f_i^t, f_{j,i}^t`: CPU 频率分配（连续）
- `q_j^t = [x_j^t, y_j^t]`: UAV 2D 轨迹（连续，固定高度 H）

**目标函数（公式20）**: 最小化加权和：
1. 归一化任务延迟
2. 边缘计算能耗
3. UAV 飞行能耗

**二层分解** (详见 `文档/公式20_两层解耦.md`):
- **Level 1**: 固定轨迹/资源 → 求解卸载决策 (BLP via Gurobi)
- **Level 2**: 固定卸载 → 联合优化轨迹 + 资源
  - Level 2a: 固定轨迹 → 凸资源分配
  - Level 2b: 固定资源 → 通过 SCA (连续凸近似) 的轨迹优化

### Edge UAV 模块状态（更新 2026-03-25）

**已完成（✅）** — 62/62 测试通过:
- `edge_uav/data.py` — 数据类 (ComputeTask / UAV / EdgeUavScenario)
- `config/config.py` — 10 个部分，42 个 Edge UAV 参数
- `edge_uav/prompt/base_prompt.py` — 基础提示类 + 15 个 Gurobi 规则
- `edge_uav/prompt/mod_prompt.py` — 4 种进化策略 (way1-way4)
- `edge_uav/model/offloading.py` — Level 1 BLP 卸载模型
- `edge_uav/scenario_generator.py` — 场景生成器（39/39 smoke test）
- `edge_uav/model/precompute.py` — 预计算模块（13/13 functions）
- `edge_uav/model/evaluator.py` — HS 适应度评估器（8/8 tests）[Phase④-S1]
- `edge_uav/model/propulsion.py` — UAV 推进能耗模型（114 行）✅ [Phase⑥-S1]
- `edge_uav/model/resource_alloc.py` — 凸频率/功率分配（253 行）✅ [Phase⑥-S2]
- `edge_uav/model/trajectory_opt.py` — SCA 轨迹求解器（579 行，开发阶段）🟡 [Phase⑥-S3]
- `heuristics/hsIndividualEdgeUav.py` — Edge UAV 个体运行器（3/3 tests）[Phase④-S2]
- `heuristics/hsPopulation.py` — Edge UAV 分支 + way4 + 进度日志 [Phase④-S3 + Phase⑤]
- `heuristics/hsFrame.py` — 框架 + run_id 归档 + 摘要统计 [Phase④-S3 + Phase⑤]
- `testEdgeUav.py` — Edge UAV 入口点 + 环境变量覆盖 + 600s 超时 [Phase④-S4 + Phase⑤]
- `llmAPI/llmInterface_huggingface.py` — LLM API + 120s 超时 + 3 路解析器 [Phase⑤]
- `analyze_results.py` — 结果分析 + S1-S4 标准检查 [Phase⑤-F]
- 完整测试套件：`test_propulsion.py` / `test_resource_alloc.py` / `test_trajectory_opt.py` (50 pass, 12 待 Step3 修复)

**架构决策（已确认）**:
- Level-2 (SCA 轨迹 + 频率): 暂时跳过，使用默认快照
- SimEnvironment: Edge UAV 不需要（一次性求解，非在线派遣）
- evaluation_score: 固定外部评估器，NOT objVal（不同目标不可比）
- way4: 集成到 hsPopulation 的 `random.choice(["way3","way4"])`

### Phase⑥ 当前状态 (Step3 规划完成，2026-03-25)

**Step 3 (轨迹优化) — DCP 非凸性修复**:
- **问题确认**: 通信延迟 (sqrt×inv_pos) 和安全分离 (SCA 线性化) 存在 DCP 约束违反
- **解决方案**: SOCP 改写（7步计划，25-26 小时，已准备好执行）
- **计划位置**: `plans/phase6-step3-socp-fix-plan.md`（620 行，包含数学推导）
- **当前测试**: 1 pass, 11 fail（由 DCP 违反阻塞）
- **下一步**: 立即执行 Step3 SOCP 修复计划 → Step4 完整 HS+BCD 集成

**重要**: 原始 MoD 模块（`scenarioGenerator.py`, `AssignmentModel.py`, `SequencingModel.py` 等）保留。运行入口点仍使用原始链。Edge UAV 模块并行构建（双轨制），通过 `testEdgeUav.py` 集成。

---

## 文件地图

**原始 MoD 系统**:
- `scenarioGenerator.py` — 场景生成
- `AssignmentModel.py`, `SequencingModel.py` — 优化模型
- `SimClass.py` — 仿真评估

**Edge UAV 系统**:
- `edge_uav/data.py` — 数据类定义
- `edge_uav/model/` — 物理模型 (offloading / propulsion / resource_alloc / trajectory_opt)
- `edge_uav/prompt/` — 提示工程 (base_prompt / mod_prompt)
- `edge_uav/scenario_generator.py` — 场景生成器
- `heuristics/hsIndividualEdgeUav.py` — HS 个体评估

**Harmony Search 框架**:
- `heuristics/hsFrame.py` — 主框架
- `heuristics/hsPopulation.py` — 种群管理
- `heuristics/hsIndividualMultiCall.py` — 个体评估 (MoD)
- `heuristics/hsSorting.py` — 适应度排序

**LLM 接口**:
- `llmAPI/llmInterface_huggingface.py` — OpenAI 兼容接口
- `llmAPI/llmInterface.py` — 工厂路由

**配置与工具**:
- `config/setting.cfg` — 主配置 (HS 参数、LLM 模型)
- `config/env/.env` — API 凭证
- `config/config.py` — Edge UAV 参数（42 个）
- `check_llm_api.py` — API 连接性检查

**测试套件**: `tests/test_*.py` (62 tests)

---

## 常见任务

### 切换 LLM 模型
编辑 `config/setting.cfg`:
```ini
[llmSettings]
model = qwen3.5-plus    # or deepseek-chat, gpt-4o, etc.
```

### 修改 HS 参数
编辑 `config/setting.cfg`:
```ini
[hsSettings]
popSize = 5
iteration = 10
```

### 运行完整管道并验证结果
```bash
python testEdgeUav.py --popsize=5 --iteration=10
python analyze_results.py --run-dir discussion/LATEST_RUN/
```

### 检查 LLM API 连接
```bash
python check_llm_api.py
```

---

## 重要约束

1. **Gurobi 许可证**: 必需用于 Level 1 BLP。已验证: gurobipy 13.0.1，受限许可证（expires 2027-11-29）。支持约 2000-5000 变量；当前项目规模（默认配置 ~600 二进制变量）安全。

2. **LLM API**: 必须配置 `config/env/.env` 有效的 API 令牌。支持的平台定义在 `llmAPI/llmInterface.py`。

3. **时间槽结构**: 系统使用离散时间槽（索引 `t`）。时间槽时长 `δ` 是关键参数。

4. **滚动时域**: 原始代码使用滚动窗口优化（每槽执行）。对于轨迹规划，考虑实现滚动时域与状态对齐。

5. **派生变量**: 速度 `v_j^t` NOT 独立变量——它从轨迹派生：`v_j^t = (q_j^{t+1} - q_j^t) / δ`。

---

## 开发文档导航

- **数学模型**: `文档/公式.md` — 完整数学模型
- **凸性分析**: `文档/公式20_凸性分析.md` — 目标函数属性分析
- **二层分解**: `文档/公式20_两层解耦.md` — Level1 BLP + Level2 BCD/SCA 设计
- **变量映射**: `文档/图片变量映射分析.md` — 与原论文符号对应
- **场景生成器**: `文档/场景生成器设计方案.md` — 固定 depot、连续活跃窗口、EdgeUavScenario 设计
- **代码审查**: `文档/代码审查报告_2026-03-13.md` — 原代码库静态分析（7 问题发现）
- **仿真参数**: `文档/仿真参数说明_Simulation_Setup.md` — 参数配置参考
- **原始项目**: `文档/项目文档_MoD原始参考.md` — 原 MoD 项目文档
- **论文第 3 章**: `plans/chapter3-system-model-plan.md` — 章节结构设计（5 节，评分 7.3/10）
- **预计算模块**: `文档/precompute_analysis.md` — A1/A2 设计
- **Phase④ HS 适配**: `文档/A4_hs_individual_plan.md` — hsIndividualEdgeUav 设计 + 架构决策
- **Phase⑤ 首次试跑**: `文档/首次试跑计划_Phase5_pipeline.md` — 完整管道首次运行（8 阶段 A-H）
- **Phase⑤ 诊断报告**: `文档/Phase5_LLM调用问题诊断报告.md` — LLM 调用链诊断（3 根本原因、修复计划、5 运行记录）
- **安全审查**: `文档/安全审查报告_2026-03-17.md` — Edge UAV 模块安全审计（6 问题调查，0 漏洞确认）
- **Phase⑥ Step3 计划**: `plans/phase6-step3-socp-fix-plan.md` — DCP 非凸性解决（7 步，25-26h，SOCP 改写，已准备好执行）
- **项目进度**: `MEMORY.md` — 跨会话进度追踪（可选）
- **工作日记**: `文档/70_工作日记/YYYY-MM-DD.md` — 每日工作日志（由 `/endday` 自动生成）

---

## 输出结构

结果保存到 `./discussion/{run_id}/`（时间戳，B1 可观察性补丁后不覆盖）:
- `population_result_0.json`: 初始种群
- `population_result_N.json`: 第 N 代种群
- 每条记录包含：prompt, generated objective code, llm_status, used_default_obj, feasible, evaluation_score

**首次运行成功标准** (S1-S4):
- S1: Exit 0 + JSON 文件存在
- S2: ≥1/3 个体 llm_status="ok" 且 used_default_obj=false
- S3: ≥1 个体 feasible=true
- S4: 对照组基线分数已记录

---

## 论文写作

**第 3 章**: 基于双向数据计算的无线通信系统模型及建模 — 结构规划已完成。

5 个章节: 系统架构 → 空地信道与双向通信 → 任务卸载与边缘计算 → UAV 轨迹与能耗 → 联合优化问题建模

详见 `plans/chapter3-system-model-plan.md`。

---

## 依赖

- **Gurobi**: 学术用途免费许可 (https://www.gurobi.com/academia/)
- **Python 3.10.20** 及包: transformers, torch, gurobipy, ortools, sentence-transformers

---

*本文件由 `/endday` skill 自动维护（当前状态部分）。其他部分可手动编辑。*
