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

**更新时间**: 2026-03-29 00:38:31

### 项目进度

- **Phase Status**: Phase⑥ Step4 已完成验证，当前进入结构清理与归档阶段
- **最新稳定提交**: `9c78066` `refactor(structure): move entry scripts out of repo root`
- **最新文档提交**: `5cd9499` `docs(diag): move Phase4 diagnostic guide into audit docs`
- **最近提交**: `cdbf0b8` `删除`

### 当前代码结构结论

- 根目录业务 Python 入口已清理，当前根目录仅保留项目级文件和 `__init__.py`
- 可执行入口统一迁移到 [`scripts/`](scripts)
- 原始 MoD 共享模块迁移到 [`legacy_mod/`](legacy_mod)
- `PHASE4_DIAGNOSTIC_GUIDE.md` 已迁移到 [`文档/40_审查与诊断/Phase4_诊断指南_2026-03-27.md`](文档/40_审查与诊断/Phase4_诊断指南_2026-03-27.md)

### 最新运行/实验结论

- BCD ON/OFF 在 2026-03-28 的 10 代标准参数运行中最优值一致，均为 `31.7735`
- 小规模场景下，BCD 没带来成本收益，但稳定性低于 BCD OFF
- 当前推荐默认阅读和运行入口以 `scripts/` 目录为准

### 当前工作区状态

- **未提交改动**:
  - `LICENSE` 已删除
  - `dependencies.yml` 已删除
- 上述两个删除尚未提交，后续需要明确是否保留

---

## 快速命令

```bash
# 环境
uv sync

# 主运行入口
uv run python scripts/testEdgeUav.py
uv run python scripts/testAll.py

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

### 2026-03-28

- 新增 [`scripts/run_all_experiments.py`](scripts/run_all_experiments.py)，用于批量实验
- 将 `config/config.py` 中 `f_max` 默认值从 `5e9` 提高到 `1e10`
- 移除 `testEdgeUav.py` 中运行前强制放宽 `tau` / `f_local` 的默认兜底逻辑
- 将根目录入口和旧模块迁移到 `scripts/` 与 `legacy_mod/`
- 将 Phase4 诊断指南迁移到审查与诊断文档目录

---

## 下次开始建议

1. 决定是否保留 `LICENSE` 和 `dependencies.yml` 的删除
2. 若继续清理仓库根目录剩余杂项文件，可优先处理 `.log`、`.sh`、历史临时说明
3. 若继续实验，统一使用 `scripts/` 下入口，避免再新增根目录脚本

---

**维护方式**: 项目级说明文件，结合工作日记持续更新。
