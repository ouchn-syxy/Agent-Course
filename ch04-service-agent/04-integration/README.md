# 实验 12：网店客服智能体综合实践

> 对应章节 4.4 实战：网店客服智能体 ｜ 2 学时 ｜ ✅ 已完成

## 概述

本实验将前三次实验的成果整合为**完整的网店客服批量 GUI 自动回复系统**：

```
实验 9（文本决策层）  →  实验 10（视觉感知层）  →  实验 11（GUI 执行层）
    分类+策略+回复          截图+消息提取            键鼠操作原语
          │                      │                      │
          └──────────────────────┼──────────────────────┘
                                 │
                                 ▼
                    实验 12（综合编排层）
              批量遍历用户 → 截图 → 识别 → 分类
              → 策略 → 回复 → GUI 发送 → 截图验证 → 下一个
```

核心思路：

```
BatchGUIReplyAgent（批量编排器）
  │
  ├─ 步骤 1：截图客服工作台 → VLM 识别左侧栏用户选项卡
  │
  ├─ 步骤 2：循环点击每个用户选项卡
  │     │
  │     └─ GUIReplyAgent（单用户 GUI 编排器）
  │           │
  │           ├─ 截图聊天窗口
  │           ├─ VLM 看图 → 提取沟通记录
  │           ├─ 调用 generate_reply 工具
  │           │    ├─ Classifier（消息分类）
  │           │    ├─ StrategyEngine（策略决策）
  │           │    └─ ReplyGenerator（Tool Calling 生成回复）
  │           └─ VLM 继续看图 → 输入框粘贴 → 点击发送
  │                              → 重新截图验证回复气泡
  │
  └─ 步骤 3：输出批量处理统计摘要
```

与前三个实验不同，本实验的 **SAL 查询层对接真实的后端 HTTP API**（`eshop-service-workbench`），商品信息、订单、物流等数据均来自真实数据库，而非 Mock 数据。

## 架构总览

### 双层编排架构

```
┌─────────────────────────────────────────────────────────┐
│  BatchGUIReplyAgent（批量编排器）                          │
│                                                         │
│  职责：截图工作台 → 识别用户 → 循环调度 → 统计汇总         │
│                                                         │
│  ┌─────────────────────────────────────────────────┐   │
│  │  GUIReplyAgent（单用户 GUI 编排器）                │   │
│  │                                                   │   │
│  │  职责：VLM ReAct 循环驱动 GUI 操作                  │   │
│  │                                                   │   │
│  │  截图 → VLM 看图决策 → 调用工具 → 结果回传          │   │
│  │    ↑                              ↓               │   │
│  │    └──────── 链式操作 ←───────────┘               │   │
│  │                                                   │   │
│  │  工具：click / type_text / clipboard /            │   │
│  │        generate_reply（内置分类→策略→回复流水线）    │   │
│  └─────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────┘
```

### 回复流水线（内嵌于 generate_reply 工具）

```
客户沟通记录（VLM 从截图提取）
      │
      ▼
┌──────────────┐      ┌──────────────┐
│ Classifier    │ ←── │ core.json    │  4 大类
│ 消息分类器     │      │ sub.json     │  13 子类
└──────┬───────┘      └──────────────┘
       │ MessageClassificationResult
       ▼
┌──────────────┐
│ StrategyEngine│      规则 + LLM 升级判定
│ 策略引擎       │
└──────┬───────┘
       │ HandlingStrategy（AUTO / AUTO_WITH_ESCALATION / HUMAN / IGNORE）
       ▼
┌──────────────┐      ┌──────────────────────┐
│ ReplyGenerator│ ←── │ 真实后端 HTTP API × 5  │
│ 回复生成器      │      │ 商品 · 订单 · 库存 · 退换货 │
└──────┬───────┘      └──────────────────────┘
       │
       ▼
  回复文本（返回给 VLM → 粘贴进输入框 → 点击发送）
```

## 功能清单

| 功能 | 命令 | 说明 |
|------|------|------|
| 批量自动回复 | `python main.py` | 自动遍历用户选项卡，逐一处理聊天消息 |
| 定向处理用户 | `python main.py --target-user 钱七` | 精确匹配并只处理指定用户，适合课堂演示 |
| 自定义处理上限 | `python main.py --max-users 30` | 最多处理 30 个用户会话 |
| 自定义步数限制 | `python main.py --max-steps 15` | 每用户最多 15 步 ReAct |
| 调整等待时间 | `python main.py --wait 3.0` | 切换用户后等待 3 秒 |
| 安静模式 | `python main.py --quiet` | 减少日志输出 |

## 文件结构

```
04-integration/
├── config.yaml                    # 双模型配置（LLM + VLM + 后端地址）
├── config.yaml.example            # 配置模板（DeepSeek / Qwen / 智谱 / OpenAI）
├── requirements.txt               # 实验依赖
│
├── data/                          # 数据文件
│   └── eshop_service/
│       └── message_category/
│           ├── core.json          #   4 个消息大类定义
│           └── sub.json           #   13 个消息子类 + 策略规则
│
├── prompts/                       # Jinja2 提示词模板
│   └── agents/eshop_service/
│       ├── batch_gui_reply_agent/
│       │   └── identify_users.j2  #   VLM 识别用户选项卡提示词
│       ├── gui_reply_agent/
│       │   ├── system.j2          #   GUI ReAct 系统提示词（动态注入工具 Schema）
│       │   └── extract_conversation.j2  # VLM 消息提取提示词
│       ├── message_classifier/    #   （inherit）分类提示词
│       ├── reply_generator/
│       │   └── generate.j2        #   回复生成提示词（带 Tool Calling 要求）
│       ├── strategy_engine/       #   （inherit）策略引擎提示词
│       └── vision/                #   VLM 视觉分析提示词
│
├── src/                           # 核心代码
│   ├── main.py                    #   CLI 入口（组装批量编排器）
│   ├── config.py                  #   Pydantic v2 配置模型
│   │
│   ├── agents/eshop_service/
│   │   ├── batch_gui_reply_agent.py  # 批量编排器（遍历用户 + 统计）
│   │   ├── gui_reply_agent.py        # GUI ReAct 编排器（VLM FC 循环）
│   │   ├── reply_generator.py        # Tool Calling 回复生成器
│   │   └── sal/
│   │       ├── api.py                # 5 个后端查询函数 + ToolDef 定义
│   │       └── api_client.py         # HTTP API 客户端（对接 eshop-service-workbench）
│   │
│   ├── inherit/                   # 继承的通用组件
│   │   └── agents/eshop_service/
│   │       ├── message_category_manager.py  # 分类管理器
│   │       ├── message_classifier.py        # Few-shot 分类器
│   │       ├── strategy_engine.py           # 策略引擎
│   │       ├── models/types.py              # 领域模型
│   │       └── sal/                         # SAL 类型 + 原始 mock
│   │
│   └── vlm/                       # VLM 客户端
│
├── output/                        # 运行输出（预留）
├── test_sessions/                 # 测试会话记录（预留）
├── tmp/                           # 运行时截图临时目录
└── docs/
    ├── design.md                  # 当前实现对应的详细设计
    └── 教案讲课稿.md               # 教案式讲课稿
```

## 快速开始

### 1. 安装依赖

```bash
cd ch04-service-agent/04-integration
pip install -r requirements.txt
```

依赖包：

| 包名 | 用途 |
|------|------|
| `openai` | LLM + VLM API 调用（兼容 DeepSeek / Qwen / 智谱 / OpenAI） |
| `PyYAML` | YAML 配置文件解析 |
| `pydantic` | 领域模型与配置校验（v2） |
| `jinja2` | 提示词模板渲染 |
| `Pillow` | 截图图像处理、VLM 图片编码 |

### 2. 配置双模型

```bash
cp config.yaml.example config.yaml
# 编辑 config.yaml，填写 LLM 和 VLM 的 api_key_env
```

> ⚠️ `config.yaml` 已被 `.gitignore` 排除，不会提交到 Git。
>
> LLM 和 VLM 可以使用**不同模型**：LLM 负责文本分类和回复生成（可用 deepseek-v4-flash），VLM 负责截图理解和界面识别（需要视觉模型）。

### 3. 启动后端服务

```bash
# 终端一：启动网店客服模拟平台后端
cd ch04-service-agent/eshop-service-workbench/backend
uvicorn main:app --reload --port 8000

# 终端二：启动前端
cd ch04-service-agent/eshop-service-workbench/frontend
npm run dev
```

### 4. 打开客服界面

用外部 Google Chrome 打开前端页面，确认标签页标题含“网店客服工作台”，并确保左侧能看到钱七。程序只激活这个已经打开的 Chrome 窗口，不会自动打开页面，也不会把其他 Chrome 窗口当作工作台。

### 5. 运行批量处理

```bash
cd src
python main.py

# 自定义参数
python main.py --max-users 30 --max-steps 15 --wait 3.0

# 课堂案例：只处理钱七
python main.py --target-user 钱七 --max-steps 20 --wait 2.0
```

## 运行效果

以下日志展示定向处理“钱七”的关键阶段。模型名称、截图文件名、坐标和耗时会随本机运行状态变化。

### 启动日志

```
🔌 LLM:   deepseek/deepseek-v4-flash @ https://api.deepseek.com
🔌 VLM:   volcano/doubao-seed-2-0-lite-260215 @ https://ark.cn-beijing.volces.com/api/v3
🔧 每用户最大步数: 20  |  切换等待: 2.0s  |  最多处理: 1 个会话
🎯 指定用户: 钱七

✅ 已确认 Google Chrome 位于最前台，准备查找工作台窗口
🪟 窗口: Google Chrome - 网店客服工作台 (1470×867)
🔍 正在通过 VLM 识别左侧栏用户选项卡...
✅ 识别到多个用户选项卡:
  [1] 张三 @ 绝对坐标 (120, 180)
  ...
  [7] 钱七 @ 绝对坐标 (120, 540)
🎯 课堂定向演示：仅处理用户「钱七」
  ...
```

### 单用户处理日志

```
── [1/1] 切换到用户: 钱七 ──
  🖱️ 点击成功: (120, 540)
  ⏳ 等待 2.0s 页面加载...
============================================================
🚀 GUI 自动化编排器 启动 (VLM-FC Agent)
   VLM: volcano/doubao-seed-2-0-lite-260215
   最大步数: 20
   工具: ['click', 'type_text', 'clipboard_write', 'clipboard_paste', 'scroll', 'generate_reply']
============================================================
── Step 1 ──
🪟 窗口: Chrome — 网店客服工作台 (id=12345)
  💬 收到沟通记录: 1 条
  ✏️ 生成回复: 已核对钱七的订单、售后条件与黑色 L 码库存，下面给出换货答复...
  🔧 clipboard_write → 已写入剪贴板
  🔧 click → 点击成功: (960, 860)
  🔧 clipboard_paste → 粘贴成功
  🔧 click → 点击成功: (1100, 860)
  🔎 发送动作已执行，等待页面更新后重新截图验证
── Step 2 ──
📸 截图完成: 1470x867 → screenshot_….png
  ✅ 处理完成: 发送验证成功
  ✅ 用户 钱七 处理完成 (…s): 处理完成
```

### 批量处理统计摘要

```
============================================================
📊 批量处理统计摘要
============================================================
  处理总数: 1 个用户会话
  总耗时: …s
  平均耗时: …s / 用户
------------------------------------------------------------
  [1] 钱七 (…s) → 处理完成
============================================================
```

## 核心设计要点

### 1. 双层编排

| 层级 | 组件 | 职责 | 驱动方式 |
|------|------|------|---------|
| 外层 | `BatchGUIReplyAgent` | 识别用户列表、循环调度、统计汇总 | VLM 纯视觉识别 |
| 内层 | `GUIReplyAgent` | 看截图 → 提取消息 → 生成回复 → GUI 操作 | VLM Function Calling |

### 2. generate_reply 工具封装

`GUIReplyAgent` 不直接调用 Classifier / StrategyEngine / ReplyGenerator，而是将它们封装为一个名为 `generate_reply` 的 Function Calling 工具。VLM 从截图中提取沟通记录后，调用该工具获取回复文本，再驱动 GUI 操作发送。

```
VLM 看图 → 提取沟通记录 → 调用 generate_reply(messages=[...])
                              │
                              ├─ Classifier.classify()
                              ├─ StrategyEngine.decide()
                              └─ ReplyGenerator.generate()
                              │
                              ▼
                         返回回复文本（或"需人工介入"/"无需回复"）
```

### 3. 真实后端数据

与前三个实验使用 Mock 数据不同，本实验的 `sal/api.py` 对接 `eshop-service-workbench` 后端，通过 HTTP API 查询真实商品信息、订单详情、库存状态和售后政策，杜绝 LLM"幻觉编造数据"的可能性。

### 4. 多模型分工

| 模型 | 职责 | 调用方式 |
|------|------|---------|
| LLM（文本模型） | 消息分类、策略判定、回复生成 | `LLMClient` / `ToolLLMClient` |
| VLM（视觉模型） | 截图理解、消息提取、界面元素定位 | `ToolVLMClient`（图片 + Function Calling） |
