# 实验 13：写作工作室角色分工设计

> 对应章节 5.1 写作工作室角色设计 ｜ 4 学时 ｜ ✅ 已完成

## 概述

本实验通过 **Pydantic Agent 类 + 类型化输入输出模型 + Jinja2 Prompt 模板**，构建一个写作工作室的 5 个基础角色：**Planner / Writer / FactChecker / Polisher / Reviewer**。

核心思路：

```
Agent 类（职责封装） → Pydantic 模型（输入输出约束） → Jinja2 模板（提示词渲染） → LLM 执行 → 类型化输出
```

每个角色都是一个独立的 Agent 类，继承自 `BaseRoleAgent`，通过 Pydantic 模型强制类型约束，确保上下游协作的数据契约稳定可靠。

## 功能清单

| 功能 | 命令 | 说明 |
|------|------|------|
| 列出角色 | `python src/main.py --list-roles` | 查看写作工作室中的所有角色 |
| 查看角色 | `python src/main.py --show-role planner` | 查看某个角色的职责、输入契约和输出契约 |
| 单角色测试 | `python src/main.py --run-role planner --topic "为什么 Rust 越来越受欢迎"` | 执行指定角色并校验输出格式 |
| 生成流程图 | `python src/main.py --workflow` | 生成写作团队协作关系 Mermaid 图 |
| 完整流水线 | `python src/main.py --pipeline --topic "主题"` | 一键运行 5 个角色的完整写作流程 |
| 类型校验 | 自动执行 | 通过 Pydantic 模型自动校验输入输出类型 |

## 文件结构

```
01-role-design/
├── config.yaml.example        # LLM 配置参照（复制为 config.yaml 后填入密钥）
├── requirements.txt           # 实验依赖（openai, pydantic, pyyaml, jinja2）
│
├── prompts/                   # Jinja2 提示词模板
│   └── agents/
│       └── write_studio/      # 5 个角色的 prompt 模板目录
│           ├── planner/       #   策划编辑 prompt
│           ├── writer/        #   内容作者 prompt
│           ├── fact_checker/  #   事实核查员 prompt
│           ├── polisher/      #   润色编辑 prompt
│           └── reviewer/      #   审稿主编 prompt
│
├── output/                    # 运行输出
│   ├── planner_input.json     #   用户输入（供 Reviewer 使用）
│   ├── planner_output.json    #   策划编辑输出
│   ├── writer_output.json     #   内容作者输出
│   ├── fact_checker_output.json  #  事实核查输出
│   ├── polisher_output.json   #   润色编辑输出
│   ├── reviewer_output.json   #   审稿主编输出
│   ├── workflow.md            #   协作流程图
│   └── pipeline/              #   完整流水线输出目录
│       └── final_article.md   #     最终文章
│
└── src/                       # 核心代码
    ├── main.py                #   CLI 入口（668 行）
    ├── config.py              #   配置加载（基于 Pydantic）
    │
    ├── agents/                #   Agent 实现
    │   └── write_studio/      #   写作工作室 5 个角色
    │       ├── base.py        #     BaseRoleAgent 基类 + RoleMeta
    │       ├── planner.py     #     PlannerAgent（策划编辑）
    │       ├── writer.py      #     WriterAgent（内容作者）
    │       ├── fact_checker.py#     FactCheckerAgent（事实核查员）
    │       ├── polisher.py    #     PolisherAgent（润色编辑）
    │       └── reviewer.py    #     ReviewerAgent（审稿主编）
    │
    └── inherit/               #   继承自前面章节的基础设施
        ├── llm/               #     LLM 客户端封装
        ├── prompt/            #     PromptManager（Jinja2 模板管理）
        ├── memory/            #     对话历史管理
        ├── tools/             #     工具调用
        ├── vlm/               #     视觉模型
        └── utils/             #     工具函数
```

## 快速开始

### 1. 安装依赖

```bash
cd ch05-writing-studio/01-role-design
pip install -r requirements.txt
```

依赖包：

| 包名 | 用途 |
|------|------|
| `openai` | LLM API 调用（兼容 DeepSeek / Qwen / 智谱 / OpenAI） |
| `pydantic` | 数据模型定义与类型校验（Agent 输入输出） |
| `pyyaml` | 解析配置文件 config.yaml |
| `jinja2` | Prompt 模板渲染 |
| `jsonschema` | （保留依赖，实际使用 Pydantic 校验） |

### 2. 配置 LLM

```bash
cp config.yaml.example config.yaml
# 编辑 config.yaml，将 api_key_env 替换为你的 API Key 环境变量名
# 如需切换模型，修改 provider、base_url、model 字段即可
```

> ⚠️ `config.yaml` 已被 `.gitignore` 排除，不会提交到 Git。

### 3. 运行

```bash
# 查看所有角色
python src/main.py --list-roles

# 查看 planner 角色定义
python src/main.py --show-role planner

# 生成协作流程图
python src/main.py --workflow

# 测试单个角色
python src/main.py --run-role planner --topic "为什么 Rust 越来越受欢迎"

# 一键运行完整流水线
python src/main.py --pipeline --topic "为什么 Rust 越来越受欢迎" --audience "后端开发者" --goal "解释 Rust 的核心优势"
```

## 输出效果

运行单角色测试后，会在 `output/` 下生成结构化 JSON 输出，例如 Planner 的输出（PlannerOutput 模型）：

```json
{
  "audience_analysis": {
    "profile": "读者画像",
    "needs": ["需求1", "需求2"],
    "pain_points": ["痛点1", "痛点2"]
  },
  "core_message": {
    "angle": "独特角度",
    "thesis": "核心论点",
    "takeaways": ["收获1", "收获2"]
  },
  "outline": [
    {
      "title": "章节标题",
      "objective": "写作目标",
      "key_points": ["要点1", "要点2"],
      "notes": "给作者的说明（可选）"
    }
  ],
  "writing_guidelines": {
    "dos": ["应该做的事"],
    "donts": ["应该避免的事"],
    "examples": ["建议示例方向"]
  }
}
```

运行完整流水线后，会在 `output/pipeline/` 下生成：
- 所有中间角色的 JSON 输出
- `final_article.md` — 最终文章（包含润色后的内容 + 审稿意见）

## 技术架构

```
BaseRoleAgent[TInput, TOutput]
     │
     ├─ meta() → RoleMeta（角色元信息）
     ├─ input_model() → type[TInput]（输入模型类）
     ├─ output_model() → type[TOutput]（输出模型类）
     └─ run(task: TInput) → TOutput
            │
            ├─ 1. PromptManager.render() → System Prompt + User Prompt
            ├─ 2. LLMClient.call() → JSON 字符串
            └─ 3. Pydantic.model_validate() → 类型化输出

角色依赖链（自动加载前序输出）：
  planner → writer → fact_checker → polisher → reviewer
     ↓         ↓            ↓             ↓          ↓
  planner  planner+     planner+      planner+   planner+
  _output  writer       writer        writer     polisher
   .json   _output      _output       _output    _output
           .json        .json         .json      .json
```

### 核心模块说明

#### 1. BaseRoleAgent（`src/agents/write_studio/base.py`）

所有角色的抽象基类，定义统一接口：

- `meta()` - 返回角色元信息（RoleMeta：role_id, role_name, role_description, quality_focus）
- `input_model()` - 返回输入 Pydantic 模型类
- `output_model()` - 返回输出 Pydantic 模型类
- `run(task: TInput) -> TOutput` - 执行角色任务，返回类型化输出

异常体系：
- `PromptRenderError` - Jinja2 模板渲染失败
- `LLMCallError` - LLM 调用失败
- `OutputParseError` - JSON 解析失败
- `OutputValidationError` - Pydantic 校验失败

#### 2. 角色实现（`src/agents/write_studio/*.py`）

每个角色文件包含：
- **输入模型** - 定义角色需要的输入字段（Pydantic BaseModel）
- **输出模型** - 定义角色的输出结构（嵌套 Pydantic 模型）
- **Agent 类** - 继承 BaseRoleAgent，实现 meta() 等方法

示例（PlannerAgent）：
- 输入：PlannerInput（topic, audience, goal, word_count, tone, requirements, constraints）
- 输出：PlannerOutput（audience_analysis, core_message, outline, writing_guidelines）
- 质量关注：读者需求准确性、大纲逻辑性、写作指导可操作性

#### 3. Prompt 模板（`prompts/agents/write_studio/`）

每个角色目录下包含 Jinja2 模板文件，通过 PromptManager 渲染。
模板变量从 Pydantic 模型实例中提取（通过 `.model_dump()`）。

#### 4. CLI 入口（`src/main.py`）

主要功能：
- `cmd_list_roles()` - 列出所有角色
- `cmd_show_role()` - 查看角色详情
- `cmd_workflow()` - 生成 Mermaid 流程图
- `cmd_pipeline()` - 一键运行完整流水线
- `run_xxx()` 系列 - 单角色运行方法（自动处理依赖链）

依赖链加载逻辑：
- planner：无依赖，仅需 CLI 参数
- writer：读取 planner_input.json + planner_output.json
- fact_checker：读取 planner_input.json + planner_output.json + writer_output.json
- polisher：读取 planner_input.json + planner_output.json + writer_output.json
- reviewer：读取 planner_input.json + polisher_output.json

## 添加新角色

1. 在 `src/agents/write_studio/` 下创建 `<角色名>.py`
2. 定义输入模型类（继承 BaseModel）和输出模型类
3. 定义 Agent 类，继承 `BaseRoleAgent[输入类型, 输出类型]`
4. 实现 `meta()` / `input_model()` / `output_model()` 类方法
5. 在 `prompts/agents/write_studio/` 下创建对应 prompt 模板目录
6. 在 `src/main.py` 中注册新角色（添加到 agents 列表和命令分发逻辑）
7. 运行 `python src/main.py --list-roles` 确认角色已被识别
8. 运行 `python src/main.py --run-role <角色名> --topic "测试主题"` 验证输出

示例参考：`src/agents/write_studio/planner.py`

## 与后续实验的关系

本实验是第五章写作工作室的基础模块。后续实验将在此基础上：

| 实验 | 新增能力 | 改动点 |
|------|---------|--------|
| 实验 14（协作） | 状态机 + 上下文管理 + 质量门禁 | 将 5 个角色串成完整写作流程 |
| 实验 15（集成） | WritingStudio 统一入口 + 批量运行 + Researcher | 封装应用层，并加入资料调研增强流程 |

## 实验流程

| 步骤 | 内容 | 预计时间 |
|------|------|----------|
| 1 | 阅读 `src/agents/write_studio/base.py`，理解 BaseRoleAgent 接口设计 | 20min |
| 2 | 阅读 `src/agents/write_studio/planner.py`，理解 Pydantic 模型定义 | 20min |
| 3 | 运行 `--list-roles` 和 `--show-role` 查看角色元信息 | 20min |
| 4 | 运行 `--workflow` 生成协作流程图 | 20min |
| 5 | 运行 `--run-role planner` 测试单角色输出 | 30min |
| 6 | 运行 `--pipeline` 体验完整流水线（5 个角色自动串联） | 30min |
| 7 | 修改某个角色的 Prompt 模板或输出模型结构，观察输出变化 | 60min |
| 8 | （进阶）新增一个 SEO 编辑或配图设计师角色，实现完整 Agent 类 | 90min |
