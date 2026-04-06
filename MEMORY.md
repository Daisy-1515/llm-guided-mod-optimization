# 项目进度记录

## 当前进度

**更新时间**: 2026-04-06

### 已完成

- [x] 文档整理：INDEX同步 + 文件重命名 + archive完善
- [x] 聚合归一化代码实现（evaluator.py, precompute.py, objectives.py, trajectory_opt.py）
- [x] SCA 求解器修复：Gurobi solver fallback + F_max 参数调整
- [x] BCD cost rollback 联合目标修复（cost_ra + cost_traj）
- [x] 贪心轨迹初始化 Bug 修复（起点丢失 + tie-breaking）
- [x] 3 个 pre-existing 测试全部修复（154/154 tests pass）
- [x] HS 替代 Layer1 求解器可行性分析文档（文档/60_规划草案/）

### 当前参数配置

- F_max = 2e8 Hz
- B_up / B_down = 2e7 Hz
- tau = 0.5s
- alpha = 35, lambda_w = 1

### 待验证

- [ ] offloading_outputs 是否正确保存到 JSON（run_all_experiments.py）
- [ ] BCD 多轮迭代效果验证（确认 L1 整数决策是否翻转）
- [ ] F_max=2e8 + B=2e7 "甜区"参数下轨迹分化 + 卸载并存

## 下次开始建议

1. **验证 offloading_outputs 保存**：检查 `run_all_experiments.py` 中 `offloading_outputs` 是否写入 JSON，用 F_max=2e8 + B=2e7 参数跑一次完整实验
2. **BCD 多轮迭代验证**：观察多次 BCD 迭代中 L1 决策是否翻转（检查 `bcd_iterations` 字段）
3. **HS-L1 原型实现**（可选）：参考 `文档/60_规划草案/HS替代Layer1求解器_可行性分析_2026-04-06.md`，从"编码空间强制可行性"方案开始

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
