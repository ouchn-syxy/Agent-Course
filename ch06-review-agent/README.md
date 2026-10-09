# 实验 16：复习助手智能体 — 21 天自适应学习系统

> 对应章节 第六章 复习助手智能体 ｜ 4 学时 ｜ ✅ 已完成

## 概述

本实验构建一个完整的**复习助手智能体**，模拟"一对一老师"的教学过程：先诊断学生的知识水平，再制定个性化复习计划，每天出题、批改、反思、调整——在 **21 天**的复习周期中**持续观察、判断和优化**学习路径。

核心思路：

```
诊断当前水平 → 制定个性化计划 → 出题+批改 → 日终反思 → 条件重规划 → 循环递进
```

与前面章节的"单次问答"不同，本章的智能体需要**长期运行、持续适应**——这正是从"回答问题"到"持续服务"的升级。

## 功能清单

| 功能 | 命令 | 说明 |
|------|------|------|
| 初始化会话 | `python main.py --init` | 加载考试大纲 → 多轮诊断 → 生成 21 天计划 |
| 执行当日学习 | `python main.py` | 出题 → 作答 → 批改 → 反思 → 重规划（全自动） |
| 查看状态 | `python main.py --status` | 展示知识点掌握度柱状图、计划进度 |
| 列出会话 | `python main.py --list` | 查看所有历史学习会话 |
| 指定会话 | `python main.py --session ID` | 切换到指定会话继续学习 |
| 删除会话 | `python main.py --reset ID` | 删除指定会话 |

## 文件结构

```
ch06-review-agent/
├── config.yaml.example        # LLM + Tavily 搜索配置参照
├── requirements.txt           # 实验依赖
│
├── prompts/                   # Jinja2 提示词模板
│   └── agents/review/
│       ├── knowledge_assessor/   # 知识评估器 prompt
│       │   ├── system.j2         #   诊断系统角色
│       │   └── diagnose.j2       #   诊断对话模板
│       ├── plan_generator/       # 计划生成器 prompt
│       │   ├── system.j2         #   计划制定原则
│       │   └── generate.j2       #   逐天计划生成模板
│       ├── question_generator/   # 出题器 prompt
│       │   ├── system.j2         #   出题原则 + 工具声明
│       │   └── generate.j2       #   题目生成模板
│       ├── exam_grader/          # 批改器 prompt
│       │   ├── system.j2         #   评分原则 + 工具声明
│       │   └── grade.j2          #   批改模板
│       ├── daily_reviewer/       # 每日回顾器 prompt
│       │   ├── system.j2         #   反思维度定义
│       │   └── reflect.j2        #   当日数据模板
│       └── replanner/            # 重规划器 prompt
│           ├── system.j2         #   调整原则
│           └── replan.j2         #   当前状态 + 未来计划模板
│
├── data/                      # 数据文件
│   ├── data_structure_exam.json  # 数据结构考试大纲（6 个知识点）
│   └── sessions/                 # 运行时持久化的会话状态
│
└── src/                       # 核心代码
    ├── main.py                #   CLI 入口
    ├── config.py              #   Pydantic 配置加载
    │
    ├── agents/review/
    │   ├── review_agent.py        # ★ 主编排器（ReAct 循环 + 状态机）
    │   ├── knowledge_assessor.py  #   知识评估器（ReAct 多轮诊断对话）
    │   ├── plan_generator.py      #   计划生成器（程序排序 + LLM 逐天生成）
    │   ├── question_generator.py  #   出题器（支持 Tool Calling）
    │   ├── exam_grader.py         #   批改智能体（三维评分 + 事实核查）
    │   ├── mastery_calculator.py  #   掌握度计算器（纯程序，LLM 不参与）
    │   ├── daily_reviewer.py      #   每日回顾器（Reflection）
    │   ├── replanner.py           #   重规划器（局部修改未来计划）
    │   │
    │   ├── models/
    │   │   └── study_state.py     #   全部 Pydantic 数据模型
    │   ├── data/
    │   │   └── syllabus_loader.py #   大纲加载器
    │   └── tools/
    │       ├── lookup_knowledge_point.py    # Wikipedia 知识点查询
    │       ├── search_reference_questions.py # Tavily 参考题目搜索
    │       └── search_fact_check.py         # Tavily 事实核查
    │
    └── inherit/                # 受保护（前序章节继承，不可修改）
```

## 快速开始

### 1. 安装依赖

```bash
cd ch06-review-agent
pip install -r requirements.txt
```

依赖包：

| 包名 | 用途 |
|------|------|
| `openai` | LLM API 调用（兼容 DeepSeek / Qwen / 智谱 / OpenAI） |
| `pydantic` | 配置校验 + 全部数据模型定义 |
| `pyyaml` | 解析 config.yaml 配置文件 |
| `jinja2` | Prompt 模板渲染 |
| `jsonschema` | JSON Schema 校验 |

### 2. 配置 LLM

```bash
cp config.yaml.example config.yaml
# 编辑 config.yaml，填入 API Key 和 Tavily Search API Key
```

> ⚠️ `config.yaml` 已被 `.gitignore` 排除，不会提交到 Git。

### 3. 运行

```bash
# 初始化新学习会话（加载大纲 + 诊断 + 生成计划）
python main.py --init

# 执行当天学习任务
python main.py

# 查看当前掌握度
python main.py --status

# 列出所有会话
python main.py --list
```

## 技术架构

```
                          CLI (main.py)
                               │
                               ▼
                     ReviewAgent（主编排器）
                               │
          ┌────────────────────┼────────────────────┐
          │                    │                    │
          ▼                    ▼                    ▼
    【初始化阶段】          【每日 ReAct 循环】    【状态管理】
          │                    │                    │
    ┌─────┴─────┐         ┌───┴───┐            load_state()
    │           │         │       │            save_state()
    ▼           ▼         ▼       ▼            list_sessions()
KnowledgeAssessor  PlanGenerator  │            reset_session()
(ReAct 多轮诊断)  (逐天 LLM 生成)  │
                              ┌───┴───────────┐
                              │   逐任务循环    │
                              │               │
                              ▼               ▼
                      QuestionGenerator   ExamGrader
                      (支持 Tool Calling) (支持 Tool Calling)
                              │               │
                              ▼               ▼
                      Tavily 搜索         Tavily 事实核查
                      Wikipedia 查询
                              │               │
                              └───────┬───────┘
                                      ▼
                              mastery_calculator
                              (纯 Python 程序：
                               指数移动平均 +
                               遗忘因子衰减)
                                      │
                                      ▼
                              DailyReviewer
                              (日终 Reflection)
                                      │
                              ┌───────┴───────┐
                              │ needs_replan? │
                              └───────┬───────┘
                                  Y   │   N
                                  ▼   │   ▼
                            Replanner  │  继续下一天
                         (局部修改未来计划)│
```

### 核心模块说明

#### 1. 知识评估器（`knowledge_assessor.py`）

借鉴 ch03 的 ReAct 多轮对话收集模式。通过与学生的 5~8 轮对话，评估每个知识点的掌握度（mastery）和置信度（confidence）。

每轮执行：**Thought（LLM 分析）→ Action（提问或结束）→ Observation（学生回复）**。

所有知识点置信度达标（> 0.35）后自动结束诊断。

#### 2. 计划生成器（`plan_generator.py`）

借鉴 ch03 的 TaskDecomposer 模式，采用**程序排序 + LLM 逐天生成**的混合策略：

- **程序部分**：基于 `priority = importance × (1 - mastery) / max(confidence, 0.1)` 对知识点排序
- **LLM 部分**：逐天调用 `chat_with_json` 生成当日 `DailyPlan`，每次携带前几天摘要作为上下文

设计要点：不是一次性生成全部 21 天，而是 day-by-day，确保前后衔接、不遗漏知识点。

#### 3. 出题器（`question_generator.py`）

借鉴 ch05 的 AgentRunner JSON Schema 约束，并引入 ch04 的 **Tool Calling** 能力：

- 支持 `search_reference_questions`（Tavily 搜索真实考试题作为参考）
- 支持 `lookup_knowledge_point`（Wikipedia 查询知识点权威定义）
- 根据知识点掌握度自适应调整题目难度
- 输出包含题目、参考答案、三维评分标准

#### 4. 批改智能体（`exam_grader.py`）

借鉴 ch05 的 QualityGate 评分逻辑，从**正确性、完整性、清晰度**三个维度评分：

- 支持 `search_fact_check`（Tavily 事实核查学生答案中的关键陈述）
- 输出结构化 `GradingResult`，含维度得分、优点、不足、改进建议

#### 5. 掌握度计算器（`mastery_calculator.py`）★ 关键设计

**全部计算由纯 Python 程序完成，LLM 不参与数值计算。** 这是本章的核心设计决策：

- **证据融合**：`evidence_score = weighted_evidence(quiz_score, self_assessment, completion)`
- **指数移动平均**：`new_mastery = old_mastery + α × (evidence_score - old_mastery)`
- **遗忘因子**：连续 3 天未练习后，每日衰减 2%（`0.98^gap`）
- **置信度更新**：`new_confidence = old_confidence + β × (evidence_quality - old_confidence)`

> 教育理论中的掌握度计算来自教育者的经验，使用程序实现比 LLM 更高效、更可调试、更可靠。

#### 6. 每日回顾器（`daily_reviewer.py`）

借鉴 ch03 的 InfoInspector 模式。分析当日任务完成情况、测验表现、时间效率，判断是否触发重规划（`needs_replan`）。

#### 7. 重规划器（`replanner.py`）

借鉴 ch03 的 Replanning 和 ch05 的 Feedback 模式。**只修改未来未执行天数的计划**，已完成天数保持不变——最小改动原则。

#### 8. 主编排器（`review_agent.py`）

`ReviewAgent` 是顶层编排器，负责：

- `--init`：诊断 → 计划生成 → 持久化
- `daily`：逐任务 ReAct 循环（出题→批改→更新掌握度→反思→重规划）→ 持久化
- `--status`：展示当前状态
- `--list / --reset`：会话管理

#### 9. 数据模型（`models/study_state.py`）

全部数据结构通过 Pydantic 模型定义：

```
StudyState
├── list[KnowledgePoint]
│   └── list[MasteryRecord]
└── list[DailyPlan]
    ├── list[DailyTask]
    │   └── TaskResult
    │       └── GradingResult
    └── ReflectionResult
```

`KnowledgePoint.priority` 为 `@computed_field`，实时反映掌握度变化，无需手动维护。

## 关键设计决策

| 设计决策 | 理由 |
|----------|------|
| 掌握度计算用纯程序，禁止 LLM 参与 | 教育理论公式可调试、可调整、成本低 |
| 计划逐天生成而非一次性全量 | 每步携带前情摘要，确保前后衔接 |
| Replanning 只修改未来天数 | 最小改动原则，已完成的不动 |
| 出题/批改支持 Tool Calling | Tavily 搜索保证题目和评分有据可依 |
| 状态 JSON 序列化到文件 | 会话可恢复，支持多会话并存 |
| 遗忘因子 3 天后生效 | 模拟艾宾浩斯遗忘曲线 |

## 与其他章节的关系

本章是课程的收官章节，整合了前序全部能力：

| 章节 | 复用/借鉴的能力 | 在本章中的体现 |
|------|----------------|---------------|
| 第二章（角色智能体） | Prompt 工程、角色定义、JSON Schema | 6 个子 Agent 各有 system prompt 和输出 Schema |
| 第三章（行程规划） | ReAct 多轮对话、任务分解、Replanning | 诊断对话、计划逐天生成、条件重规划 |
| 第四章（服务智能体） | Tool Calling、Tavily 搜索 | 出题器搜索参考题、批改器事实核查 |
| 第五章（写作工作室） | 结构化输出、质量评估 | 三维评分、JSON Schema 约束、Jinja2 模板分离 |

## 实验流程

| 步骤 | 内容 | 预计时间 |
|------|------|----------|
| 1 | 阅读 `data/data_structure_exam.json`，理解考试大纲结构 | 10min |
| 2 | 阅读 `models/study_state.py`，理解全部 Pydantic 数据模型 | 20min |
| 3 | 运行 `--init`，体验诊断对话和计划生成全流程 | 30min |
| 4 | 阅读 `knowledge_assessor.py`，理解 ReAct 多轮诊断实现 | 20min |
| 5 | 阅读 `mastery_calculator.py`，理解掌握度计算公式和遗忘因子 | 20min |
| 6 | 阅读 `question_generator.py` + `exam_grader.py`，理解 Tool Calling 出题/批改 | 30min |
| 7 | 运行 `python main.py`，完成一天完整学习流程 | 30min |
| 8 | 阅读 `daily_reviewer.py` + `replanner.py`，理解反思和重规划机制 | 20min |
| 9 | （进阶）修改 `mastery_calculator.py` 中的学习率或遗忘因子，观察效果 | 40min |
| 10 | （进阶）为自己的学科编写考试大纲 JSON，运行完整流程 | 60min |
