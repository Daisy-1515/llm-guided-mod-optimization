# 项目内存索引（MEMORY.md）

## 当前进度（更新于 2026-03-25）

### Phase⑤ 首次试跑 — S2 修复待验证

**现状**：Phase⑤-A~F 完成（2026-03-20）
- S1: ✅ PASS — 程序正常退出 + JSON 生成
- S2: ❌ FAIL — 当时 LLM api_error（glm-5 太慢）
- S3: ✅ PASS — 所有个体可行
- S4: ✅ PASS — 基线记录

**最新发现**（2026-03-25）：
- D1 诊断：LLM 修复已完全落地
  - 模型：`qwen3.5-plus`（快速非推理，响应 ~5s）
  - 代理：`Session(trust_env=False)` 绕代理有效
  - 验证：`check_llm_api.py` status=SUCCESS
- **结论**：根因 A/B/C 已修复，可直接启动 Phase⑤-G 重跑

**后续行动**：
1. 启动 Phase⑤-G：用修复的 LLM 重跑 3×3
2. 预期 S2 应该 PASS（≥1/3 个体使用自定义目标函数）

---

### Phase⑥ 轨迹优化 — 求解器致命问题

**现状**：Step 1-3 代码完成（2026-03-24）
- Step 1（propulsion.py）：✅ 完成 + 测试通过
- Step 2（resource_alloc.py）：✅ 完成 + 测试通过
- Step 3（trajectory_opt.py）：✅ 代码完成，❌ **求解器测试全失败**

**致命问题**（2026-03-25 D2 诊断）：
```
约束表达式非 DCP
位置：trajectory_opt.py:527-533
症状：所有求解器（CLARABEL/ECOS/SCS）拒绝
错误：DCPError: Problem does not follow DCP rules. var4 == quad
```

**根本原因**：通信时延约束的设计
```python
# 非凸组合 → DCP 检查失败
rate_safe = cp.maximum(rate_lb_expr, 1e-12)
dist_from_height = cp.sqrt(z)
delay_ub = 2.0 * dist_from_height * cp.inv_pos(rate_safe)
constraints.append(delay_ub <= tau_comm_budget + 1e-9)
```

**后续行动**：
1. **立即**：重新设计约束表达式为 DCP-safe 形式
   - 参考论文标准 SOCP 形式
   - 可能需要引入辅助变量或改用二阶锥约束
2. **并行**：增加诊断日志（捕获 exception、DCP check 结果）

---

### 参数可行性 — 部分约束过紧

**诊断结果**（2026-03-25 D3）：
| 工作负荷 | D_l | F | tau | D_hat_local | 可行? |
|--------|-----|-----|-----|------------|-------|
| 小 | 5e6 | 1e8 | 2.0 | 0.10s | ✅ |
| 中 | 1e7 | 5e8 | 1.0 | 0.50s | ✅ |
| 大 | 5e7 | 1e9 | 0.5 | 1.00s | ❌ |

**结论**：
- 2/3 可行（67%）— 不是"90% 不可行"
- **但大任务完全不可行** — `tau_max=0.5s` vs `D_hat_local=1.0s`
- **原因**：`tau ∝ [0.5, 2.0]s` 但 `D_l ∝ [5e6, 5e7] bits, F ∝ [1e8, 1e9] cycles`

**后续行动**：
1. 决策：放宽 `tau` 范围 OR 缩窄 `D_l/F` 生成范围
2. 或修改场景生成器的参数采样逻辑
3. 实施后重新验证可行性比例

---

## 下次开始建议

**优先级 1（本周）**：
- [ ] 启动 Phase⑤-G：3×3 重跑（用修复的 LLM API）
- [ ] 修复 trajectory_opt.py DCP 问题（约束重设计）
- [ ] 重跑 test_trajectory_opt.py（12 个测试应全部通过）

**优先级 2（后周）**：
- [ ] 参数调整决策与实施
- [ ] Phase⑤-G 完成（S1-S4 全 PASS）
- [ ] Phase⑥ 完整管道首跑

**优先级 3（四周后）**：
- [ ] 论文第三章：系统模型完整写作
- [ ] 消融实验设计与执行

---

## 相关文档引用

| 主题 | 位置 | 说明 |
|------|------|------|
| 首跑计划 | `文档/60_规划草案/首次试跑计划_Phase5_pipeline.md` | Phase⑤ 完整执行流程 |
| 诊断报告 | `文档/40_审查与诊断/Phase5_LLM调用问题诊断报告.md` | Phase⑤ LLM 链路完整分析 |
| 轨迹优化 | `文档/20_架构与实现/` | Phase⑥ 数学设计文档 |
| 当日日记 | `文档/70_工作日记/2026-03-25.md` | 本次诊断会话详细记录 |

---

## 历史里程碑

- **2026-03-20**：Phase⑤ 首次试跑 A-F 完成（S1/S3/S4 PASS，S2 FAIL）
- **2026-03-23**：Phase⑥ Step 1-2 代码完成（propulsion + resource_alloc 测试通过）
- **2026-03-24**：Phase⑥ Step 3 代码完成（trajectory_opt.py 727 行）
- **2026-03-25**：完整诊断运行 D1/D2/D3，发现求解器 DCP 问题 ← **你在这里**
