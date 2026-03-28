# LLM-Guided Edge UAV 实验方案（执行版）

**创建日期**: 2026-03-28  
**项目**: `llm-guided-mod-optimization`  
**目标**: 用可复现、可汇总、可答辩的实验设计验证 `LLM + HS` 在 Edge-UAV Level-1 目标设计中的价值。

---

## 1. 研究问题

本轮实验只研究 **Level-1 目标函数设计与搜索策略**，默认关闭 `use_bcd_loop`，避免 Level-2 资源分配/轨迹优化混入主结论。

需要回答的假设：

| 假设 | 含义 | 主要对比 |
|---|---|---|
| H1 | LLM 生成目标函数优于无 LLM 的人工/随机目标设计 | A vs C1/C2/D1/D2，B vs D1/D2 |
| H2 | HS 进化优于无进化的独立采样 | A vs B，C1/C2 vs D1/D2 |
| H3 | LLM 与 HS 组合存在正向效应 | A vs B/C1/C2 |
| H4 | 方法收益在不同场景规模下趋势保持一致 | Small / Medium / Large |

---

## 2. 实验组

### 2.1 已实现主实验组

| 组别 | LLM | HS | 当前实现 | 说明 |
|---|:---:|:---:|---|---|
| A | 是 | 是 | `edge_uav` | 完整系统，LLM 生成目标函数，HS 进化搜索 |
| B | 是 | 否 | 独立 50 次 LLM 采样 | 无代际记忆、无 crossover |
| C1 | 否 | 是 | `edge_uav_random` + `template` 模式 | 无 LLM，随机模板库 + HS |
| C2 | 否 | 是 | `edge_uav_random` + `parametric` 模式 | 无 LLM，固定结构随机权重 + HS |
| D1 | 否 | 否 | 默认目标函数 | 代码内 `default_dynamic_obj_func` |
| D2 | 否 | 否 | 手工调参默认目标 | 运行时通过 `--manual-alpha/--manual-gamma` 指定 |

### 2.2 设计原则

- A、B、C1、C2、D1、D2 都按统一 **evaluation budget** 比较，默认预算为 `popSize * iteration = 50`
- 非搜索组 D1/D2 也重复 50 次，以保持预算和结果文件结构一致
- D2 不是自动搜索，而是人为指定的一组参考权重，用作 stronger baseline

---

## 3. 场景与预算

### 3.1 默认主场景

| 参数 | 值 |
|---|---|
| `numTasks` | 10 |
| `numUAVs` | 5 |
| `T` | 20 |
| `scenario_seed` | 多 seed，默认 `42 43 44` |
| `use_bcd_loop` | `false` |

### 3.2 规模敏感性

| 场景 | `numTasks` | `numUAVs` | `T` |
|---|---:|---:|---:|
| Small | 5 | 3 | 10 |
| Medium | 10 | 5 | 20 |
| Large | 20 | 10 | 40 |

### 3.3 公平性口径

- 主公平口径：统一 `eval_budget_target`
- 附加报告口径：`llm_calls`、`wall_time_sec`、`best_cost`、`mean_cost`
- 不把“只看最优值”当成唯一结论

---

## 4. 指标与结果格式

### 4.1 核心指标

| 指标 | 含义 |
|---|---|
| `best_cost` | 预算内最好结果 |
| `mean_cost` | 所有评估的平均成本 |
| `std_cost` | 成本稳定性 |
| `feasible_rate` | 可行率，越高越好 |
| `llm_calls` | LLM 调用次数 |
| `wall_time_sec` | 总耗时 |

### 4.2 收敛输出

所有搜索组输出 `best_so_far` 曲线：

- A：LLM + HS 收敛曲线
- C1：随机模板 + HS 收敛曲线
- C2：随机权重 + HS 收敛曲线
- B：独立采样 best-so-far 曲线

### 4.3 单次运行 JSON

每个 `run_seed_*.json` 至少包含：

- `group`
- `seed`
- `scenario`
- `search.eval_budget_target`
- `search.eval_budget_used`
- `search.llm_calls`
- `metrics.best_cost`
- `metrics.mean_cost`
- `metrics.std_cost`
- `metrics.feasible_rate`
- `history`

---

## 5. 运行方式

### 5.1 批量运行

```bash
uv run python scripts/run_all_experiments.py
```

### 5.2 指定组别和 seed

```bash
uv run python scripts/run_all_experiments.py --groups A B C1 C2 D1 --seeds 42 43 44
```

### 5.3 启用 D2

```bash
uv run python scripts/run_all_experiments.py --groups D2 --manual-alpha 1.5 --manual-gamma 0.6
```

### 5.4 仅查看计划，不执行

```bash
uv run python scripts/run_all_experiments.py --dry-run
```

### 5.5 结果汇总

```bash
uv run python analyze_results.py --experiment-dir discussion/experiment_results/<timestamp>
```

---

## 6. 输出目录

```text
discussion/experiment_results/<timestamp>/
├── manifest.json
├── comparison_summary.json
├── A/
│   ├── run_seed_42.json
│   └── summary.json
├── B/
├── C1/
├── C2/
├── D1/
└── D2/
```

---

## 7. 当前边界与下一步

本次实现已经落地：

- A / B / C1 / C2 / D1 / D2 六组运行脚手架
- 统一 JSON schema
- 实验目录汇总分析

仍建议后续补强：

- 为 D2 选择一组来自人工调参或文献的固定权重，而不是临时拍脑袋
- 在论文版实验中加入显著性检验或置信区间
- 若论文需要完整系统结论，再追加 `use_bcd_loop=true` 的补充实验

---

## 8. 结论写法约束

实验前不预设排序，不写类似 “A 必然优于 B” 的结论。论文中统一使用以下写法：

- 若数据支持 H1/H2/H3/H4，则报告支持程度和幅度
- 若数据不支持，则报告负结果并分析原因
- 不用单一 seed 或单次最好结果替代总体结论
