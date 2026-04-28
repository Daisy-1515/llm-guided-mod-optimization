# 项目进度与下次开始建议

> 本文件记录当前项目状态，每次会话结束时更新。

---

## 当前状态

**更新时间**: 2026-04-28

### 最新提交

- `40f55b5` chore: update experiment plot labels
- 本次会话已统一 5 个最终实验作图脚本的命名口径；当前仅剩本地 MATLAB 自动保存文件 `最后实验/失败率/shibai.asv` 保持未跟踪

### 测试状态

- 5 个相关 MATLAB 脚本已用 MATLAB R2025b 实际运行验图
- 本次会话未运行 `uv run pytest tests -v`

### 本次主要变更（最终实验图例统一）

- **任务数消融图已统一命名**：`最后实验/横坐标任务 消融/plot_task_ablation_cost.m`
  - 图例统一为 `ALA / Default Objective / LOGO / LLM+HS`
- **无人机数量消融图已统一命名**：`最后实验/横坐标无人机 消融实验/plot_uav_ablation_cost.m`
  - 图例统一为 `ALA / Default Objective / LOGO / LLM+HS`
- **任务时延图已统一到 LLM+HS 参数 sweep**：`最后实验/横坐标任务 时延不同/plot_task_delay_comparison_cost.m`
  - 图例统一为 `LLM+HS (τ=0.5/1.0/1.5/2.0)`
- **任务带宽图已统一到 LLM+HS 参数 sweep**：`最后实验/横坐标任务 带宽不同/plot_task_bandwidth_cost.m`
  - 图例统一为 `LLM+HS (1 Mbps ... 5 Mbps)`
- **失败率柱状图已统一组名**：`最后实验/失败率/shibai.m`
  - 横轴组名统一为 `LLM+HS` 与 `Default Objective`
  - 类别名统一为 `本地处理 / UAV卸载 / 失败`

### 已知遗留问题

- 若论文、Word 或答辩材料中仍嵌有旧图，需要重新导出并替换终版图片
- `最后实验/失败率/shibai.asv` 仍为未跟踪的本地 MATLAB 自动保存文件
- 本次未跑自动化测试；若后续继续修改脚本或汇总逻辑，应先补一次 `uv run pytest tests -v`

---

## 下次开始建议

1. **重新导出终版图**：把 5 张已改名的最终实验图导出到论文/答辩使用路径，并核对图题、图注和正文口径
2. **统一正文里的旧名称**：把“本地执行 / 标准目标函数 / LLM”同步替换为 `ALA / Default Objective / LOGO / LLM+HS`
3. **如需继续修改脚本或汇总逻辑，先补回归**：运行 `uv run pytest tests -v`
4. **处理 `shibai.asv`**：确认其是否应加入本地忽略策略，避免下次 endday 再次误暂存
