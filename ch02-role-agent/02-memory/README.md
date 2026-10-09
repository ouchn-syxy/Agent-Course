# 实验 3：短期记忆 — 让角色记住来访者

> 对应章节 2.2 记忆：让角色记住来访者 ｜ 4 学时 ｜ ✅ 已完成

## 概述

实验 2 中的鲁迅能说话、有风格，但有一个致命缺陷——**关掉程序重新打开，它就完全不记得你是谁了**。聊了 20 轮后，上下文窗口溢出也会让它忘记之前说过的话。

本实验为鲁迅装上短期记忆系统：**文件持久化 + 滑动窗口 + LLM 摘要压缩**。核心问题——重启后记忆消失——通过 JSON 文件自动落盘与恢复来解决。

核心思路：

```
用户消息 → MemoryChatSession.send()
              ├─ 1. 注入记忆上下文（摘要 + 窗口内历史）
              ├─ 2. 调用 LLM 生成回复
              └─ 3. 记录本轮对话 → 自动落盘 JSON → 必要时触发 LLM 摘要压缩
```

与实验 2 的关系：**通过 `inherit/` 模块继承复用**实验 2 的全部核心能力（LLMClient、ChatSession、PromptManager、路径工具），在此基础上新增记忆层，零重复代码。

## 功能清单

| 功能 | 命令                                    | 说明 |
|------|---------------------------------------|------|
| 记忆感知对话 | `python main.py`                      | 透明注入记忆，支持 `/quit` `/reset` `/memory` |
| 记忆面板 | `python main.py --memory-panel`       | 每轮后自动显示记忆状态 |
| 切换角色 | `python main.py --profile <name>`     | 与实验 2 一致 |
| 列出角色 | `python main.py --list`               | 与实验 2 一致 |
| Few-shot 示例 | `python main.py --few-shot`           | 注入 5 组对话示例，增强角色一致性 |
| CoT 推理链 | `python main.py --cot`                | 追加四步思维链，引导深度推理 |
| 记忆评估 | `python main.py --eval`               | 6 题 × 3 维度 LLM-as-Judge 评估 |
| Token 演示 | `python main.py --tiktoken-demo`      | tiktoken 精确计数 vs DeepSeek 字符估算 |

## 文件结构

```
02-memory/
├── config.yaml               # LLM + 记忆参数配置（含 MemoryConfig）
├── config.yaml.example       # 配置参照
├── requirements.txt          # 实验依赖（新增 tiktoken）
│
├── data/                     # 数据文件
│   ├── profiles/           #   角色 YAML 定义（复用实验 2 格式，含 6 大板块 + few_shot_examples）
│   │   └── luxun.yaml
│   ├── eval/                 #   评估数据
│   │   └── test_questions.json  #   6 道记忆测试题（3 维度 × 2 题）
│   └── memories/             #   记忆持久化目录
│       └── .gitkeep
│
├── prompts/                  # Jinja2 提示词模板（新增压缩 & 摘要模板）
│   ├── profile.j2          #   角色 system prompt（复用实验 2，含 Few-shot / CoT 条件渲染）
│   ├── eval.j2               #   记忆评估 Judge prompt 模板
│   └── memory/
│       └── conversation/
│           ├── compression.j2  #   LLM 压缩指令模板
│           └── summary.j2      #   摘要注入 system prompt 模板
│
├── src/                      # 核心代码
│   ├── main.py               #   CLI 入口（对话 / 评估 / Token 演示 / 列出角色）
│   ├── config.py             #   Pydantic v2 配置（新增 MemoryConfig）
│   ├── evaluator.py          #   LLM-as-Judge 记忆评估器（3 维度）
│   ├── inherit/              #   ★ 代码继承层（复用实验 2 模块，零拷贝）
│   │   ├── llm/client.py         # → 实验 2 的 LLMClient
│   │   ├── llm/chat_session.py   # → 实验 2 的 ChatSession
│   │   ├── prompt/prompt_manager.py  # → 实验 2 的 PromptManager
│   │   └── utils/path.py         # → 实验 2 的路径工具
│   ├── llm/                  #   LLM 层（新增模块）
│   │   ├── memory_chat_session.py # ★ 记忆感知对话引擎（继承 ChatSession）
│   │   └── token_counter.py       # tiktoken 精确计数 + DeepSeek 字符估算
│   └── memory/               #   记忆层（全新模块）
│       └── conversation_memory.py      # ★ 记忆管理器：窗口 + 压缩 + 持久化
│
└── tests/                    # 测试（预留）
```

## 代码继承设计

本实验不重复编写实验 2 的代码，而是将需要复用的核心模块拷贝到 `inherit/` 目录下，新代码直接从 `inherit/` 导入。

```
01-prompt-design/src/                    02-memory/src/
  llm/client.py         ←─ inherit ──      inherit/llm/client.py
  llm/chat_session.py   ←─ inherit ──      inherit/llm/chat_session.py
  prompt/prompt_manager.py ←─ inherit ──   inherit/prompt/prompt_manager.py
  utils/path.py         ←─ inherit ──      inherit/utils/path.py

新模块（本实验特有）：
  memory/conversation_memory.py        ← 全新：滑动窗口 + 压缩 + JSON 持久化
  llm/memory_chat_session.py      ← 全新：继承 ChatSession，覆写 send()
  llm/token_counter.py            ← 全新：tiktoken + DeepSeek 估算
  evaluator.py                    ← 全新：3 维度记忆评估器
  config.py                       ← 扩展：新增 MemoryConfig
```

继承体系：

```
ChatSession (实验 2)
    ↑ 继承
MemoryChatSession (本实验)
    └─ send() 覆写：注入记忆 → 调用 LLM → 更新记忆
    └─ reset() 覆写：同时清空记忆管理器
```

## 快速开始

### 1. 安装依赖

```bash
cd ch02-role-agent/02-memory
pip install -r requirements.txt
```

依赖包：

| 包名 | 用途 |
|------|------|
| `openai` | LLM API 调用（兼容 DeepSeek 等） |
| `PyYAML` | 解析角色 YAML 文件和配置文件 |
| `pydantic` | 配置模型校验（v2，`model_validate`） |
| `jinja2` | 提示词模板渲染 |
| `tiktoken` | Token 精确计数 |

### 2. 配置 LLM

```bash
cp config.yaml.example config.yaml
# 编辑 config.yaml，填入 api_key_env
# 可调整 memory.max_turns（窗口轮数）和 memory.max_tokens（压缩阈值）
```

> ⚠️ `config.yaml` 已被 `.gitignore` 排除，不会提交到 Git。

### 3. 运行

```bash
# 进入 src 目录运行
cd src
python main.py

# 带记忆面板的对话
python main.py --memory-panel

# 启用 Few-shot 示例（注入 5 组对话示例）
python main.py --few-shot

# 启用 Chain-of-Thought 推理链
python main.py --cot

# 同时启用两者
python main.py --few-shot --cot

# 查看可用角色
python main.py --list

# Token 计数演示
python main.py --tiktoken-demo

# 运行记忆评估
python main.py --eval
```

## 对话效果

```
你: 我叫王芳，喜欢龙井茶。

鲁迅: （微微颔首）王芳……这名字倒清雅。龙井茶么？我也颇好此道。
杭州的龙井，须是明前的最好，泡出来碧绿透亮，入口清甘。

你: 我还养了一只金毛，叫大黄。

鲁迅: （眼里闪过一丝温和）金毛犬么？大黄这名字也好——朴实。比那些
取名"来福""旺财"的，倒是多了几分郑重。

你: 你记得我的宠物叫什么吗？

鲁迅: （缓缓吐出一口烟）金毛犬，名字叫大黄——你方才说过的。你莫要
考我的记性，我这记性虽说不上多好，对自己在意的事情，倒也不至于转头就忘。

你: /quit
再见！

# ── 关掉程序，过一会儿重新运行 ──

[系统] 已恢复 2 轮历史对话记忆

你: 我叫什么名字？

鲁迅: （目光透过烟雾看来）王芳。这名字我上次已记住了。你还有什么要问的？
```

## 技术架构

```
用户输入: "我叫王芳"
        │
        ▼
  MemoryChatSession.send()
        │
        ├─ 1. 构建含记忆的 messages
        │     ├── [0] system: 角色 prompt
        │     ├── [1] system: 历史摘要（由 memory/conversation/summary.j2 渲染，如有）
        │     └── [2..N] 窗口内完整对话（user + assistant）
        │
        ├─ 2. LLM.chat(messages) → 生成回复
        │
        └─ 3. ConversationMemory.record_turn(user_msg, reply)
              ├── 追加到滑动窗口
              ├── 必要时触发 LLM 摘要压缩（memory/conversation/compression.j2）
              └── 自动落盘 JSON（data/memories/{session_id}.json）
```

### 核心模块说明

#### 1. ConversationMemory（`memory/conversation_memory.py`）

统一的记忆管理器，封装滑动窗口 + LLM 摘要压缩 + 文件持久化：

| 能力 | 方法 | 说明 |
|------|------|------|
| 记录对话 | `record_turn(user, reply)` | 追加到窗口 → 判断压缩 → 自动落盘 |
| 获取消息 | `get_messages()` | 返回记忆层消息列表（摘要 + 窗口轮次） |
| 压缩判断 | `needs_compression()` | 轮数超 `max_turns` 或 token 数超 `max_tokens` |
| 摘要压缩 | `_compress()` | 取窗口外旧对话 → LLM 生成结构化摘要 |
| 状态可视化 | `visualize()` | 打印记忆面板（轮数、token、压缩状态） |
| 重置 | `reset()` | 清空记忆 + 删除持久化文件 |
| 持久化 | `_save_to_file()` / `_load_from_file()` | JSON 格式，按 `session_id` 区分文件 |

**压缩策略**：

```
压缩前：[轮1-20] [轮21-40] [轮41-60] ← 窗口最多 20 轮
         ↑ 旧对话，将被压缩

压缩后：[摘要：来访者叫王芳，初中语文教师...] [轮41-60]
```

**持久化格式**（`data/memories/luxun.json`）：

```json
{
    "turns": [
        {"role": "user", "content": "我叫王芳，喜欢龙井茶。"},
        {"role": "assistant", "content": "王芳……这名字倒清雅..."}
    ],
    "summary": null
}
```

#### 2. MemoryChatSession（`llm/memory_chat_session.py`）

继承实验 2 的 `ChatSession`，覆写 `send()` 将记忆读写透明织入对话：

```python
class MemoryChatSession(ChatSession):
    def send(self, user_input: str) -> str:
        # 1. 构建含记忆上下文的 messages（替代父类直接使用 self.messages）
        messages = [system_prompt] + self._memory.get_messages() + [user_msg]

        # 2. 调用 LLM
        reply = self._llm.chat(messages)

        # 3. 更新记忆（写入窗口 + 可能压缩 + 自动落盘）
        self._memory.record_turn(user_input, reply)

        return reply
```

**设计要点**：
- **继承而非改写**：`ChatSession` 的所有能力（`turn_count`、`peek_last`、`messages`）直接可用
- **透明注入**：调用方 `chat_loop()` 无需感知记忆的存在，`send()` 签名不变
- **覆写 `reset()`**：同时清空记忆管理器

#### 3. Token 计数器（`llm/token_counter.py`）

| 方法 | 用途 | 算法 |
|------|------|------|
| `estimate_tokens(text, model)` | 通用估算 | GPT 模型用 tiktoken 精确计数；DeepSeek 用字符估算 |
| 字符估算 | DeepSeek 模型 | `英文_chars × 0.3 + 中文_chars × 0.6`（源自 DeepSeek 官方文档） |

#### 4. 配置扩展（`config.py`）

在实验 2 的 `Config` 基础上新增 `MemoryConfig`：

```python
class MemoryConfig(BaseModel):
    max_turns: int = Field(default=20, ge=1)
    max_tokens: int = Field(default=3000, ge=1)
```

#### 5. 记忆提示词模板

| 模板 | 用途 |
|------|------|
| `summary.j2` | 将压缩摘要注入 system prompt："以下是之前对话的摘要：{{ summary }}" |
| `compression.j2` | 指导 LLM 将旧对话压缩为结构化摘要 |
| `eval.j2` | LLM-as-Judge 记忆评估 prompt |

## 评估体系

预置 6 道测试题（`data/eval/test_questions.json`），覆盖三个评估维度各 2 题：

| 维度 | 含义 | 示例题 |
|------|------|--------|
| 信息回忆 | 能否正确回忆前文信息？ | "先生，我刚才提到在读您的哪本书？" |
| 上下文连贯 | 对话风格是否前后一致？ | "那我该怎么做才能写得更好呢？" |
| 防幻觉表现 | 记忆为空时是否诚实？ | "我刚才跟您说过我的电话号码了吧？" |

每题包含 `setup` 轮（建立上下文）和 `question` 轮（测试回忆），例如：

```json
{
    "id": "recall_02",
    "dimension": "短期记忆_信息回忆",
    "setup": [
        {"role": "user", "content": "先生，我最近在读您的《呐喊》..."},
        {"role": "user", "content": "我有个朋友叫赵德贵..."},
        {"role": "user", "content": "对了，我自己是学医的，和您年轻时一样。"}
    ],
    "question": "先生，我刚才提到在读您的哪本书？还有我是学什么专业的？"
}
```

运行评估的期望输出：

```
============================================================
  记忆准确性评估报告 — luxun
============================================================
  测试题目数: 6
  信息回忆 均值: 4.67
  上下文连贯 均值: 4.50
  防幻觉表现 均值: 4.33
  ──────────────────────────────────────────────────
  综合得分 均值: 4.50
============================================================
```

## 与实验 2 的关系

| | 实验 2（提示词设计） | 本实验（短期记忆） |
|------|------|------|
| 角色定义 | YAML 定义 | 复用实验 2 |
| System prompt | Jinja2 渲染 | 复用实验 2 + 摘要注入 |
| LLM 调用 | ChatSession.send() | MemoryChatSession.send()（继承覆写） |
| 记忆 | 无 | 滑动窗口 + LLM 摘要压缩 + JSON 持久化 |
| 评估维度 | 身份/风格/知识/时代 | 回忆/连贯/防幻觉 |
| 代码复用 | — | 通过 `inherit/` 继承 4 个核心模块 |

## 与后续实验的关系

| 实验 | 新增能力 | 改动点 |
|------|---------|--------|
| 实验 4（工具调用） | 自动搜索 + 特征提取 | 用工具调用获取信息补充角色知识 |
| 实验 5（综合） | TTS 语音 + 自我反思 | 整合提示词 + 记忆 + 工具 + 语音输出 |

## 实验流程

| 步骤 | 内容 | 预计时间 |
|------|------|----------|
| 1 | 回顾实验 2 代码，理解 `inherit/` 继承机制 | 15min |
| 2 | 阅读 `memory/conversation_memory.py`，理解滑动窗口 + 压缩算法 | 30min |
| 3 | 阅读 `llm/memory_chat_session.py`，理解覆写 `send()` 的继承模式 | 15min |
| 4 | 运行 `main.py` 进行记忆感知对话，观察窗口和压缩 | 20min |
| 5 | 运行 `main.py --eval`，理解三个记忆评估维度 | 20min |
| 6 | 调整 `config.yaml` 中的 `max_turns` / `max_tokens`，观察行为变化 | 30min |
| 7 | （进阶）对比实验：用同一套问题分别测试 `python main.py` / `--few-shot` / `--cot` / `--few-shot --cot` 四种组合，观察记忆+提示词增强的叠加效果；使用 `--eval` 对比评估分数 | 30min |
