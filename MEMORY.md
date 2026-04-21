# 项目进度记录

## 当前进度

**更新时间**: 2026-04-21 20:35 CST

### 已完成

- [x] 最终实验文档整理：手册统一收拢到 `文档/30_测试与执行/最终实验手册/`
- [x] 新增 `文档/30_测试与执行/最终实验现状总览_2026-04-21.md`，按真实目录核对 `最后实验/` 的完成情况
- [x] 无人机数量消融实验结果统一归档到 `最后实验/横坐标无人机 消融实验/`
- [x] 填充 `最后实验/横坐标无人机 消融实验/横坐标无人机数量 消融实验.csv`
- [x] 任务数参考表归档到 `最后实验/横坐标任务数 消融实验.csv`
- [x] 为无人机消融目录补充 `README.md`，写明 `u=3~9` 覆盖范围与重复点位选取规则

### 当前参数配置

- A 组无人机消融结果口径：`seed=42`，`numTasks=20`，`numUAVs=3~9`
- A 组带宽参数：`B_up = 5e7`，`B_down = 5e7`
- A 组求解设置：`use_bcd_loop = true`，`hs popSize = 3`，`hs iteration = 3`
- 待补 D1 口径：`B_up = 1e7`，`B_down = 1e7`，`use_bcd_loop = false`

### 待验证

- [ ] 在具备完整 Gurobi 授权的机器上补跑 D1 无 BCD 的无人机数量 sweep（`u=3~9`，`B_up=B_down=1e7`）
- [ ] 为无人机消融补齐 D1 结果后，更新对比 CSV / 出图
- [ ] 确认是否需要把 `u=3`、`u=6` 的重复 A 组结果进一步人工定版

## 下次开始建议

1. **在授权机器上跑 D1 无人机 sweep**：直接执行已整理好的 `D1` 命令，参数固定为 `numTasks=20`、`tau=1.0`、`B_up=B_down=1e7`、`--no-bcd-loop`
2. **回填无人机对比表**：补完 D1 后，把 `最后实验/横坐标无人机 消融实验/横坐标无人机数量 消融实验.csv` 扩展为正式对比表
3. **统一出图**：基于任务数 / 无人机数量两张 CSV 生成最终图，避免继续依赖分散目录人工读数

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
