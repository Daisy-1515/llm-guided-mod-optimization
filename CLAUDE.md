# llm-guided-mod-optimization 项目指南

> 快速导航：查看 [`文档/INDEX.md`](文档/INDEX.md) 了解完整文档结构。

---

## 项目概览

本项目实现 **LLM 引导的分层优化系统**，面向按需出行（MoD）和 Edge-UAV 联合优化问题。

三层主架构：
1. **Layer 1 (LLM)**：动态生成目标函数
2. **Layer 2 (HS)**：Harmony Search 进行提示词/目标进化
3. **Layer 3 (Optimizer)**：数学约束求解与可行性保证

---

## 当前状态

**更新时间**: 2026-04-05

### 项目进度

- **Phase Status**: Phase⑧ 完成 — 代码-文档对齐与归档整合
- **最新稳定提交**: `2c53c0e` `refactor(L1): remove drop mechanism — pure cost1+cost2 objective`
- **最新实验提交**: `2c53c0e` (同上)

### Phase⑧ 完成摘要（2026-03-30）

**代码-文档一致性对齐与归档整合**：

1. **一致性验证**：代码-文档对齐评级 A+（98%）
2. **归档整理**：29 个不活跃文档归档至 7 个 archive 目录
3. **活跃文档更新**：4 个文档更新（+104 行），确保与当前代码同步
4. **分离统计指标**：5 个实验验证全部通过
5. **修改统计**：42 文件变更，+1499 行

**已知遗留问题**：
- ~~`evaluator.py` 的 `drop` 字段兼容性问题~~ — **已修复**（2026-04-01，drop 机制完全移除）
- `test_bcd_metadata_recorded` 键名不匹配（检查 `iterations`/`converged` 但实际为 `bcd_iterations`/`bcd_converged`）
- `test_condition_t_equals_0_is_integer_comparison` 需要 LLM API 配置

### 当前代码结构结论

- 根目录业务 Python 入口已清理，当前根目录仅保留项目级文件和 `__init__.py`
- 可执行入口统一迁移到 [`scripts/`](scripts)
- 原始 MoD 共享模块迁移到 [`legacy_mod/`](legacy_mod)
- 不活跃文档统一归档至各目录下的 `archive/` 子目录

---

## 快速命令

```bash
# 环境
uv sync

# 主运行入口
uv run python scripts/run_edge_uav.py
uv run python scripts/run_all.py

# 结果分析
uv run python scripts/analyze_results.py --run-dir discussion/<run_id>

# API 诊断
uv run python scripts/check_llm_api.py

# 测试
uv run pytest tests -v
```

---

## 目录职责

- [`scripts/`](scripts)：可执行入口脚本
- [`legacy_mod/`](legacy_mod)：原始 MoD 共享数据结构和场景生成
- [`edge_uav/`](edge_uav)：Edge-UAV 主线
- [`heuristics/`](heuristics)：Harmony Search 框架
- [`model/`](model)：原始 MoD 优化模型
- [`llmAPI/`](llmAPI)：LLM 接口层
- [`文档/`](文档)：设计、诊断、运行分析、工作日记

---

## 近期重要变更

### 2026-03-30

- Phase⑧ 完成：代码-文档一致性对齐与归档整合（`daffa90`）
- 29 个不活跃文档归档至 7 个 archive 目录
- 4 个活跃文档更新（+104 行）
- 5 个分离统计指标实验验证通过

### 2026-03-28

- 新增 [`scripts/run_all_experiments.py`](scripts/run_all_experiments.py)，用于批量实验
- 将 `config/config.py` 中 `f_max` 默认值从 `5e9` 提高到 `1e10`
- 移除 `run_edge_uav.py`（原 `testEdgeUav.py`）中运行前强制放宽 `tau` / `f_local` 的默认兜底逻辑
- 将根目录入口和旧模块迁移到 `scripts/` 与 `legacy_mod/`
- 将 Phase4 诊断指南迁移到审查与诊断文档目录

---

### 2026-04-01

- Drop 机制完全移除：7 文件 +160/-348（`2c53c0e`）
- L1 目标函数回退到纯 cost1+cost2，超时任务不再被丢弃
- Codex 审查通过（PASS WITH NOTES）
- 133 tests passed, 2 pre-existing failures

### 2026-04-04

- BCD cost rollback 改为完整 L2 联合目标（`2d1011d`）
- D1 实验运行验证，轨迹图生成
- 发现多 UAV 轨迹完全相同问题
- 139 tests passed, 3 pre-existing failures

### 2026-04-05

- greedy init Bug 修复（`c3618d6`）
- 修复 3 个 pre-existing 测试失败（`d19ec0a`）
- SCA 轨迹分化根因诊断
- SCA 求解器修复：Gurobi 加入 solver fallback 首位，解决开源求解器大规模 SOCP 精度不足
- 参数调优：F_max 2.5e8→1.5e8（消除双重死锁），B_up/B_down 4e7→5e6（提升通信时延占比）
- 150 passed, 1 skipped, 2 skipped

## 下次开始建议

1. ~~修复 3 个 pre-existing 测试失败~~ — **已完成**（2026-04-05）
2. ~~SCA unbounded / 求解器精度问题~~ — **已完成**（2026-04-05）：Gurobi fallback + F_max 调整
3. 调查多 UAV 轨迹退化问题（3 架 UAV 轨迹完全相同，SCA 无分化）— 当前 alpha=35 下通信牵引力仍不足
4. 运行完整规模 HS 实验，验证 LLM 引导优化效果
5. 分析诊断指标趋势，评估目标函数多样性

---

**维护方式**: 项目级说明文件，结合工作日记持续更新。
