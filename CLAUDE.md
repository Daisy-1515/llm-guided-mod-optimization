# llm-guided-mod-optimization 项目指导

> **快速导航**：查看 [`文档/INDEX.md`](文档/INDEX.md) 了解完整的文档导航。

---

## 项目概述

这个项目实现了 **LLM 引导的分层优化系统**，应用于按需出行（MoD）系统，基于 NeurIPS 2025 论文。

三层架构：
1. **Layer 1 (LLM)**: 动态生成目标函数
2. **Layer 2 (HS)**: 进化优化策略
3. **Layer 3 (Gurobi)**: 数学约束求解

详见 [`文档/架构设计.md`](文档/架构设计.md)

---

## 当前状态（自动更新）

**更新时间**: 2026-03-28 14:35:00

### 项目进度
- **Phase Status**: 🟢 Phase⑦ Step4 完成 — BCD 效果验证完成，建议关闭 BCD
- **Latest Commit**: 待提交（标准参数完整运行 + 对比分析报告）
- **Last Verified**: ✅ BCD ON/OFF 各 10 代完整运行，100% 可行解

### 最新运行结果
- **冒烟测试** (popSize=3, iter=3): best=31.77 (均相同)
- **标准运行 BCD ON** (popSize=5, iter=10): `discussion/20260328_134903/` → best=31.77, 成功率 80%
- **标准运行 BCD OFF** (popSize=5, iter=10): `discussion/20260328_134908/` → best=31.77, 成功率 100%
- **结论**: BCD 轨迹优化在当前小规模场景下**无成本改进**，反而降低稳定性（80% vs 100%）

### LLM 配置
- **LLM Model**: `qwen3.5-plus` (config/setting.cfg:7)
- **HS Parameters**: popSize=2, iteration=2 (冒烟); popSize=5, iteration=10 (完整)
- **Endpoint**: CloseAI (api.openai-proxy.org)
- **BCD Integration**: ✅ 启用 (config/setting.cfg:89-94 `use_bcd_loop=true`)

## ⚡ 快速命令

```bash
# 环境
uv sync                                          # 安装依赖

# 运行（务必使用 uv run python，避免系统多版本冲突）
uv run python testEdgeUav.py                     # Edge UAV 管道
uv run python testAll.py                         # 原始 MoD 系统

# 验证
uv run python analyze_results.py --run-dir discussion/20260325_152149/
uv run pytest tests/ -v                          # 66 测试

# 诊断
uv run python check_llm_api.py                   # LLM API 连接检查
```

**⚠️ Python 环境说明**：
- **务必使用 `uv run python`** 运行所有 Python 脚本，避免系统多版本 Python 冲突
- 使用 `uv run pytest` 而非直接 `pytest`（确保正确的虚拟环境）
- 错误示例 ❌：`python script.py`
- 正确示例 ✅：`uv run python script.py`

详见 [`文档/配置指南.md`](文档/配置指南.md) 的「快速命令参考」

---

## 🔧 常见操作

| 操作 | 说明 | 详见 |
|------|------|------|
| **切换 LLM 模型** | qwen → deepseek | 配置指南.md §配置任务1 |
| **修改 HS 参数** | popSize, iteration | 配置指南.md §Harmony Search |
| **调整 Edge UAV 参数** | 能耗、通信参数 | 配置指南.md §仿真参数 |
| **分析运行结果** | 检查 S1-S4 标准 | 配置指南.md §任务4 |

---

## 📚 文档导航

**完整索引**: 查看 [`文档/INDEX.md`](文档/INDEX.md)

**快速链接**：

| 需求 | 文档 |
|------|------|
| 架构和设计 | [`架构设计.md`](文档/架构设计.md) |
| 配置和操作 | [`配置指南.md`](文档/配置指南.md) |
| 数学模型 | [`公式.md`](文档/10_模型与公式/公式.md) |
| Phase⑥ 计划 | [`phase6-step3-socp-fix-plan.md`](plans/phase6-step3-socp-fix-plan.md) |
| 工作日记 | [`70_工作日记/`](文档/70_工作日记/) |
| 诊断报告 | [`40_审查与诊断/`](文档/40_审查与诊断/) |

---

## ⚠️ 重要信息

### 依赖

- **Gurobi**: 商业优化库（学术免费）
- **Python 3.10.20**: 通过 `uv` 管理
- **CVXPY**: 凸优化框架

### 约束

1. **时间槽结构**: 系统使用离散时间槽（$\delta = 1s$）
2. **滚动时域**: 每个时间槽独立优化（可实现在线）
3. **派生变量**: 速度由轨迹导出（$v = \Delta q / \delta$）
4. **BCD 分解**: Edge UAV 轨迹优化使用块坐标下降法

详见 [`文档/架构设计.md` 的「关键设计决策」](文档/架构设计.md)

---

## 👥 项目进展追踪

**实时进度**: 查看 `MEMORY.md`（跨会话）
**工作日记**: `文档/70_工作日记/YYYY-MM-DD.md`（由 `/endday` 自动更新）
**运行结果**: `discussion/{run_id}/` （时间戳）

---

**维护**: 项目级指导，结合 `/endday` skill 自动维护
**更新**: 2026-03-25 20:30
**架构**: 渐进式披露（快速参考 → 导航 → 详细文档）
