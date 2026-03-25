# llm-guided-mod-optimization 项目 CLAUDE.md

## 当前状态（自动更新）

**更新时间**: 2026-03-25 16:15:52

### 项目进度
- **Phase Status**: 🟡 Phase⑥ in progress (Step1/2/3 in development)
- **Latest Commit**: dddde3c refactor: 改进 analyze_results.py 动态读取 HS 迭代数配置

### 最新运行结果
- **Latest Run**: `20260325_152149/` (10 generations)
- **Status**: Check with `python analyze_results.py --run-dir 20260325_152149/`

### LLM 配置
- **LLM Model**: `qwen3.5-plus` (config/setting.cfg:7)
- **HS Parameters**: popSize=5, iteration=10
- **Endpoint**: CloseAI (api.openai-proxy.org)

## 快速命令

```bash
uv sync                      # 环境设置
python testEdgeUav.py        # 运行 Edge UAV 管道
python analyze_results.py    # 验证结果
pytest tests/ -v             # 运行全部测试
```

## 文件地图

**原始 MoD 系统**:
- `scenarioGenerator.py` — 场景生成
- `AssignmentModel.py`, `SequencingModel.py` — 优化模型
- `SimClass.py` — 仿真评估

**Edge UAV 系统** (Phase④-⑤ 已完成，⑥ 进行中):
- `edge_uav/model/` — 物理模型 (offloading / propulsion / resource_alloc / trajectory_opt)
- `edge_uav/prompt/` — 提示工程
- `heuristics/hsIndividualEdgeUav.py` — HS 个体评估

**LLM 接口**:
- `llmAPI/llmInterface_huggingface.py` — OpenAI 兼容接口

**测试套件**: `tests/test_*.py` (62 tests)

## 常见任务

### 切换 LLM 模型
编辑 `config/setting.cfg`:
```ini
[llmSettings]
model = qwen3.5-plus    # or deepseek-chat, gpt-4o, etc.
```

### 修改 HS 参数
编辑 `config/setting.cfg`:
```ini
[hsSettings]
popSize = 5
iteration = 10
```

### 运行完整管道
```bash
python testEdgeUav.py --popsize=5 --iteration=10
python analyze_results.py --run-dir discussion/LATEST_RUN/
```

## 详细文档

- **全局指导**: `.claude/CLAUDE.md` (深度设计、架构决策)
- **全局进度**: `MEMORY.md` (跨会话追踪)
- **数学模型**: `文档/10_模型与公式/公式.md`
- **工作日记**: `文档/70_工作日记/YYYY-MM-DD.md`
- **诊断报告**: `文档/40_审查与诊断/`

## 下一步里程碑

- [ ] Phase⑥ Step3: 解决 DCP 约束非凸性问题
- [ ] 完整 HS + BCD 集成和验证
- [ ] 论文第 3 章完稿

---
*本文件由 `/endday` skill 自动维护（当前状态部分）。其他部分可手动编辑。*
