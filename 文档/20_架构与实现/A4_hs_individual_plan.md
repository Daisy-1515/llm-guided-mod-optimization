# Phase ④ — HS 个体适配 Edge UAV 执行计划

> 日期：2026-03-18
> 前置依赖：③ 预计算模块全部完成（S1-S7，44/44 测试通过）
> 目标：创建 Edge UAV 版 HS 个体类，跑通 LLM 引导的优化循环
> 状态：历史执行计划（正文保留 2026-03-18 的计划语义）
> 说明：当前项目状态请以 `CLAUDE.md` 和 `文档/70_工作日记/2026-03-27.md` 为准。

---

## 架构决策（3 项，已确认）

### Q1: Level-2 是否先跳过？

**结论：是，但标记为"框架联调阶段"**

用 `make_initial_level2_snapshot`（默认直线轨迹 + 均分频率）先跑通 HS 循环。
Level-2（SCA 轨迹优化 + 频率分配）在 Phase ⑤ 补上。

**风险**：
- HS 会过拟合到默认代价结构，Level-2 补上后 prompt 偏好可能漂移
- 固定初始快照可能导致"总是本地"等投机策略
- 当前阶段的 prompt 排名不作为最终结论

### Q2: 是否需要 SimEnvironment？

**结论：不需要**

原项目 SimEnvironment 负责在线事件流（乘客到达→分配→行驶→接客→送客）。
Edge UAV 是"给定场景一次性求解"，直接：

```
make_initial_level2_snapshot → precompute → OffloadingModel.solveProblem() → getOutputs()
```

**重要**：不等于直接复用 hsIndividualMultiCall 的"多时步 prompt 数组"接口。
需要新建 single-call runner，不把 one-shot 问题硬塞进 `steps` 次循环。

### Q3: evaluation_score 用什么？

**结论：⚠️ 不能直接用 objVal，需要固定外部评估器**

原因（Codex 关键指出）：HS 进化的是不同目标函数，各自 objVal 不可比。
某个体把权重缩小 100 倍，objVal 立刻更小但决策未必更好。

**固定评估器设计**：

```python
def evaluate_solution(outputs, precompute_result, scenario) -> float:
    """固定评估函数，不随 LLM 生成的目标函数变化。"""
    score = 0.0
    for i, task in scenario.tasks.items():
        for t in scenario.time_slots:
            if not task.active.get(t, False):
                continue
            # ① 实际总延迟（归一化）
            if i in outputs[t]["local"]:
                score += precompute_result.D_hat_local[i][t] / task.tau
            else:
                for j, ids in outputs[t]["offload"].items():
                    if i in ids:
                        score += precompute_result.D_hat_offload[i][j][t] / task.tau
                        # ② 边缘能耗（归一化）
                        score += precompute_result.E_hat_comp[j][i][t] / scenario.uavs[j].E_max
            # ③ Deadline 超限罚项（本地执行无硬约束，但评估时应惩罚）
            # ④ [可选] 负载均衡罚项
    return score
```

---

## HS 框架可复用分析

| 组件 | 文件 | 行数 | 复用? | 说明 |
|------|------|------|-------|------|
| 顶层框架 | `hsFrame.py` | 56 | ✅ | 通用迭代循环 |
| 种群管理 | `hsPopulation.py` | 157 | ✅ | 已接 way4 + Edge UAV 分支（S3 完成） |
| 基础个体 | `hsIndividual.py` | 113 | ❌ | 绑定 Taxi/Passenger，需 Edge UAV 版 |
| 完整个体 | `hsIndividualMultiCall.py` | 127 | ❌ | 绑定 SimEnvironment，需 Edge UAV 版 |
| 种群排序 | `hsSorting.py` | 89 | ✅ | 完全通用 |
| 工具函数 | `hsUtils.py` | 55 | ✅ | 完全通用 |

---

## 新建 vs 原有对比

| 原 hsIndividualMultiCall | 新 hsIndividualEdgeUav |
|---|---|
| `scenarioInfo` 元组 (taxi, passenger, OD) | `EdgeUavScenario` 对象 |
| `modPrompts` (way1/2/3) | `EdgeUavModPrompts` (way1/2/3/**4**) |
| `SimEnvironment` 时步循环 × steps 次 | **无模拟器**，一次性求解 |
| `_callLevel1Model` → AssignmentModel | precompute → OffloadingModel |
| `_callLevel2Model` → SequencingModel | **无** (Level-2 在 Phase ⑤) |
| `passDelay` → evaluation_score | `EdgeUavEvaluator` (固定评估器) |
| `steps` 次 prompt 调用 | **1 次** prompt 调用 |

---

## 执行步骤

### S1: 设计固定评估器 EdgeUavEvaluator（~50 行）

**产出**：`edge_uav/model/evaluator.py`

功能：
- 输入 `(outputs, precompute_result, scenario)` → 输出 `float` 分数
- 组成：① 归一化时延 ② 归一化能耗 ③ deadline 超限罚项 ④ [可选]负载均衡
- 固定公式，不随 LLM 变化 → 不同目标函数可公平比较

验收：
- [x] 用 S7 Test B 的 outputs 调用评估器，得到合理分数 ✅
- [x] 全本地 outputs 分数 > 混合卸载 outputs 分数 ✅（8/8 测试通过，commit 0ead52b）

### S2: 创建 hsIndividualEdgeUav.py（实际 302 行）

**产出**：`heuristics/hsIndividualEdgeUav.py`

核心方法：
- `__init__(config, scenario)` — 初始化 EdgeUavModPrompts + InterfaceAPI + PrecomputeParams
- `runOptModel(parent, way)` — 单次流程：
  1. 调用 `getNewPrompt(parent, way)` 获取 LLM 生成的目标函数代码
  2. `make_initial_level2_snapshot(scenario)` → Level-2 快照
  3. `precompute_offloading_inputs(scenario, params, snap)` → 预计算
  4. `OffloadingModel(..., dynamic_obj_func=code).solveProblem()` → Level-1 求解
  5. `getOutputs()` → 决策结果
  6. `EdgeUavEvaluator(outputs, result, scenario)` → 评估分数
  7. 记录到 promptHistory
- `getNewPrompt(parent, way)` — 路由到 way1/2/3/4
- `format_scenario_info()` — 格式化 task/UAV 信息供 prompt 使用

依赖：S1 (评估器)

验收：
- [x] 用默认 obj（不调 LLM）单个体跑通，得到合理 promptHistory ✅
- [x] 能正确路由 way1/2/3/4 ✅（3/3 测试通过，commit 8fd9322）

### S3: 修改 hsPopulation.py 支持 Edge UAV（小改）

改动点：
1. `generate_new_harmony()` 中加入 way4 采样概率
2. `get_init_ind()` / `get_new_ind()` 支持条件分支创建 Edge UAV 个体
3. 简化 `steps` 参数（Edge UAV 只需 1 步）

依赖：S2

验收：
- [x] `generate_new_harmony` 能产出 way4 ✅
- [x] 双轨制：原 MoD 链路不受影响 ✅（62/62 测试通过，commit 57af7ee）

### S4: 创建入口 testEdgeUav.py（~30 行）

**产出**：`testEdgeUav.py`

流程：
1. `configPara(config_file, env_file).getConfigInfo()`
2. `EdgeUavScenarioGenerator().getScenarioInfo(config)`
3. `HarmonySearchSolver(config, scenario).run()`

依赖：S2, S3

### S5: 单个体 Smoke Test（无 LLM，用默认 obj）

验证 pipeline 通畅：
1. 创建 1 个 hsIndividualEdgeUav
2. 用 `way="default"` 跳过 LLM，使用 OffloadingModel 默认目标
3. 检查 promptHistory 结构和 evaluation_score 合理性

依赖：S4

### S6: 小规模 HS 测试（3 个体，2 代，接 LLM）

验证完整 HS 循环：
1. popsize=3, max_generations=2
2. 接真实 LLM API
3. 检查：代际间 evaluation_score 有变化，种群排序正常
4. 检查 `./discussion/` 输出文件

依赖：S5, LLM API 配置

---

## 注意事项

1. ~~**hsPopulation.generate_new_harmony() 只产出 way1/2/3**~~ → 已修复（S3，`random.choice(["way3","way4"])` for Edge UAV）
2. **prompt 调用次数**：原项目每个个体调 `steps` 次 LLM，Edge UAV 只需 **1 次**
3. **LLM API 配置**：需要 `config/env/.env` 中有可用 endpoint
4. **双轨制**：原 MoD 链路必须保持可用

---

## 后续 Phase

### Phase ⑤-前置：完整 Pipeline 首次试跑（P0，先于 BCD 循环）

> 详细计划见：`文档/30_测试与执行/首次试跑计划_Phase5_pipeline.md`
> 状态：**历史状态：已批准，待执行（仅对应 2026-03-19）**

执行顺序：A（提交加固）→ B（可观测性）→ C/D（预飞）→ E（1×1 → 3×3 试跑）→ F（分析）

成功判据：至少 1/3 个体 llm_status=ok + used_default_obj=false + 至少 1 个 feasible=true

### Phase ⑤-后续: Level-2 BCD 循环（可延后至试跑成功后）

| 步骤 | 内容 |
|------|------|
| S1 | 轨迹优化（SCA 或梯度投影）— 固定 assignment → 优化 q[j][t] |
| S2 | 频率分配（凸优化）— 固定 assignment + 轨迹 → 优化 f_edge[j][i][t] |
| S3 | BCD 循环封装 — Level-1 ↔ Level-2 交替迭代，收敛检查 |
| S4 | 集成到 hsIndividualEdgeUav — 每个个体内跑 BCD |

### Phase ⑥: 论文第三章正文（P1，可与 ④ 并行）

| 节 | 内容 | 页数 |
|----|------|------|
| 3.1 | 系统架构 + 双向数据流时序图 + 符号表 | 2-3 |
| 3.2 | 空地信道 + 双向通信模型 | 2-3 |
| 3.3 | 任务卸载 + 边缘计算模型 | 3-4 |
| 3.4 | UAV 轨迹 + 系统能耗模型 | 3-4 |
| 3.5 | 联合优化问题建模 | 2-3 |
