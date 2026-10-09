# 实验 9：电商客服场景分析与流程设计

> 对应章节 4.1 上岗培训：场景分析与流程设计 ｜ 2 学时 ｜ ✅ 已完成

## 概述

本实验通过 **JSON 配置分类体系 + LLM Few-shot 分类 + 策略引擎路由 + Tool Calling 回复**，搭建一套完整的电商客服消息处理流水线。

核心思路：

```
客户消息 → 分类器（是什么）→ 策略引擎（怎么做）→ 回复生成器（说什么）
                                                    ↘ 查商品/订单/物流（Mock API）
```

学生无需操作真实客服系统——分类规则存于 JSON 文件、回复用 Mock 数据验证，全部逻辑集中在纯文本层面。另可通过 `--workflow` 一键导出 Mermaid 流程图。

## 功能清单

| 功能 | 命令 | 说明 |
|------|------|------|
| 交互式演示 | `python main.py` | 逐条输入客户消息，查看分类→策略→AI 回复全流程 |
| 导出流程图 | `python main.py --workflow` | 基于分类配置自动生成 Mermaid 流程图 DSL |

## 文件结构

```
01-scenario-design/
├── config.yaml                    # LLM 配置（Pydantic v2 校验）
├── config.yaml.example            # 多厂商配置模板（DeepSeek / Qwen / 智谱 / OpenAI）
├── requirements.txt               # 实验依赖
│
├── data/                          # 数据文件
│   ├── sample_messages.json       #   22 条标注示例消息（覆盖全部 13 个子类）
│   └── eshop_service/
│       └── message_category/
│           ├── core.json          #   4 个消息大类定义
│           └── sub.json           #   13 个消息子类 + 策略规则
│
├── prompts/                       # Jinja2 提示词模板
│   └── agents/eshop_service/
│       ├── message_classifier/
│       │   └── classify.j2        #   消息分类提示词（Few-shot + 分类体系注入）
│       ├── strategy_engine/
│       │   └── evaluate_escalation.j2  # 升级评估提示词
│       └── reply_generator/
│           └── generate.j2        #   回复生成提示词（带 Tool Calling）
│
├── src/                           # 核心代码
│   ├── main.py                    #   CLI 入口（交互式 / workflow 两种模式）
│   ├── config.py                  #   Pydantic v2 配置模型
│   └── agents/eshop_service/
│       ├── message_category_manager.py  # 分类管理器（加载 core / sub JSON）
│       ├── message_classifier.py        # LLM Few-shot 消息分类器
│       ├── strategy_engine.py           # 策略引擎（四步决策）
│       ├── reply_generator.py           # Tool Calling 回复生成器
│       ├── workflow_render.py           # Mermaid 流程图渲染
│       ├── models/
│       │   └── types.py                 # 领域模型（8 个 Pydantic DTO + 1 个枚举）
│       └── sal/
│           ├── api.py                   # 6 个 Mock 查询函数 + ToolDef 定义
│           ├── mock.py                  # Mock 数据（商品/订单/物流/客户）
│           └── types.py                # SAL 数据类型
│
├── docs/                          # 文档
│   ├── design.md                  #   设计文档
│   ├── 消息分类与处理流程图.md      #   流程图预览
│   └── 教案讲课稿.md               #   教案讲课稿
│
└── tests/                         # 测试（预留）
```

## 快速开始

### 1. 安装依赖

```bash
cd ch04-service-agent/01-scenario-design
pip install -r requirements.txt
```

依赖包：

| 包名 | 用途 |
|------|------|
| `openai` | LLM API 调用（兼容 DeepSeek / Qwen / 智谱 / OpenAI） |
| `PyYAML` | 解析 YAML 配置文件 |
| `pydantic` | 领域模型与配置校验（v2，`model_validate`） |
| `jinja2` | 提示词模板渲染 |

### 2. 配置 LLM

```bash
cp config.yaml.example config.yaml
# 编辑 config.yaml，将 api_key_env 替换为你的 API Key
```

> ⚠️ `config.yaml` 已被 `.gitignore` 排除，不会提交到 Git。

### 3. 运行

```bash
# 进入 src 目录运行
cd src
python main.py

# 导出 Mermaid 流程图（无需 LLM，纯本地生成）
python main.py --workflow
```

## 对话效果

以下为交互式模式下的典型输入输出。

> [待运行验证] 以下输出于 2026-07-21 使用 deepseek-v4-flash 运行获得，代码更新后需重新验证。

### 售前咨询 — 库存查询

```
👤 客户消息: 这个红色的还有M码吗？
📨 这个红色的还有M码吗？
──────────────────────────────────────────────────
 分类: 售前咨询 / 库存查询
🎯 置信度: 0.95
😊 情感: 中性  |  ⚡ 紧急度: 普通
🔑 关键信息: {'product': '商品', 'color': '红色', 'size': 'M'}

📋 策略决策:
   回复模式: ✅ 自动回复
   查商品:   是
   查订单:   否
   回复模板: 亲，关于'{product}'，{query_result}。还有其他问题吗？
   操作提示: 查询商品信息, 确认库存和尺码, 生成回复并发送
──────────────────────────────────────────────────

⏳ 正在生成回复...
🤖 AI 回复:
亲，您好！😊 请问您说的是哪一款红色商品呢？方便告诉我具体的商品名称吗？这样我马上帮您查一下M码的库存情况～
```

### 售后服务 — 退货退款

```
👤 客户消息: 鞋子穿了三天就开胶了，我要退货！
📨 鞋子穿了三天就开胶了，我要退货！
──────────────────────────────────────────────────
 分类: 售后服务 / 退货退款
🎯 置信度: 0.95
😊 情感: 负面  |  ⚡ 紧急度: 普通
🔑 关键信息: {'product': '鞋子', 'issue': '开胶'}

📋 策略决策:
   回复模式: ⚠️ 自动回复（可升级转人工）
   查商品:   否
   查订单:   是
   回复模板: 亲，非常抱歉给您带来不便。{resolution}。请问还有其他需要帮您的吗？
   操作提示: 查询订单详情, 确认商品售后政策, 判断是否符合退货条件, 生成回复
──────────────────────────────────────────────────

⏳ 正在生成回复...
  🔧 [query_return_policy] → 支持7天无理由退货，商品须保持原状（未穿着、未洗涤、吊牌完整）。退回运费由买家承担（质量问题除外）。退款在仓库签收后1-3个工作日到账。以下商品不支持退货：...
🤖 AI 回复:
亲，我已经查到了咱们的售后政策，来跟您说一下：

您反馈的鞋子**开胶属于质量问题**，这个您放心，质量问题是支持处理的，而且**退回运费由我们承担**，您不需要出运费哦！👍

不过为了帮您进一步操作，我需要先查一下您的订单信息，方便您提供一下**订单号**吗？有了订单号我就能帮您走退货流程啦~
```

### 投诉 — 商品质量投诉

```
👤 客户消息: 你们卖的羽绒服是次品！钻绒还脏！坑人！
📨 你们卖的羽绒服是次品！钻绒还脏！坑人！
──────────────────────────────────────────────────
 分类: 投诉 / 商品质量投诉
🎯 置信度: 0.95
😊 情感: 愤怒  |  ⚡ 紧急度: 紧急
🔑 关键信息: {'product': '羽绒服', 'issue': '钻绒、脏'}

📋 策略决策:
   回复模式: ❌ 转人工处理
   转人工原因: 客户投诉商品质量，需人工介入处理退赔
   查商品:   否
   查订单:   是
   回复模板: 亲，非常理解您的心情，给您带来不愉快的体验我们深表歉意。我已经记录了您的问题，马上为您转接专属客服处理，请稍等~
   操作提示: 安抚客户情绪, 查询订单详情, 标记转人工
──────────────────────────────────────────────────
```

### 垃圾广告 — 引流广告

```
👤 客户消息: 加我微信 xxxxx，有优惠
📨 加我微信 xxxxx，有优惠
──────────────────────────────────────────────────
 分类: 垃圾广告 / 引流广告
🎯 置信度: 0.95
😊 情感: 中性  |  ⚡ 紧急度: 普通

📋 策略决策:
   回复模式: 🚫 忽略不回复
   查商品:   否
   查订单:   否
   操作提示: 忽略, 标记已处理
──────────────────────────────────────────────────
```

## 技术架构

### 数据流图

```
data/eshop_service/message_category/
├── core.json       ────┐
└── sub.json        ────┤
                         ▼
              MessageCategoryManager
                         │
                         ▼
用户输入 ──→ MessageClassifier ──→ StrategyEngine ──→ ReplyGenerator ──→ AI 回复
                 │                      │                   │
                 ▼                      ▼                   ▼
           classify.j2          evaluate_escalation.j2   generate.j2
           (Few-shot 分类)       (升级判定)              (Tool Calling)

                                                    ┌──────────────┐
                                                    │ Mock 查询 API │
                                                    │ 商品·订单·物流 │
                                                    │ ·售后政策     │
                                                    └──────────────┘
```

### 核心模块

| 模块 | 职责 | 关键类/函数 |
|------|------|------------|
| `message_category_manager.py` | 加载 JSON 分类体系，提供查询接口 | `MessageCategoryManager` · `find_core()` · `find_sub()` |
| `message_classifier.py` | LLM Few-shot 消息分类 | `MessageClassifier.classify()` → `MessageClassificationResult` |
| `strategy_engine.py` | 四步决策：验证→查策略→升级评估→紧急兜底 | `StrategyEngine.decide()` → `HandlingStrategy` |
| `reply_generator.py` | Tool Calling 循环查数据 + 生成回复 | `ReplyGenerator.generate()` → `str` |
| `workflow_render.py` | 基于分类配置生成 Mermaid 流程图 | `render_mermaid()` → Mermaid DSL |
| `sal/api.py` | 6 个 Mock 查询工具（商品/订单/物流/售后） | `TOOLS` 字典 → `query_product_info()` 等 |
| `models/types.py` | 领域模型 DTO | `ConversationMessage` · `MessageClassificationResult` · `HandlingStrategy` · `ResponseMode` |
| `main.py` | CLI 入口，组装三大模块 | `main()` → `interactive_mode()` / `workflow_mode()` |

### 分类体系（4 大类 × 13 子类）

| 大类 | 子类 | 回复模式 | 需查商品 | 需查订单 |
|------|------|----------|----------|----------|
| **售前咨询** | 库存查询 | auto | ✅ | — |
| | 尺码咨询 | auto | ✅ | — |
| | 商品信息 | auto | ✅ | — |
| | 商品推荐 | auto | ✅ | — |
| | 物流咨询 | auto | — | — |
| | 复购咨询 | auto | ✅ | ✅ |
| **售后服务** | 退货退款 | auto_with_escalation | — | ✅ |
| | 换货 | auto_with_escalation | ✅ | ✅ |
| | 物流查询 | auto | — | ✅ |
| **投诉** | 商品质量投诉 | human | — | ✅ |
| | 服务投诉 | human | — | — |
| **垃圾广告** | 引流广告 | ignore | — | — |
| | 无关内容 | ignore | — | — |

### 策略引擎四步决策

```
MessageClassificationResult
         │
    ┌────▼────┐  大类不存在？
    │ 1. 验证  │──────→ HandlingStrategy(response_mode=HUMAN)
    └────┬────┘
         │ 存在
    ┌────▼────┐
    │ 2. 查子类 │  find_sub() → 获取预设 HandlingStrategy
    └────┬────┘
         │
    ┌────▼────────────┐  auto_with_escalation？
    │ 3. 升级评估(LLM) │──────→ LLM 判定 → 可能升级为 HUMAN
    └────┬────────────┘
         │
    ┌────▼────┐  AUTO 且紧急？
    │ 4. 兜底  │──────→ 强制升级为 HUMAN
    └────┬────┘
         ▼
   最终 HandlingStrategy
```

### 设计要点

- **配置驱动**：分类体系和策略规则全部存于 JSON 文件，修改策略无需改代码
- **LLM 做语义理解**：用 Few-shot 提示词让模型"理解"消息含义，而非正则匹配关键词
- **规则兜底**：紧急消息自动升级、未知类型转人工——即使 LLM 误判也有安全网
- **Mock 数据隔离**：回复生成器查的是 Mock 数据，不依赖真实客服系统

## 与后续实验的关系

本实验是第四章的基础模块。后续实验将在此基础上：

| 实验 | 新增能力 | 与本实验的关系 |
|------|---------|---------------|
| 实验 10（视觉理解） | 截图 + 多模态识别消息文本 | 将视觉识别的文本喂给本实验的分类器 |
| 实验 11（GUI 自动化） | 键鼠操作 + 操作规划 | 根据本实验的 `action_hints` 规划操作序列 |
| 实验 12（综合实战） | 批量处理 + 质量评估 | 本实验的三大模块作为决策引擎被集成调用 |

```
实验 10（视觉）→ 实验 9（决策，即本实验）→ 实验 11（操作）
                       ↕
              实验 12（综合编排）
```

## 实验流程

| 步骤 | 内容 | 预计时间 |
|------|------|----------|
| 1 | 阅读 `data/eshop_service/message_category/` 下的 `core.json` 和 `sub.json`，理解 4 大类 × 13 子类的分类体系 | 15min |
| 2 | 阅读 `prompts/agents/eshop_service/message_classifier/classify.j2`，理解 Few-shot 提示词如何注入分类体系 | 15min |
| 3 | 运行 `python main.py`，逐条测试 4 大类消息，观察分类→策略→回复全流程 | 30min |
| 4 | 在 `data/sample_messages.json` 中新增 3-5 条自定义消息，验证分类准确性 | 20min |
| 5 | 修改 `sub.json` 中某一子类的策略规则（如调整 `response_mode`、增删 `escalation_rules`），重新运行观察决策变化 | 20min |
| 6 | 运行 `python main.py --workflow` 导出流程图，对比修改前后的流程图变化 | 20min |
| **合计** | | **2 学时** |
