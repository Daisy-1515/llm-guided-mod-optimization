# 项目进度记录

## 当前进度

**更新时间**: 2026-04-05

### 已完成

- [x] 文档整理：INDEX同步 + 文件重命名 + archive完善
- [x] 聚合归一化实现方案设计（公式20）
- [x] 目标函数同尺度归一化更正说明

### 进行中

- [ ] 聚合归一化代码实现（evaluator.py, precompute.py 等）
  - evaluator.py: 添加 N_act, N_fly 归一化因子 (+53, -3)
  - precompute.py: 添加推进参数和归一化计算 (+54, -0)
  - objectives.py: 目标函数调整 (+38, -4)
  - trajectory_opt.py: 轨迹优化调整 (+64, -8)
  - 测试文件更新

### 待验证

- [ ] 聚合归一化实现正确性验证
- [ ] 轨迹优化结果对比（修正前后）

## 下次开始建议

1. 完成聚合归一化代码变更的验证
2. 运行测试确认实现正确性
3. 考虑提交聚合归一化相关变更

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

### 文档结构

- `文档/INDEX.md` - 文档索引
- `文档/40_审查与诊断/archive/INDEX.md` - 归档索引
- `文档/10_模型与公式/` - 核心公式文档

---
*此文件由 endday 自动化工作流维护*