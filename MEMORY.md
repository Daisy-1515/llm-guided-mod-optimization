# 项目进度记录

## 当前进度

**更新时间**: 2026-04-28 20:00 CST

### 已完成

- [x] 统一最终实验 5 个 MATLAB 作图脚本的算法命名与图例口径
- [x] 任务数 / 无人机数两张消融图统一为 `ALA`、`Default Objective`、`LOGO`、`LLM+HS`
- [x] 任务时延图统一为 `LLM+HS (τ=...)`，任务带宽图统一为 `LLM+HS (1 Mbps ... 5 Mbps)`
- [x] 失败率柱状图统一为 `LLM+HS` vs `Default Objective`，类别名改为 `本地处理 / UAV卸载 / 失败`
- [x] 用 MATLAB R2025b 实际跑通 5 个相关脚本并逐图验收图例
- [x] 提交图例脚本改动：`40f55b5 chore: update experiment plot labels`
- [x] 生成 2026-04-28 工作日记并回填项目级进度记录

### 当前参数配置

- 当前图面命名统一口径：`ALA / Default Objective / LOGO / LLM+HS`
- 时延参数图使用 `LLM+HS` 的 `τ=0.5/1.0/1.5/2.0` sweep
- 带宽参数图使用 `LLM+HS` 的 `1 Mbps ... 5 Mbps` 口径
- `Default Objective` 仍对应原 D1 固定目标基线，`LOGO` 对应单次 LLM 目标生成分支

### 待验证

- [ ] 本次会话未运行 `uv run pytest tests -v`
- [ ] 若论文、Word 或答辩稿中仍嵌有旧图，需要重新导出 5 张最终实验图并同步正文/图注口径
- [ ] 确认 `最后实验/失败率/shibai.asv` 是否仅为本地 MATLAB 自动保存文件，必要时加入忽略策略

## 下次开始建议

1. **重新导出终版图**：把这 5 张已改名的最终实验图导出到论文或答辩使用路径，核对图题、图注和正文是否一致
2. **统一正文命名**：把文中旧称呼（“本地执行”“标准目标函数”“LLM”）收敛到 `ALA / Default Objective / LOGO / LLM+HS`
3. **如需继续改脚本或 CSV，先补回归**：运行 `uv run pytest tests -v`
4. **处理 MATLAB 自动保存文件**：确认 `最后实验/失败率/shibai.asv` 是否要长期忽略，避免下次 endday 混入

## 技术备忘

### 聚合归一化公式 (2026-04-05)

```
score = (1/N_act) × delay_weight × delay_term
      + (1/N_act) × energy_weight × energy_comp_term
      + (1/N_fly) × energy_weight × energy_prop_term
      + deadline_weight × deadline_term
      + balance_weight × balance_term

其中：
- N_act = Σ_t Σ_i ζ_i^t (active task-slot 总数)
- N_fly = |U| × (T-1) (UAV 移动段总数)
```

### SCA 调参经验 (2026-04-05)

- F_max 必须 > tau × f_local，否则所有任务本地可行，0 卸载
- F_max 过大（>2.5e8）导致双重死锁（本地不可完成 + 远端卸载超时）
- Gurobi 在 415 active_offloads 规模 SOCP 下精度远超 CLARABEL/ECOS
- B_up/B_down 越大，通信时延占比越高，BCD 迭代动力越强

### 文档结构

- `文档/INDEX.md` - 文档索引
- `文档/40_审查与诊断/` - 诊断与审查文档
- `文档/60_规划草案/` - 规划草案（含 HS-L1 可行性分析）
- `文档/10_模型与公式/` - 核心公式文档

---
*此文件由 endday 自动化工作流维护*
