# 实验 15：写作工作室智能体综合实践

> 对应章节 5.3 写作工作室综合实践 ｜ 2 学时 ｜ ✅ 已完成

## 概述

本实验在实验 13 的角色设计和实验 14 的协作机制基础上，运行一个完整的**多智能体写作工作室系统**，生成一篇技术博客或课程案例文章，并通过评估分析文章质量、角色表现和协作效果。

本节新增 **Researcher（资料研究员）智能体**，用于在写作前收集背景资料、关键发现和参考来源，使写作流程从“按大纲生成文章”扩展为“先策划、再研究、再写作、再核查和审稿”的完整生产流程。

核心流程：

```
Planner → Researcher → Writer → FactChecker → Polisher → Reviewer → Evaluator
```

其中 Researcher 可通过 `--enable-researcher` 开启；Evaluator 通过独立的 `evaluate` 命令运行，用于对已生成的工作流结果进行综合评估。

## 功能清单

| 功能 | 命令 | 说明 |
|------|------|------|
| 生成文章 | `python src/main.py generate --topic "主题"` | 运行完整写作工作流，生成最终文章 |
| 启用资料研究 | `python src/main.py generate --topic "主题" --enable-researcher` | 在 Planner 和 Writer 之间加入 Researcher |
| 文件输入 | `python src/main.py generate --from-file data/topics/example.json` | 从 JSON 文件读取主题、读者、目标等参数 |
| 综合评估 | `python src/main.py evaluate --workflow-dir output/<workflow_id>` | 评估输出质量、角色表现和协作效果 |
| 质量门禁 | 自动执行 | 根据阶段输出决定通过、退回或终止 |
| 中间结果保存 | 自动执行 | 保存每个 Agent 的输出 JSON，便于分析问题 |
| 最终文章生成 | 自动执行 | 生成 `final_article.md` |
| 工作流摘要 | 自动执行 | 生成 `workflow_summary.json`，记录耗时、阶段和重试信息 |
| 评估报告 | `evaluate` 命令生成 | 生成 `evaluation_report.json` |

## 文件结构

```
03-integration/
├── config.yaml.example        # LLM 和 Tavily 配置参照
├── requirements.txt           # 实验依赖
│
├── prompts/                   # Jinja2 提示词模板
│   └── agents/
│       └── write_studio/
│           ├── planner/       # 策划编辑 prompt
│           ├── researcher/    # 资料研究员 prompt
│           ├── writer/        # 内容作者 prompt
│           ├── fact_checker/  # 事实核查员 prompt
│           ├── polisher/      # 润色编辑 prompt
│           ├── reviewer/      # 审稿主编 prompt
│           └── stage_evaluator/  # 阶段评估 prompt
│
├── src/
│   ├── main.py                # CLI 入口（generate / evaluate）
│   ├── config.py              # 配置加载（基于 Pydantic）
│   │
│   ├── agents/
│   │   └── write_studio/
│   │       ├── base.py        # BaseRoleAgent 基类
│   │       ├── planner.py     # PlannerAgent（策划编辑）
│   │       ├── researcher.py  # ResearcherAgent（资料研究员）
│   │       ├── writer.py      # WriterAgent（内容作者）
│   │       ├── fact_checker.py# FactCheckerAgent（事实核查员）
│   │       ├── polisher.py    # PolisherAgent（润色编辑）
│   │       ├── reviewer.py    # ReviewerAgent（审稿主编）
│   │       │
│   │       ├── workflow/      # 工作流编排核心
│   │       │   ├── state.py   # 状态定义
│   │       │   ├── context.py # 上下文管理
│   │       │   ├── gate.py    # 质量门禁
│   │       │   └── orchestrator.py  # 工作流编排器
│   │       │
│   │       └── evaluation/    # 评估模块
│   │           ├── stage_evaluator.py
│   │           └── workflow_evaluator.py
│   │
│   └── inherit/               # 继承自前序实验的 LLM、Prompt 和工具能力
│
└── output/                    # 运行输出
    └── <workflow_id>/         # 每次运行创建独立目录
        ├── planning_output.json
        ├── researching_output.json  # 启用 Researcher 时生成
        ├── writing_output.json
        ├── fact_checking_output.json
        ├── polishing_output.json
        ├── reviewing_output.json
        ├── workflow_summary.json
        ├── evaluation_report.json   # evaluate 后生成
        └── final_article.md
```

## 快速开始

### 1. 安装依赖

```bash
cd ch05-writing-studio/03-integration
pip install -r requirements.txt
```

### 2. 配置 LLM 和搜索工具

```bash
cp config.yaml.example config.yaml
# 编辑 config.yaml，填入 LLM API Key、模型参数和 Tavily API Key（可选）
```

配置文件示例：

```yaml
llm:
  provider: "deepseek"
  base_url: "https://api.deepseek.com"
  model: "deepseek-v4-flash"
  api_key_env: "sk-..."

generation:
  temperature: 0.8
  top_p: 0.95
  max_tokens: 4096

tavily:
  api_key: ""
  max_results: 5
  include_answer: false
```

> ⚠️ `config.yaml` 已被 `.gitignore` 排除，不会提交到 Git。当前代码中 `llm.api_key_env` 字段直接作为 API Key 传入客户端。

### 3. 运行生成流程

```bash
# 基础模式：Planner → Writer → FactChecker → Polisher → Reviewer
python src/main.py generate --topic "大模型智能体在课程案例生成中的应用"

# 增强模式：Planner → Researcher → Writer → FactChecker → Polisher → Reviewer
python src/main.py generate \
    --topic "大模型智能体在课程案例生成中的应用" \
    --audience "人工智能课程学习者" \
    --goal "生成一篇可用于课堂讨论的技术案例文章" \
    --words "2000-3000" \
    --tone "专业、清晰、案例化" \
    --enable-researcher
```

### 4. 从 JSON 文件读取主题

```json
{
  "topic": "多智能体协作在技术博客写作中的应用",
  "target_audience": "有一定 Python 和大模型基础的本科生",
  "writing_goal": "解释多智能体写作流程，并给出课程案例分析",
  "word_count": "2000-3000",
  "tone": "专业、易懂、适合教学",
  "requirements": ["包含流程说明", "包含角色分工", "包含质量评估和优化建议"],
  "constraints": ["避免空泛介绍", "尽量结合写作工作室案例"]
}
```

运行：

```bash
python src/main.py generate --from-file data/topics/example.json --enable-researcher
```

### 5. 运行综合评估

生成文章后，控制台会提示评估命令：

```bash
python src/main.py evaluate --workflow-dir output/<workflow_id>
```

评估完成后，会在同一目录生成 `evaluation_report.json`。

## 核心机制详解

### 1. 集成工作流（`workflow/orchestrator.py`）

`WorkflowOrchestrator` 负责把角色执行、上下文传递、质量门禁和文件保存串联起来。

启用 Researcher 时的正向流程：

```
PLANNING → RESEARCHING → WRITING → FACT_CHECKING → POLISHING → REVIEWING → COMPLETED
```

未启用 Researcher 时的正向流程：

```
PLANNING → WRITING → FACT_CHECKING → POLISHING → REVIEWING → COMPLETED
```

关键子流程：

- **`_prepare_input()`**：从 `WorkflowContext` 读取前序输出，构造当前 Agent 输入；
- **`_get_agent()`**：根据当前状态选择 Planner、Researcher、Writer 等 Agent；
- **`_check_gate()`**：调用质量门禁判断当前阶段是否通过；
- **`_handle_decision()`**：根据门禁结果前进、退回或终止；
- **`_save_final_result()`**：保存最终文章、工作流摘要和中间结果。

### 2. Researcher 资料研究（`researcher.py`）

Researcher 的输入来自 Planner：

```python
ResearcherInput(
    topic=ctx.topic,
    audience=ctx.audience,
    core_message=ctx.planner_output["core_message"],
    outline=ctx.planner_output["outline"],
    search_keywords=ctx.planner_output.get("search_keywords", []),
)
```

Researcher 的输出会传给 Writer：

```python
researcher_data = {
    "research_sources": ctx.researcher_output.get("sources", []),
    "key_findings": ctx.researcher_output.get("key_findings", []),
    "background_context": ctx.researcher_output.get("background_context", ""),
}
```

它的作用是把 Planner 的写作计划转化为可供 Writer 使用的资料包，包括：

- 背景资料；
- 关键发现；
- 参考来源；
- 最新进展；
- 写作建议。

### 3. 质量门禁（`workflow/gate.py`）

质量门禁负责判断每个阶段输出是否足以进入下一阶段。

| 阶段 | 主要检查内容 | 可能结果 |
|------|--------------|----------|
| Planning | 是否生成大纲、核心观点和写作建议 | 进入 Researching 或 Writing |
| Researching | 是否生成资料来源和关键发现 | 进入 Writing 或终止 |
| Writing | 是否生成文章正文 | 进入 FactChecking |
| FactChecking | 是否通过事实核查 | 进入 Polishing 或退回 Writing |
| Polishing | 是否生成润色后正文 | 进入 Reviewing |
| Reviewing | 是否达到终审标准 | 完成、退回 Polishing、退回 Writing 或终止 |

### 4. 综合评估（`evaluation/`）

本实验采用**综合评估**模式：

- `generate`：只负责生成文章和保存工作流数据；
- `evaluate`：读取指定 `output/<workflow_id>/`，评估文章质量、角色表现和协作效果。

评估模块包含：

- `StageEvaluator`：评估单个阶段输出；
- `WorkflowEvaluator`：汇总阶段评分、角色表现、流程问题和优化建议。

这种设计使生成和评估解耦，便于对同一次生成结果多次评估，也便于调整评估标准。

## 输出效果

### 1. 控制台输出

```
======================================================================
模式：生成文章
======================================================================

======================================================================
写作工作室协作流程启动
======================================================================
工作流 ID: 20260726_232816
主题: 大模型智能体在课程案例生成中的应用
读者: 人工智能课程学习者
目标: 生成一篇可用于课堂讨论的技术案例文章
Researcher: 启用
最大重试次数: 3
======================================================================

──────────────────────────────────────────────────────────────────────
阶段：PLANNING
──────────────────────────────────────────────────────────────────────
执行 Agent: 策划编辑...
✓ 阶段 planning 完成

[门禁] 策划完成，进入资料研究阶段
[流转] planning → researching

...（省略中间阶段）

[门禁] 审稿通过，文章发布
[流转] reviewing → completed

======================================================================
工作流执行完毕
======================================================================
最终状态: completed
输出目录: output/20260726_232816
======================================================================

✓ 写作流程成功完成！
✓ Researcher 增强模式已启用

文章已保存到：output/20260726_232816/final_article.md

如需评估文章质量，运行：
  python src/main.py evaluate --workflow-dir output/20260726_232816
```

### 2. 输出文件

#### `workflow_summary.json` — 工作流执行摘要

```json
{
  "workflow_id": "20260726_232816",
  "topic": "大模型智能体在课程案例生成中的应用",
  "current_state": "completed",
  "duration_seconds": 512.4,
  "stages_executed": 6,
  "retry_count": 0,
  "final_content_available": true
}
```

#### `evaluation_report.json` — 综合评估报告

```json
{
  "workflow_id": "20260726_232816",
  "topic": "大模型智能体在课程案例生成中的应用",
  "overall_score": 8,
  "stage_performances": [],
  "collaboration_analysis": {},
  "optimization_suggestions": []
}
```

#### `final_article.md` — 最终文章

```markdown
# 大模型智能体在课程案例生成中的应用

> 作者：AI 写作工作室
> 工作流 ID：20260726_232816

---

[文章内容]
```

## 实验要求对照

| 要求级别 | 内容 | 实现情况 |
|---------|------|---------|
| 基本（了解） | 能运行完整写作工作室智能体并生成文章 | ✅ `generate` 命令运行完整流程并生成 `final_article.md` |
| 合格（理解） | 能评估输出质量、角色表现和协作效果 | ✅ `evaluate` 命令生成 `evaluation_report.json`，结合 `workflow_summary.json` 分析流程 |
| 进阶（掌握） | 能识别流程衔接或输出质量问题并进行针对性优化 | ✅ 可通过修改 Prompt、门禁规则、Researcher 搜索策略或阶段输入传递进行优化 |

## 与实验 13 / 14 的关系

| 实验 13（角色设计） | 实验 14（协作机制） | 实验 15（综合实践） |
|-------------------|-------------------|-------------------|
| 定义 Planner、Writer 等基础角色 | 用状态机串联 5 个角色 | 加入 Researcher 和 Evaluator，形成完整实践闭环 |
| 强调输入输出契约和 Prompt 模板 | 强调上下文、门禁和退回机制 | 强调生成、评估、诊断和优化 |
| 可运行单角色或基础流水线 | 可运行完整协作流程 | 可生成文章并评估角色表现与协作质量 |

实验 15 **复用**实验 13 的角色抽象和实验 14 的工作流思想，并新增资料研究和综合评估能力。

## 实验流程

| 步骤 | 内容 | 预计时间 |
|------|------|----------|
| 1 | 阅读 `src/main.py`，理解 `generate` 和 `evaluate` 两种运行模式 | 10min |
| 2 | 阅读 `src/agents/write_studio/workflow/orchestrator.py`，理解 Researcher 如何接入工作流 | 20min |
| 3 | 阅读 `src/agents/write_studio/researcher.py` 和对应 Prompt，理解资料研究智能体 | 20min |
| 4 | 运行 `generate` 生成一篇技术博客或课程案例文章 | 20min |
| 5 | 运行 `evaluate` 生成评估报告，分析输出质量、角色表现和协作效果 | 20min |
| 6 | 对比启用和不启用 Researcher 的输出差异 | 20min |
| 7 | （进阶）选择一个问题，修改 Prompt、门禁或 Researcher 搜索策略并重新运行 | 30min |

## 常见问题

### Q1: 为什么没有生成 `researching_output.json`？

需要在生成命令中添加 `--enable-researcher`：

```bash
python src/main.py generate --topic "主题" --enable-researcher
```

### Q2: 如何评估已经生成的文章？

使用 `evaluate` 子命令，并指定工作流输出目录：

```bash
python src/main.py evaluate --workflow-dir output/<workflow_id>
```

### Q3: 如何判断哪个智能体表现不好？

先阅读 `evaluation_report.json` 中的阶段评分和问题列表，再打开对应的 `*_output.json`。例如 Writer 评分较低时，检查 `writing_output.json` 是否偏离 Planner 大纲，是否使用了 Researcher 的资料包。

### Q4: Researcher 资料不足怎么办？

可以从三个方向优化：

1. 修改 `prompts/agents/write_studio/researcher/` 下的 Prompt，要求更明确的资料筛选标准；
2. 修改 Planner Prompt，让它输出更适合检索的 `search_keywords`；
3. 修改 `src/agents/write_studio/researcher.py`，调整工具调用和资料整理策略。

### Q5: 如何做进阶优化？

建议选择一个明确问题闭环处理：

| 问题 | 定位文件 | 优化方向 |
|------|----------|----------|
| 大纲过粗 | `prompts/agents/write_studio/planner/` | 增加章节目标、案例线索、搜索关键词要求 |
| 资料不相关 | `prompts/agents/write_studio/researcher/` / `researcher.py` | 调整检索关键词和资料筛选标准 |
| Writer 未使用资料 | `prompts/agents/write_studio/writer/` | 要求整合 `key_findings` 和 `background_context` |
| 事实核查过严或过松 | `prompts/agents/write_studio/fact_checker/` / `workflow/gate.py` | 区分严重事实错误和轻微表达问题 |
| 审稿频繁退回 | `prompts/agents/write_studio/reviewer/` / `workflow/gate.py` | 明确通过、润色、重写、拒绝的判定标准 |
| 阶段衔接信息不足 | `workflow/orchestrator.py` | 调整 `_prepare_input()`，向后续 Agent 传递更多前序信息 |

## 总结

本实验通过完整运行写作工作室智能体系统，让学生完成从“文章生成”到“质量评估”再到“针对性优化”的闭环实践。

Researcher 的加入使系统具备资料研究能力，Evaluator 的加入使系统具备诊断能力。完成本实验后，应能够运行完整多智能体写作系统，分析各角色表现和协作效果，并能针对流程衔接或输出质量问题进行优化。