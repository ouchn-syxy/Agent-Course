# 实验 7：行程任务分解与工具编排

> 对应章节 3.2 运筹帷幄：任务分解与工具编排 ｜ 3 学时 ｜ ✅ 已完成

## 概述

本实验在实验 6（ReAct 需求理解）的基础上，将用户需求传递给**规划-执行-审查-生成**四阶段流水线，自动完成航班查询、酒店搜索、景点发现、天气预报、美食推荐等多工具协同调用，最终生成结构化的 Markdown 方案报告。

核心思路：

```
用户需求 → TaskDecomposer 分解子任务 → PlanningAgent 批量执行工具调用
                                              ↑              ↓
                                         InfoInspector 审查信息缺口
                                              │              ↓
                                              └── 补充调用 ←──┘
                                              ↓
                                    PlanReporter 生成方案
```

不再像实验 6 那样让 LLM 在思考-行动-观察间来回跳跃，而是将**规划与执行分离**：先一次性分解全部子任务，再批量执行，再审查补充，最后汇总生成。审查环节发现的缺口生成补充工具调用后**由 PlanningAgent 直接执行**（不重新调用 TaskDecomposer），然后用新收集到的信息再次审查，直到充分或达到轮次上限。

## 功能清单

| 功能 | 说明 |
|------|------|
| 交互式行程规划 | 单行输入需求，回车即执行，支持多轮复用 |
| 任务分解（Phase 1） | LLM 将出行需求分解为带依赖关系的子任务列表 |
| 工具执行（Phase 2） | 批量执行所有子任务的工具调用（航班/酒店/景点/天气/搜索） |
| 审查补充（Phase 3） | InfoInspector 逐项审核信息充分性，自动生成补充工具调用 |
| 方案生成（Phase 4） | PlanReporter 汇总全部信息，输出 Markdown 行程方案 |
| `--max-inspect N` | 限制审查循环轮次（默认 5） |
| `-o output/xxx.md` | 指定输出文件路径 |
| 自动输出文件 | 不指定 `-o` 时自动生成 `trip_plan_时间戳.md` |

## 文件结构

```
02-task-planning/
├── config.yaml               # LLM 配置（API Key、模型、生成参数）
├── config.yaml.example       # LLM 配置参照（复制为 config.yaml 后填入密钥）
├── requirements.txt          # 实验依赖
│
├── data/                     # 数据文件（当前为空，预留扩展目录）
│
├── prompts/                  # Jinja2 提示词模板
│   ├── agents/               #   Agent 提示词
│   │   ├── planning/         #     ★ PlanningAgent 及其组件的 prompt
│   │   │   ├── task_decomposer/  #   system.j2 + decompose.j2
│   │   │   ├── info_inspector/   #   system.j2 + inspect.j2
│   │   │   └── plan_reporter/    #   system.j2 + report.j2
│   │   └── trip_planning/    #     行程领域 prompt
│   │       └── requirement_collector/  # 需求收集（提取 + ReAct）
│   └── memory/               #   记忆相关 prompt
│       └── conversation/     #     对话摘要/压缩模板
│
├── src/                      # 核心代码
│   ├── main.py               #   CLI 入口（输入需求 → 编排执行 → 输出方案）
│   ├── config.py             #   Pydantic v2 配置模型
│   ├── agents/               #   ★ Agent 领域模块
│   │   ├── planning/         #     ★ 自主规划智能体（通用编排）
│   │   │   ├── planning_agent.py    #   ★ PlanningAgent：驱动 Decompose→Execute→Inspect→Report
│   │   │   ├── task_decomposer.py   #   任务分解器：需求 → SubTask 列表
│   │   │   ├── info_inspector.py    #   审查器：审核信息充分性 → 补充工具调用
│   │   │   ├── plan_reporter.py     #   方案报告器：汇总信息 → Markdown 方案
│   │   │   └── models/             #   Pydantic 数据模型
│   │   │       └── types.py         #     SubTask / DecompositionResult / InspectionResult / TaskExecutionRecord
│   │   └── trip_planning/   #     行程领域
│   │       ├── trip_planning_agent.py   #  ★ TripPlanningAgent：封装构建逻辑，对外提供简洁入口
│   │       ├── domain_context.py    #   ★ 领域上下文（3 个 domain context 字符串）
│   │       ├── models/             #   Pydantic 领域模型
│   │       │   └── types.py         #     TripRequirement
│   │       └── tools/              #   ★ Mock 工具实现
│   │           ├── flight_search.py     #   航班查询（多城市/多日期/参数化价格）
│   │           ├── hotel_search.py      #   酒店搜索（按预算/偏好/评分筛选）
│   │           ├── attraction_search.py #   景点发现（按城市/分类返回）
│   │           └── weather_query.py     #   天气预报（按城市/日期范围）
│   └── inherit/              #   代码继承（来自 ch02 + ch03/01）
│       ├── llm/              #     LLM 客户端 / ToolRegistry / ChatSession
│       ├── prompt/           #     PromptManager（Jinja2）
│       ├── tools/            #     TavilySearchTool（真实网络搜索）
│       ├── utils/            #     项目路径工具
│       ├── memory/           #     记忆管理（继承自 ch02）
│       ├── agents/           #     Agent 基类（继承自 ch02）
│       └── tts/              #     语音合成（继承自 ch02，本实验未使用）
│
└── output/                   # 行程方案输出
    └── trip_plan_*.md        #   自动生成的时间戳文件名
```

## 快速开始

### 1. 安装依赖

```bash
cd ch03-trip-agent/02-task-planning
pip install -r requirements.txt
```

依赖包：

| 包名 | 用途 |
|------|------|
| `openai` | LLM API 调用（兼容 DeepSeek 等） |
| `PyYAML` | 解析配置文件 |
| `pydantic` | 数据模型校验（v2，`model_validate_json`） |
| `jinja2` | 提示词模板渲染 |

### 2. 配置 LLM

```bash
cp config.yaml.example config.yaml
```

编辑 `config.yaml`，填入 API Key：

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
  api_key: "your-tavily-api-key-here"
  max_results: 5
  include_answer: false
```

### 3. 运行

```bash
# 交互式出行规划
python main.py

# 限制审查最多 1 轮
python main.py --max-inspect 1

# 指定输出文件
python main.py -o output/chengdu_trip.md
```

## 架构设计

`main.py` 创建 `TripPlanningAgent`，后者内部构建 `ToolRegistry`（注册 5 个工具）、`TaskDecomposer`、`InfoInspector`、`PlanReporter` 和 `PlanningAgent`，然后将用户需求传给 `PlanningAgent.run()` 驱动四阶段流水线。

```
                    ┌─────────────────────────────────┐
                    │          main.py                 │
                    │  plan_loop() ← 单行输入循环      │
                    │         ↓                        │
                    │  TripPlanningAgent.run()          │
                    └──────────┬──────────────────────┘
                               │
                    ┌──────────┴──────────────────┐
                    │       PlanningAgent          │
                    │   Decompose→Execute→Inspect  │
                    │   →Report 四阶段流水线        │
                    └──────────┬──────────────────┘
                               │
          ┌────────────────────┼────────────────────┐
          ▼                    ▼                    ▼
  ┌──────────────┐    ┌──────────────┐    ┌──────────────┐
  │TaskDecomposer│    │ InfoInspector│    │ PlanReporter │
  │  需求→子任务  │    │ 审核→补充     │    │ 汇总→Markdown │
  └──────┬───────┘    └──────┬───────┘    └──────────────┘
         │                   │
         └─────────┬─────────┘
                   ▼
          ┌─────────────────┐
          │  ToolRegistry   │
          │  flight / hotel │
          │  attraction     │
          │  weather / web  │
          └─────────────────┘
```

> **注**：TaskDecomposer（Phase 1）和 InfoInspector（Phase 3）均通过 `registry.list()` 获取工具表来渲染 prompt。PlanReporter 不依赖 ToolRegistry——它只做"汇总+生成"，不调用任何工具。

## 与实验 6 的关系

| 维度 | 实验 6（ReAct 需求理解） | 实验 7（任务分解与工具编排） |
|------|--------------------------|------------------------------|
| 模式 | 思考-行动-观察循环 | 规划-执行-审查-生成流水线 |
| 输出 | 结构化需求 `TripRequirement` | 完整 Markdown 行程方案 |
| 工具调用 | LLM 在循环中自主决定 | 规划器预先分解 + 批量执行 |
| 信息收集 | 一轮结束即完成 | 审查器审核后可能补充多轮 |
| 代码继承 | — | `inherit/` 从实验 6 复用 LLM/ToolRegistry/PromptManager |
