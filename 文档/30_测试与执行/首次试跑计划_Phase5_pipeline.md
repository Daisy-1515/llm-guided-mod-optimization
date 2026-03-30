---
⚠️ **归档文档** — 不再活跃维护

**状态**：存档于 archive/ 目录
**最后更新**：2026-03-19
**理由**：历史试跑计划，对应 Phase⑤ 首次运行，后续已执行多轮完整 pipeline 验证（见工作日记 70_工作日记）
**当前参考**：见工作日记和 CLAUDE.md 的最新实验报告

---

# 完整 Pipeline 首次试跑 — 详细计划

> 生成日期：2026-03-19
> 状态：历史试跑计划（该”待执行”状态仅对应 2026-03-19）
> 说明：后续运行结果与项目最新状态请以 `CLAUDE.md` 和
> `文档/70_工作日记/2026-03-27.md` 为准。

## Context

Phase ①-④ 已全部完成（62/62 测试），代码架构已就绪：
- Harmony Search 框架已接入 Edge UAV 个体
- LLM API（glm-5 via CloseAI）已配置并完成通用响应解析改造
- 工作区有 6 个文件（+59/-21）的加固改动未提交

**本计划目标**：完成从代码提交到真实 LLM 驱动 HS 优化的首次端到端试跑，并建立可复现的实验基线。

---

## 成功判据（必须在试跑结束时验证）

| 判据 | 说明 |
|------|------|
| S1 | testEdgeUav.py 正常退出（exit 0），./discussion/ 下有 JSON 文件 |
| S2 | 至少 1/3 个体 `llm_status="ok"` 且 `used_default_obj=false` |
| S3 | 至少 1 个个体 `feasible=true`（Gurobi 接受自定义目标并求解成功） |
| S4 | 控制组（全默认目标）基线分数已记录，可与 LLM 驱动分数比较 |

> 注：脚本退出 0 ≠ 成功。若所有个体都回退到默认目标，pipeline 虽然运行但 LLM 实际上没有起作用。

---

## 阶段 A：提交当前变更（基线冻结）

**目的**：在首跑前建立干净的 git 基线，确保可回滚。

```bash
git add config/config.py edge_uav/model/offloading.py \
    heuristics/hsIndividualEdgeUav.py heuristics/hsPopulation.py \
    llmAPI/llmInterface_huggingface.py testEdgeUav.py
git commit -m "chore: harden pipeline for first real LLM trial run"
git rev-parse HEAD  # 记录 SHA
```

**产出**：干净 commit，git status 工作区干净（除 .env 和安全审查报告）。

---

## 阶段 B：最小可观测性前置（首跑前必须完成）

> 可观测性必须前置，不是首跑后再加。

### B1：结果归档（防覆盖）

**文件**：`heuristics/hsFrame.py`

```python
# __init__ 中新增
import datetime
self.run_id = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
self.out_dir = f"discussion/{self.run_id}"
os.makedirs(self.out_dir, exist_ok=True)

# save_population 中
filename = f"{self.out_dir}/population_result_{generation}.json"
```

### B2：进度日志

**文件**：`heuristics/hsPopulation.py`

```python
print(f"[HS] Gen {gen}: evaluating {len(futures)} individuals...")
print(f"[HS] Gen {gen}: done. llm_ok={ok_cnt}, feasible={feas_cnt}")
```

### B3：首跑统计摘要

**文件**：`heuristics/hsFrame.py`

```python
print(f"[HS] Run complete. Results: {self.out_dir}/")
print(f"[HS] Best eval_score: {sortPop[0]['evaluation_score']:.4f}")
```

---

## 阶段 C：离线预飞检查

| 检查项 | 命令 | 期望结果 |
|--------|------|----------|
| C1 Python 环境 | `.venv/Scripts/python --version` | Python 3.10+ |
| C2 依赖完整性 | `.venv/Scripts/python -c "import gurobipy, configobj, dotenv"` | 无报错 |
| C3 Gurobi License | `.venv/Scripts/python -c "import gurobipy as gb; m=gb.Model(); print('OK')"` | 打印 OK |
| C4 配置加载 | `.venv/Scripts/python -c "from config.config import configPara; p=configPara(None,None); p.getConfigInfo(); print(p.llmModel, p.api_endpoint)"` | 显示 glm-5 和 endpoint |
| C5 API Key 存在 | 同上 + `print(bool(p.api_key))` | True |
| C6 场景生成+预计算 | `.venv/Scripts/python -m pytest tests/test_s7_offloading_e2e.py -v` | 4/4 通过 |
| C7 控制组基线 | 手动运行默认目标（无 LLM），记录 eval_score | 数字基线 |

---

## 阶段 D：在线预飞（阶梯式，不可跳过）

### D1：单次 API 连通性
```python
# test_api_ping.py
from config.config import configPara
from llmAPI.llmInterface_huggingface import llmHuggingFace
p = configPara(None, None)
p.getConfigInfo()
api = llmHuggingFace(p)
resp = api.getResponse('{"obj_description": "test", "obj_code": "def dynamic_obj_func(self): pass"}')
print("RAW:", resp[:500])
```
**Go 条件**：收到非空响应，耗时 < 30s。

### D2：单个体完整生命周期（way1）
```bash
# testEdgeUav.py 临时改 popSize=1, iteration=1
.venv/Scripts/python scripts/testEdgeUav.py
# 检查 discussion/{run_id}/population_result_0.json
# 验证: llm_status, used_default_obj, feasible, evaluation_score
```
**Go 条件**：JSON 存在，evaluation_score < 1e12。

### D3：way2/3/4 路由覆盖
- 确认 hsPopulation.py 的 generate_new_harmony 能正常路由到 4 种 way

### D4：并发稳定性（2 路并发）
```bash
# popSize=2, iteration=1
# 检查 2 个个体均在 300s 内返回
```

---

## 阶段 E：首次 HS 试跑

### E1：1×1 最小烟雾测试
```bash
# popSize=1, iteration=1
.venv/Scripts/python scripts/testEdgeUav.py 2>&1 | tee logs/run_1x1.log
```

### E2：3×3 正式首跑
```bash
# popSize=3, iteration=3（testEdgeUav.py 默认值）
mkdir -p logs
.venv/Scripts/python scripts/testEdgeUav.py 2>&1 | tee logs/run_3x3_$(date +%Y%m%d_%H%M%S).log
```
**预期耗时**：3-10 分钟（并发 3，每个体 LLM ~5-15s + Gurobi ~2-10s）。

---

## 阶段 F：结果分析脚本

```python
# analyze_results.py
import json, glob, os

run_dir = sorted(glob.glob('discussion/202*'))[-1]
all_inds = []
for f in sorted(glob.glob(f'{run_dir}/population_result_*.json')):
    with open(f) as fp:
        data = json.load(fp)
    for ind in data:
        ind['_file'] = os.path.basename(f)
        all_inds.append(ind)

llm_ok = sum(1 for x in all_inds if x.get('llm_status') == 'ok')
default_obj = sum(1 for x in all_inds if x.get('used_default_obj', True))
feasible = sum(1 for x in all_inds if x.get('feasible', False))
print(f"Total individuals: {len(all_inds)}")
print(f"llm_status=ok:        {llm_ok}/{len(all_inds)}")
print(f"used_default_obj=F:   {len(all_inds)-default_obj}/{len(all_inds)}")
print(f"feasible=True:        {feasible}/{len(all_inds)}")
scores = [x.get('evaluation_score', 1e12) for x in all_inds]
print(f"Best eval_score:      {min(scores):.4f}")
print("\nScore trend by gen:")
for f in sorted(glob.glob(f'{run_dir}/population_result_*.json')):
    with open(f) as fp:
        gen_data = json.load(fp)
    best = min(x.get('evaluation_score', 1e12) for x in gen_data)
    print(f"  {os.path.basename(f)}: best={best:.4f}")
```

---

## 阶段 G：卡点定位 + 修复

| 症状 | 可能原因 | 检查位置 |
|------|----------|----------|
| 所有 llm_status=api_error | API 连通失败 / key 错误 / 超时 | logs 中的 LLM 报错 |
| 所有 used_default_obj=true | JSON 解析失败（格式不符） | full_info[raw_llm_response] |
| 所有 feasible=false | tau 仍然太紧 / BLP 约束冲突 | offloading_model_*.ilp 文件 |
| Gurobi 报错 | exec() 注入代码有语法错误 | full_info[llm_error] |
| 线程超时 / 300s 无结果 | 并发 LLM 调用被限流 | hsPopulation 日志 |

| 问题 | 修复方案 |
|------|----------|
| LLM 响应格式不对 | 加强 mod_prompt.py 的 JSON 格式约束 |
| tau 可行性问题 | 再调大 tau 到 500s，或减小任务 F |
| 并发限流 | 降低 max_workers=1 串行，或加请求间隔 |
| exec() 代码错误 | 加 try/except 捕获 exec 异常，打印错误代码 |

---

## 阶段 H：风险矩阵

| 风险 | 概率 | 影响 | 缓解 |
|------|------|------|------|
| LLM 返回非 JSON 格式 | 高 | 所有个体 used_default_obj=true | 加强 prompt 约束；检查 raw_llm_response |
| glm-5 生成非法 Gurobi 代码 | 中 | exec() 报错，回退默认 | 加 exec 异常捕获 |
| API 并发限流 (429) | 中 | 超时回退 | 降 max_workers；加重试间隔 |
| BLP 全部不可行 | 低（tau=200s 已放宽） | feasible=false | 进一步放宽 tau |
| 结果被覆盖（未做 B1） | 高 | 数据丢失 | B1 必须在 E 之前完成 |
| exec() 安全风险 | 中（研究环境可接受） | 代码注入 | 已知风险，研究环境内可接受 |

---

## 执行顺序

```
A（提交加固）
  └─ B1+B2+B3（并行改代码）→ 提交 B
      ├─ C（离线预飞 C1-C7，顺序）
      └─ D（在线预飞 D1→D2→D3→D4，顺序）
          └─ E1（1×1 烟雾）
              └─ E2（3×3 正式首跑）
                  └─ F（analyze_results.py）
                      └─ G（如需修复 → 重跑 E2）
```

## 关键文件

| 文件 | 角色 |
|------|------|
| `testEdgeUav.py` | 入口，控制 popSize/iter/tau |
| `heuristics/hsFrame.py` | HS 主循环，save_population（B1 改这里）|
| `heuristics/hsPopulation.py` | 并发管理，进度日志（B2 改这里）|
| `heuristics/hsIndividualEdgeUav.py` | 个体生命周期，llm_status/used_default_obj |
| `edge_uav/model/offloading.py` | Gurobi BLP，exec() 注入点 |
| `edge_uav/prompt/mod_prompt.py` | way1-4 prompt 模板 |
| `llmAPI/llmInterface_huggingface.py` | API 调用，重试，响应解析 |
| `config/setting.cfg` + `config/env/.env` | LLM endpoint/key 配置 |
| `discussion/{run_id}/` | 首跑结果输出目录（B1 新建）|
| `analyze_results.py` | 首跑后统计分析脚本（阶段 F）|

