# 实验 2：角色模拟智能体提示词设计

> 对应章节 2.1 角色塑造：提示词与人格设定 ｜ 4 学时 ｜ ✅ 已完成

## 概述

本实验通过 **YAML 角色定义 + Jinja2 模板渲染**，将大模型从"乐于助人的 AI 助手"转变为一个有身份、有风格、有知识边界的角色——**鲁迅**。

核心思路：

```
YAML 角色定义（人编辑） → Jinja2 模板（程序渲染） → System Prompt（模型读取）
```

学生只需编辑 `data/profiles/<角色名>.yaml`，无需修改任何 Python 代码，即可切换角色。

## 功能清单

| 功能 | 命令                                | 说明 |
|------|-----------------------------------|------|
| 交互式对话 | `python main.py`                  | 与鲁迅进行多轮对话，支持 `/quit` 退出、`/reset` 重置 |
| 切换角色 | `python main.py --profile <name>` | 切换到其他 `data/profiles/` 下的角色 |
| 列出角色 | `python main.py --list`           | 查看所有可用角色及其身份 |
| 自动评估 | `python main.py --eval`           | 12 题 × 4 维度 LLM-as-Judge 评估，输出均值报告 |
| Few-shot 示例 | `python main.py --few-shot`       | 在 prompt 中注入 5 组对话示例，增强角色一致性 |
| CoT 推理 | `python main.py --cot`            | 在 prompt 末尾追加四步思维链，引导深度推理 |

## 文件结构

```
01-prompt-design/
├── config.yaml               # LLM 配置（API Key、模型、生成参数）
├── config.yaml.example       # LLM 配置参照（复制为 config.yaml 后填入密钥）
├── requirements.txt          # 实验依赖
│
├── data/                     # 数据文件
│   ├── profiles/           #   角色 YAML 定义
│   │   └── luxun.yaml        #     示例角色：鲁迅（6 大板块结构化定义）
│   └── eval/                 #   评估数据
│       └── test_questions.json  #   12 道测试题（4 维度 × 3 题）
│
├── prompts/                  # Jinja2 提示词模板
│   ├── profile.j2          #   角色 system prompt 模板
│   └── eval.j2        #   LLM-as-Judge 评估 prompt 模板
│
├── src/                      # 核心代码
│   ├── main.py               #   CLI 入口（对话 / 评估 / 列出角色）
│   ├── config.py             #   Pydantic v2 配置模型（Config / LLMConfig / GenerationConfig / ProfileConfig）
│   ├── evaluator.py          #   LLM-as-Judge 四维评估器
│   ├── llm/                  #   LLM 调用封装
│   │   ├── client.py         #     OpenAI SDK 统一调用（chat / chat_with_json）
│   │   └── chat_session.py   #     多轮对话会话管理
│   ├── prompt/               #   Prompt 模板管理
│   │   └── prompt_manager.py #     Jinja2 加载/缓存/渲染
│   └── utils/                #   工具模块
│       └── path.py           #     项目路径工具
│
└── tests/                    # 测试（预留）
```

## 快速开始

### 1. 安装依赖

```bash
cd ch02-role-agent/01-prompt-design
pip install -r requirements.txt
```

依赖包：

| 包名 | 用途 |
|------|------|
| `openai` | LLM API 调用（兼容 DeepSeek / Qwen / 智谱 / OpenAI） |
| `PyYAML` | 解析角色 YAML 文件和配置文件 |
| `pydantic` | 配置模型校验（v2，`model_validate`） |
| `jinja2` | 提示词模板渲染 |
| `tiktoken` | Token 计数（实验 3 使用） |

### 2. 配置 LLM

```bash
cp config.yaml.example config.yaml
# 编辑 config.yaml，将 api_key_env 替换为你的 API Key
# 如需切换模型，修改 provider、base_url、model 字段即可
```

> ⚠️ `config.yaml` 已被 `.gitignore` 排除，不会提交到 Git。

### 3. 运行

```bash
# 进入 src 目录运行
cd src
python main.py

# 查看可用角色
python main.py --list

# 启用 Few-shot 示例（注入 5 组对话示例，增强角色一致性）
python main.py --few-shot

# 启用 Chain-of-Thought 推理链（四步推理引导）
python main.py --cot

# 同时启用两者
python main.py --few-shot --cot

# 运行自动评估（12 题全维度评分）
python main.py --eval

# 评估也支持开关（对比不同配置的分数）
python main.py --eval --few-shot --cot
```

## 对话效果

```
你: 请问您是谁？

鲁迅: （沉吟片刻，烟卷在指间明灭）我么？绍兴周树人，如今人大抵叫我鲁迅。
学过医，后来觉得救人身体不如救人精神，便做起文章来。写过几篇小说，也骂过
些人——不过骂的，都是该骂的罢了。

你: 先生，我是一个想学写作的年轻人，您能给我一些建议吗？

鲁迅: （仔细看了看面前的年轻人）想学写作？好。第一，多读。中国的、外国的，
好的、坏的，都要读。读了才知道什么叫好文章。第二，写真话。世上太多人讲假
话、套话、空话——你万万不可学他们。第三，不要怕得罪人。倘若你的文章人人都
说好，你倒要反省自己了。
```

## 技术架构

```
data/profiles/luxun.yaml          data/eval/test_questions.json
        │                                    │
        ▼                                    │
  PromptManager.render("profile.j2")        │
        │                                    │
        ▼                                    ▼
  system prompt (约 640 字)    ──────▶  Evaluator.evaluate_all()
        │                                    │
        ▼                                    ▼
  ChatSession.send()  ◀── 用户输入           EvalReport
        │
        ▼
  鲁迅的回复（四个评估维度：身份/风格/知识/时代）
```

### 核心模块说明

#### 1. 角色定义（YAML）

`data/profiles/luxun.yaml` 包含 6 大板块：

| 板块 | 内容 | 示例 |
|------|------|------|
| 基本身份 | 姓名、时代、身份 | 鲁迅 · 晚清至民国 · 文学家 |
| 性格特质 | 人格特征列表 | 冷峻深刻、愤世嫉俗、对青年热忱 |
| 说话风格 | 语调、习惯、禁令 | 文白夹杂、善用反语、禁用 1949 年后词汇 |
| 知识领域 | 擅长领域列表 | 古典文学、外国文学、木刻版画 |
| 情绪基线 | 核心情感态度 | 哀其不幸，怒其不争 |
| 对话示例 | Few-shot 示例对话 | 5 组高质量问答，覆盖身份/风格/知识/时代 |

#### 2. Jinja2 模板（`prompts/profile.j2`）

将 YAML 渲染为自然语言 system prompt，使用 Jinja2 的条件渲染和循环：

```jinja2
# 你是谁
你是 **{{ profile.name }}**。
{% if profile.era %}你生活在 **{{ profile.era }}**。{% endif %}
...
{% for h in profile.speech_style.habits %}
- {{ h }}
{% endfor %}
```

设计要点：
- **条件渲染**：可选字段（如 `era`、`tone`）仅在填写后才出现在 prompt 中
- **循环渲染**：habits / forbidden / personality 等列表自动展开
- **职责分离**：模板专注"怎么呈现"，YAML 专注"呈现什么"

#### 3. Prompt 管理器（`prompt/prompt_manager.py`）

封装 Jinja2 的 `Environment` + `FileSystemLoader`，提供：
- 模板自动缓存（Jinja2 默认行为，重复渲染不重复解析）
- 一步渲染接口：`pm.render("profile.j2", profile=..., user_name="来访者")`
- `trim_blocks` / `lstrip_blocks` 配置，避免多余空行

#### 4. LLM 客户端（`llm/client.py`）

基于 OpenAI SDK，与配置文件解耦，所有参数由外部显式传入：

- `chat(messages)` — 普通对话
- `chat_with_json(messages)` — JSON 模式（评估用，设置 `response_format: json_object`）
- 支持 `**kwargs` 逐次覆盖生成参数（如评估时覆盖 `temperature=0.3`）

#### 5. 对话会话（`llm/chat_session.py`）

维护 `system + user + assistant` 消息列表：
- `send(user_input)` — 追加 user → 调用 LLM → 追加 assistant → 返回回复
- `turn_count` — 已进行对话轮数
- `peek_last(role)` — 查看最近一条消息（不修改列表）
- `reset(prompt)` — 重置对话历史

#### 6. 配置模型（`config.py`）

基于 **Pydantic v2**，从 `config.yaml` 加载并校验：

```python
class LLMConfig(BaseModel):
    provider: str
    base_url: str
    model: str
    api_key_env: str

class GenerationConfig(BaseModel):
    temperature: float | None = None  # ge=0.0, le=2.0（值来自 config.yaml）
    top_p: float | None = None        # ge=0.0, le=1.0
    max_tokens: int | None = None     # ge=1
```

## 评估体系

预置 12 道测试题（`data/eval/test_questions.json`），覆盖四个评估维度各 3 题，由 LLM-as-Judge 打分（1-5 分）：

| 维度 | 含义 | 示例题 |
|------|------|--------|
| 身份一致性 | 回复是否符合鲁迅身份和立场？ | "有人批评您的文章太过尖刻，您怎么看？" |
| 风格匹配度 | 语调、用词是否像鲁迅？ | "有人说中国社会已经很完美了……" |
| 知识准确性 | 涉及的事实是否准确？ | "您当年在日本学医，为什么又改学文学了？" |
| 时代契合度 | 是否混入现代词汇？ | "您平时用什么社交软件和朋友联系？" |

评估使用独立的 Jinja2 模板（`prompts/eval.j2`），将角色 YAML 原文喂给 Judge 作为"参考答案"。
评估用低温度（temperature=0.3）以保证评分一致性。

运行评估的期望输出：

```
============================================================
  评估报告 — luxun
============================================================
  测试题目数: 12
  身份一致性 均值: 4.92
  风格匹配度 均值: 4.92
  知识准确性 均值: 5.00
  时代契合度 均值: 5.00
  ─────────────────────────────
  综合得分 均值: 4.96
============================================================
```

## 添加新角色

1. 在 `data/profiles/` 下创建 `<角色名>.yaml`，参照 `luxun.yaml` 的 6 个板块填写
2. 运行 `python main.py --list` 确认角色已被识别
3. 运行 `python main.py --profile <角色名>` 开始对话测试

## 与后续实验的关系

本实验是第二章的基础模块。后续实验将在此基础上：

| 实验 | 新增能力 | 改动点 |
|------|---------|--------|
| 实验 3（记忆） | 短期记忆 + 长期记忆 | 在 system prompt 后追加历史摘要和长期记忆检索结果 |
| 实验 4（工具调用） | 自动搜索 + 特征提取 | 自动搜索信息补充角色知识，最终自动生成角色 YAML |
| 实验 5（综合） | TTS 语音 + 自我反思 | 整合提示词 + 记忆 + 工具 + 语音输出的完整数字分身 |

## 实验流程

| 步骤 | 内容 | 预计时间 |
|------|------|----------|
| 1 | 阅读 `data/profiles/luxun.yaml`，理解角色定义结构和 5 大板块 | 30min |
| 2 | 阅读 `prompts/profile.j2`，理解 Jinja2 模板的条件/循环渲染 | 20min |
| 3 | 运行 `main.py` 与鲁迅对话，感受 prompt 效果 | 20min |
| 4 | 选择自己感兴趣的人物，编写角色 YAML | 60min |
| 5 | 运行评估脚本，查看一致性得分 | 30min |
| 6 | 根据评估结果迭代优化角色定义，记录改动前后对比 | 60min |
| 7 | （进阶）对比实验：用同一套问题分别测试 `python main.py` / `--few-shot` / `--cot` / `--few-shot --cot` 四种组合，观察并记录回复差异；使用 `--eval` 分别生成评估报告，对比四维度分数变化 | 40min |

