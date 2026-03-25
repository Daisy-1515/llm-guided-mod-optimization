# Phase④-S2 实施计划 — hsIndividualEdgeUav.py

> 日期：2026-03-18
> 前置依赖：S1 固定评估器已完成（evaluator.py, 191行, 8/8 测试通过）
> 目标：创建 Edge UAV 版 HS 个体类，跑通单次 LLM 引导优化流程

---

## 三方协同意见汇总

| 议题 | Gemini | Codex | 最终判断 |
|------|--------|-------|----------|
| **继承 vs 独立** | 独立（父类绑死 taxi/sim） | 独立（父类绑死旧 prompt/API/默认 obj） | **独立**。鸭子类型，只需提供 `runOptModel` + `promptHistory` |
| **API 初始化** | 构造时初始化 | lazy init（避免 default bypass 炸） | **lazy init** `_ensure_api()`。S5 smoke test 无 LLM 配置 |
| **precompute 时机** | runOptModel 内每次算 | `__init__` 预算一次复用 | **`__init__` 预算**。同一个体同一场景，precompute 不变 |
| **default bypass** | func=None，跳过 LLM | 合成 JSON 响应 + func=None | **合成 JSON**。兼容 shrink_token_size 的 json.loads |
| **输入 normalize** | 解包 list[0] | 解包 list[0] | **一致**。S2 先兼容，S3 再收紧 |
| **不可行处理** | 极大惩罚分 | evaluate_solution 自然处理 | **evaluate_solution 已有 INVALID_OUTPUT_PENALTY** |
| **promptHistory 兼容** | 保持字段名 | 关键：llm_response 必须可 json.loads | **合成 JSON + error_message**，严格兼容 |

---

## 关键区别：原 hsIndividualMultiCall vs 新 hsIndividualEdgeUav

| 原 hsIndividualMultiCall | 新 hsIndividualEdgeUav |
|---|---|
| scenarioInfo 元组 (taxi, passenger, OD) | EdgeUavScenario 对象 |
| modPrompts (way1/2/3) | EdgeUavModPrompts (way1/2/3/**4**) |
| SimEnvironment 时步循环 × steps 次 | **无模拟器**，一次性求解 |
| `_callLevel1Model` → AssignmentModel | precompute → OffloadingModel |
| `_callLevel2Model` → SequencingModel | **无** (Level-2 在 Phase ⑤) |
| `passDelay` → evaluation_score | `evaluate_solution()` (固定评估器) |
| `steps` 次 prompt 调用 | **1 次** prompt 调用 |

---

## 实施步骤

### S2.1: 类骨架 + `__init__` + `format_scenario_info()`（~70 行）

**产出**：`heuristics/hsIndividualEdgeUav.py` 基础结构

**内容**：
- 定义 `class hsIndividualEdgeUav`（不继承 hsIndividual）
- `__init__(self, configPara, scenario)`:
  - `self.prompt = EdgeUavModPrompts(offloading.py 路径)`
  - `self.prompt.set_scenario_info(tasks, uavs, time_slots)` + `refresh_scenario_block()`
  - `self.params = PrecomputeParams.from_config(config)`
  - `self.snapshot = make_initial_level2_snapshot(scenario)`
  - `self.precompute_result = precompute_offloading_inputs(...)`
  - `self.api = None`（lazy init）
  - `self.promptHistory = {"simulation_steps": {}, "evaluation_score": None}`
- `_ensure_api(self)`: 延迟初始化 InterfaceAPI
- `_normalize_inputs(self, parent, way)`: list → scalar 解包
- `format_scenario_info(self) -> (str, str)`:
  - task_info: `Task i: pos=, tau=, F=, f_local=, active_slots=`
  - uav_info: `UAV j: pos=, pos_final=, E_max=, f_max=, N_max=`
  - 顶部加 diagnostics 摘要（active_task_slots, offload_feasible_ratio）

**验收**：
- [ ] 文件可 import，实例化不报错
- [ ] format_scenario_info() 返回 (str, str)，含 task/UAV 信息

---

### S2.2: `getNewPrompt(parent, way)` 路由（~50 行）

**内容**：
- `_default_obj_code(self)`: 返回默认目标函数代码字符串
- `_default_llm_response(self)`: 返回合成 JSON（兼容 shrink_token_size）
- `getNewPrompt(self, parent, way)`:
  - `default` → 返回 `(None, full_info)`，llm_response = 合成 JSON
  - `way1` → `self.prompt.get_prompt_way1(iter, task_info, uav_info)`
  - `way2` → `self.prompt.get_prompt_way2(iter, task_info, uav_info, parent)`
  - `way3` → `self.prompt.get_prompt_way3(iter, task_info, uav_info, parent)`
  - `way4` → `self.prompt.get_prompt_way4(iter, task_info, uav_info)`
  - 非 default 时 `self._ensure_api().getResponse(prompt_text)`

**验收**：
- [ ] way1 返回 prompt 文本
- [ ] default 返回合成 JSON（可 json.loads）

---

### S2.3: `runOptModel(parent, way)` 完整流程（~60 行）

**内容**：
```
def runOptModel(self, parent, way):
    parent, way = self._normalize_inputs(parent, way)  # list→scalar
    raw_response, full_info = self.getNewPrompt(parent, way)
    func = extract_code(raw_response) if way != "default" else None
    # 提取失败 → func=None, 标记 response_format
    model = OffloadingModel(..., dynamic_obj_func=func)
    feasible, cost = model.solveProblem()
    outputs = model.getOutputs()
    score = evaluate_solution(outputs, self.precompute_result, self.scenario)
    # 记录 simulation_steps["0"] 和 evaluation_score
    full_info["response_format"] = model.error_message
    full_info["feasible"] = feasible
    full_info["solver_cost"] = cost
    self.promptHistory["evaluation_score"] = float(score)
    self.promptHistory["simulation_steps"]["0"] = full_info
```

**验收**：
- [ ] `runOptModel("", "default")` 跑通
- [ ] promptHistory 结构与 hsSorting/hsPopulation 兼容

---

### S2.4: 测试（无 LLM smoke test）（~60 行）

**产出**：`tests/test_hs_individual_edge_uav.py`

| 测试 | 场景 | 断言 |
|------|------|------|
| T1 | `runOptModel("", "default")` | score > 0 且有限；promptHistory 字段齐全 |
| T2 | `shrink_token_size(promptHistory)` | 不报错；保留 evaluation_score 和 llm_response |
| T3 | `format_scenario_info()` | 返回 (str, str)，含 "Task" 和 "UAV" 字样 |

**验收**：
- [ ] 3 个测试全通过
- [ ] 全量回归无破坏

---

## promptHistory 结构规范（兼容约束）

```python
{
    "evaluation_score": float,         # 固定评估分数（MINIMIZE）
    "simulation_steps": {
        "0": {
            "task_info": str,          # 任务摘要
            "uav_info": str,           # UAV 摘要
            "llm_response": str,       # LLM 原始回复 或 合成 JSON（必须可 json.loads）
            "response_format": str,    # model.error_message 或 "Response format..."
            "feasible": bool,          # 求解可行性
            "solver_cost": float,      # 目标值
        }
    }
}
```

兼容性约束来源：
- `hsSorting.sort_population`: 按 `evaluation_score` 升序排列
- `hsSorting.hsDiversitySorting`: 对 `llm_response` 做 `json.loads` 提取 `obj_code`
- `hsPopulation.shrink_token_size`: 遍历 `simulation_steps`，检查 `response_format`，
  用 `hsUtils.extract_code_hsPopulation` 从 `llm_response` 提取代码

---

## 注意事项

1. **InterfaceAPI 只有 HuggingFace 分支**，其他平台直接 NotImplementedError → lazy init 规避
2. **prompt 初始化**必须用真实 `offloading.py` 路径 + `set_scenario_info` + `refresh_scenario_block`
3. **default bypass** 的 llm_response 必须是合法 JSON，包含 `obj_code` 键
4. **config.alpha / config.gamma_w** 传给 OffloadingModel，但评估器用自己的固定权重
5. **S2 不改 hsPopulation.py**，输入兼容通过 `_normalize_inputs` 处理
