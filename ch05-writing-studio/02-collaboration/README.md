# 实验 14：多智能体协作机制实现

> 对应章节 5.2 多智能体协作 ｜ 2 学时 ｜ ✅ 已完成

## 概述

本实验在实验 13 的 5 个角色基础上，实现**完整的多智能体协作机制**，包括：

- **状态机驱动**：定义 5 个工作阶段 + 2 个终态（完成/失败）
- **工作流编排**：按 Planning → Writing → FactChecking → Polishing → Reviewing 顺序执行
- **质量门禁**：在 FactChecking 和 Reviewing 阶段设置质量检查点
- **反馈退回**：事实核查失败退回重写，审稿不通过退回润色或重写
- **冲突处理**：重试次数限制、降级通过、强制终止等策略

核心架构：

```
WorkflowOrchestrator（编排器）
    ↓
WorkflowContext（上下文）
    ↓
状态机循环：
  while not terminal_state:
      1. _execute_stage() → 执行当前阶段的 Agent
      2. _check_gate() → 质量门禁检查
      3. _handle_decision() → 根据决策流转状态（前进 / 退回 / 终止）
```

## 功能清单

| 功能 | 说明 |
|------|------|
| 状态机驱动 | 定义 7 种状态（5 个工作阶段 + 完成 + 失败）和状态转移规则 |
| 工作流编排 | 自动依次执行 5 个 Agent，管理数据依赖和执行顺序 |
| 质量门禁 | 在关键阶段（事实核查、审稿）设置质量检查点 |
| 反馈退回 | 事实核查 FAIL → 退回写作，审稿 REVISE → 退回润色/写作 |
| 重试控制 | 每个阶段最多重试 3 次（可配置），超限则降级或终止 |
| 上下文管理 | 记录所有阶段的输入输出、执行历史和退回记录 |
| 中间结果保存 | 每个阶段的输出都保存为 JSON，便于调试和分析 |
| 最终文章生成 | 流程完成后生成包含审稿意见的 Markdown 文章 |

## 文件结构

```
02-collaboration/
├── config.yaml.example        # LLM 配置参照
├── requirements.txt           # 依赖（与实验 13 相同）
│
├── src/
│   ├── main.py                # CLI 入口
│   ├── config.py              # 配置加载
│   │
│   ├── workflow/              # 工作流编排核心
│   │   ├── __init__.py
│   │   ├── state.py           # 状态定义（WorkflowState, ReviewDecision, FactCheckVerdict）
│   │   ├── context.py         # 上下文管理（WorkflowContext, StageRecord, RetryRecord）
│   │   ├── gate.py            # 质量门禁（QualityGate, GateDecision）
│   │   └── orchestrator.py    # 工作流编排器（WorkflowOrchestrator）
│   │
│   └── inherit/               # 继承自实验 13 的基础设施
│       └── agents/
│           └── agents/
│               └── write_studio/  # 5 个角色 Agent
│                   ├── base.py
│                   ├── planner.py
│                   ├── writer.py
│                   ├── fact_checker.py
│                   ├── polisher.py
│                   └── reviewer.py
│
├── prompts/                   # Prompt 模板（继承自实验 13）
└── output/                    # 运行输出
    └── <workflow_id>/         # 每次运行创建独立目录
        ├── planning_output.json
        ├── writing_output.json
        ├── fact_checking_output.json
        ├── polishing_output.json
        ├── reviewing_output.json
        ├── workflow_summary.json  # 执行摘要
        └── final_article.md       # 最终文章
```

## 快速开始

### 1. 安装依赖

```bash
cd ch05-writing-studio/02-collaboration
pip install -r requirements.txt
```

### 2. 配置 LLM

```bash
cp config.yaml.example config.yaml
# 编辑 config.yaml，填入你的 API Key
```

### 3. 运行

```bash
# 基本使用
python src/main.py --topic "为什么 Rust 越来越受欢迎"

# 完整参数
python src/main.py \
    --topic "AI 智能体的未来发展趋势" \
    --audience "技术管理者和架构师" \
    --goal "分析 AI Agent 的技术演进路径" \
    --words "3000-4000" \
    --tone "专业、前瞻" \
    --max-retries 2
```

## 核心机制详解

### 1. 状态机设计（`workflow/state.py`）

定义 7 种状态：

```python
class WorkflowState(str, Enum):
    PLANNING = "planning"          # 策划编辑
    WRITING = "writing"            # 内容作者
    FACT_CHECKING = "fact_checking"  # 事实核查
    POLISHING = "polishing"        # 润色编辑
    REVIEWING = "reviewing"        # 审稿主编
    COMPLETED = "completed"        # 流程完成
    FAILED = "failed"              # 流程失败
```

状态转移规则：

```
正向流程：
  PLANNING → WRITING → FACT_CHECKING → POLISHING → REVIEWING → COMPLETED

退回路径：
  FACT_CHECKING --[FAIL]--> WRITING
  REVIEWING --[REVISE_POLISH]--> POLISHING
  REVIEWING --[REVISE_WRITE]--> WRITING
  
终止条件：
  - 审稿 REJECT
  - 超过最大重试次数
  - 执行异常
```

### 2. 协作上下文（`workflow/context.py`）

`WorkflowContext` 负责在 Agent 间共享数据：

```python
@dataclass
class WorkflowContext:
    # 用户输入
    topic: str
    audience: str
    goal: str
    word_count: str
    tone: str
    
    # 当前状态
    current_state: WorkflowState
    
    # 各阶段输出
    planner_output: dict | None
    writer_output: dict | None
    fact_checker_output: dict | None
    polisher_output: dict | None
    reviewer_output: dict | None
    
    # 执行历史
    history: list[StageRecord]
    retry_records: list[RetryRecord]
    retry_counts: dict[WorkflowState, int]
```

关键方法：

| 方法 | 功能 |
|------|------|
| `start_stage()` | 记录阶段开始时间和输入 |
| `complete_stage()` | 记录阶段完成时间和输出 |
| `record_retry()` | 记录退回重做信息 |
| `can_retry()` | 判断是否还能重试 |
| `get_latest_content()` | 获取最新文章内容 |
| `to_summary()` | 生成执行摘要 |

### 3. 质量门禁（`workflow/gate.py`）

`QualityGate` 在关键阶段设置检查点：

#### 事实核查门禁

```python
def check_fact_checking(self, output: dict, retry_count: int) -> GateDecision:
    verdict = FactCheckVerdict(output["verdict"])
    
    if verdict == PASS:
        return GateDecision.approve(WorkflowState.POLISHING)
    
    if verdict == FAIL:
        if retry_count >= max_retries:
            return GateDecision.terminate("事实核查失败且超过重试次数")
        else:
            return GateDecision.reject(WorkflowState.WRITING, "退回重写")
```

#### 审稿门禁

```python
def check_reviewing(self, output: dict, writing_retry: int, polishing_retry: int) -> GateDecision:
    decision = ReviewDecision(output["decision"])
    
    if decision == APPROVE:
        return GateDecision.approve(WorkflowState.COMPLETED)
    
    if decision == REVISE_POLISH:
        if polishing_retry >= max_retries:
            return GateDecision.approve(WorkflowState.COMPLETED, "降级通过")
        else:
            return GateDecision.reject(WorkflowState.POLISHING, "退回润色")
    
    if decision == REVISE_WRITE:
        if writing_retry >= max_retries:
            # 降级退回润色或强制通过
            return GateDecision.reject(WorkflowState.POLISHING, "降级退回润色")
        else:
            return GateDecision.reject(WorkflowState.WRITING, "退回重写")
    
    if decision == REJECT:
        return GateDecision.terminate("审稿拒绝")
```

### 4. 工作流编排器（`workflow/orchestrator.py`）

`WorkflowOrchestrator` 是协作引擎的核心：

```python
def run(self, ctx: WorkflowContext) -> WorkflowContext:
    while not ctx.current_state.is_terminal():
        try:
            # 1. 执行当前阶段
            self._execute_stage(ctx)
            
            # 2. 质量门禁检查
            decision = self._check_gate(ctx)
            
            # 3. 根据决策流转状态
            self._handle_decision(ctx, decision)
            
        except Exception as e:
            ctx.fail_stage(ctx.current_state, str(e))
            ctx.current_state = WorkflowState.FAILED
            break
    
    # 保存结果
    self._save_final_result(ctx)
    return ctx
```

关键子流程：

- **`_execute_stage()`**：选择对应 Agent，准备输入，执行并记录输出
- **`_prepare_input()`**：从 context 读取前序结果，构造当前 Agent 的输入
- **`_check_gate()`**：调用 QualityGate 检查当前阶段输出
- **`_handle_decision()`**：根据门禁决策更新状态（前进 / 退回 / 终止）
- **`_clear_outputs_after()`**：退回时清除目标阶段之后的所有输出

### 5. 冲突处理策略

| 场景 | 策略 |
|------|------|
| 事实核查失败 | 退回写作重做，超过 3 次则终止流程 |
| 审稿建议润色 | 退回润色，超过 3 次则降级通过 |
| 审稿建议重写 | 退回写作，超过 3 次则降级退回润色，润色也超限则强制通过 |
| 审稿拒绝 | 直接终止流程 |
| Agent 执行异常 | 捕获异常，标记失败，终止流程 |

降级通过的设计理念：**避免无限循环，在质量和效率间平衡**。

## 输出效果

### 1. 控制台输出

```
======================================================================
写作工作室协作流程启动
======================================================================
工作流 ID: 20260726_183000
主题: 为什么 Rust 越来越受欢迎
读者: 有一定技术背景的读者
目标: 清晰解释概念，提供实用建议
最大重试次数: 3
======================================================================

──────────────────────────────────────────────────────────────────────
阶段：PLANNING
──────────────────────────────────────────────────────────────────────
执行 Agent: 策划编辑...
✓ 阶段 planning 完成

[门禁] 策划完成，进入写作阶段
[流转] planning → writing

──────────────────────────────────────────────────────────────────────
阶段：WRITING
──────────────────────────────────────────────────────────────────────
执行 Agent: 内容作者...
✓ 阶段 writing 完成

[门禁] 初稿完成，进入事实核查阶段
[流转] writing → fact_checking

... (省略)

[门禁] 事实核查发现 2 个严重问题，退回重写（第 1 次）
[退回] fact_checking → writing（第 1 次重试）

... (省略)

[门禁] 审稿通过（综合评分：85），文章发布
[流转] reviewing → completed

======================================================================
工作流执行完毕
======================================================================
最终状态: completed
执行阶段数: 7
退回重做次数: 1

共 1 次退回重做：
  1. fact_checking → writing (第 1 次): 事实核查发现 2 个严重问题，退回重写

输出目录: output/20260726_183000
======================================================================

✓ 写作流程成功完成！
```

### 2. 输出文件

#### `workflow_summary.json` — 执行摘要

```json
{
  "workflow_id": "20260726_183000",
  "topic": "为什么 Rust 越来越受欢迎",
  "current_state": "completed",
  "started_at": "2026-07-26T18:30:00",
  "completed_at": "2026-07-26T18:35:23",
  "duration_seconds": 323.5,
  "stages_executed": 7,
  "retry_count": 1,
  "retry_summary": "共 1 次退回重做：\n  1. fact_checking → writing (第 1 次): 事实核查发现 2 个严重问题，退回重写",
  "final_content_available": true
}
```

#### `final_article.md` — 最终文章

```markdown
# 为什么 Rust 越来越受欢迎

> 作者：AI 写作工作室
> 目标读者：有一定技术背景的读者
> 综合评分：85
> 工作流 ID：20260726_183000

---

[文章内容]

---

## 执行信息

共 1 次退回重做：
  1. fact_checking → writing (第 1 次): 事实核查发现 2 个严重问题，退回重写
```

## 实验要求对照

| 要求级别 | 内容 | 实现情况 |
|---------|------|---------|
| 基本（了解） | 能说明常见多智能体协作模式 | ✅ README 详细说明状态机、上下文、门禁等协作模式 |
| 合格（理解） | 能实现工作流编排（策划→创作→核查→润色→审稿） | ✅ WorkflowOrchestrator 实现完整 5 阶段编排 |
| 进阶（掌握） | 能实现反馈退回、质量门禁和冲突处理机制 | ✅ QualityGate + 重试控制 + 降级通过策略 |

## 与实验 13 的关系

| 实验 13（角色设计） | 实验 14（协作机制） |
|-------------------|-------------------|
| 定义 5 个独立 Agent | 将 5 个 Agent 串成工作流 |
| 单角色独立运行 | 状态机驱动多角色协作 |
| 输入输出契约定义 | 上下文管理 + 数据依赖 |
| 无质量检查 | 质量门禁 + 退回重做 |
| 手动运行单个角色 | 自动编排完整流程 |

实验 14 **复用**实验 13 的所有 Agent 代码，只新增工作流编排层。

## 实验流程

| 步骤 | 内容 | 预计时间 |
|------|------|----------|
| 1 | 阅读 `src/workflow/state.py`，理解状态机设计 | 15min |
| 2 | 阅读 `src/workflow/context.py`，理解上下文管理 | 15min |
| 3 | 阅读 `src/workflow/gate.py`，理解质量门禁机制 | 20min |
| 4 | 阅读 `src/workflow/orchestrator.py`，理解编排器核心流程 | 30min |
| 5 | 运行完整协作流程，观察控制台输出和中间结果 | 20min |
| 6 | 修改 `max_retries` 参数，观察降级通过行为 | 20min |
| 7 | （进阶）修改门禁规则，实现自定义质量标准 | 60min |

## 常见问题

### Q1: 如何调整重试次数？

```bash
python src/main.py --topic "主题" --max-retries 2
```

或修改 `WorkflowContext` 的 `max_retries` 默认值。

### Q2: 如何自定义门禁规则？

编辑 `src/workflow/gate.py` 中的 `check_fact_checking()` 和 `check_reviewing()` 方法，修改决策逻辑。

例如，将事实核查的 `PASS_WITH_WARNINGS` 也视为失败：

```python
if verdict in (FactCheckVerdict.FAIL, FactCheckVerdict.PASS_WITH_WARNINGS):
    return GateDecision.reject(WorkflowState.WRITING, "退回重写")
```

### Q3: 如何跳过某个阶段？

不建议跳过，但如果需要，可以修改 `orchestrator.py` 中的 `_check_gate()` 方法，对特定阶段直接返回 `GateDecision.approve()`。

### Q4: 退回重做时会清除哪些数据？

`_clear_outputs_after()` 会清除退回目标阶段及其之后的所有输出。例如，退回到 WRITING 时，会清除 writer_output、fact_checker_output、polisher_output、reviewer_output。

## 扩展方向

1. **并行执行**：将事实核查和润色改为并行（需要修改状态机）
2. **人工审核**：在关键阶段加入人工确认步骤
3. **A/B 测试**：同时生成多个版本，由 Reviewer 选择最佳
4. **增量编辑**：退回时提供详细修改建议，而非完全重写
5. **流式输出**：支持 SSE 实时展示各阶段进度
