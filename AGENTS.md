# llm-guided-mod-optimization 项目指南

> 快速导航：查看 [`文档/INDEX.md`](文档/INDEX.md) 了解完整文档结构。
> 当前进度：见 [`.Codex/rules/progress.md`](.Codex/rules/progress.md)

---

## 项目概览

本项目实现 **LLM 引导的分层优化系统**，面向按需出行（MoD）和 Edge-UAV 联合优化问题。

三层主架构：
1. **Layer 1 (LLM)**：动态生成目标函数
2. **Layer 2 (HS)**：Harmony Search 进行提示词/目标进化
3. **Layer 3 (Optimizer)**：数学约束求解与可行性保证

---

## 快速命令

```bash
# 环境
uv sync

# 主运行入口
uv run python scripts/run_edge_uav.py
uv run python scripts/run_all_experiments.py --groups A D1 --seeds 42 43 44

# 结果分析
uv run python scripts/analyze_results.py --run-dir discussion/<run_id>

# API 诊断
uv run python scripts/check_llm_api.py

# 测试
uv run pytest tests -v
```

---

## 目录职责

| 目录 | 职责 |
|------|------|
| [`scripts/`](scripts) | 可执行入口脚本 |
| [`edge_uav/`](edge_uav) | Edge-UAV 主线优化代码 |
| [`heuristics/`](heuristics) | Harmony Search 框架 |
| [`llmAPI/`](llmAPI) | LLM 接口层 |
| [`legacy_mod/`](legacy_mod) | 原始 MoD 共享数据结构 |
| [`model/`](model) | 原始 MoD 优化模型 |
| [`config/`](config) | 参数配置（`setting.cfg` 为主） |
| [`文档/`](文档) | 设计、诊断、运行分析 |
| [`日记/`](日记) | 工作日记（实验记录式，只追加） |

---

## 代码规范

- Python 环境：**必须用 `uv run python`**，禁止裸 `python`
- 测试：`uv run pytest tests -v`，修改代码后必须跑回归
- 提交前检查：无裸 `print`（用 `logger`），无硬编码参数

---

**维护方式**: 本文件只含稳定内容。进度/变更记录见 `.Codex/rules/`。
