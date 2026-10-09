# 实验 10：多模态视觉理解与界面识别

> 对应章节 4.2 火眼金睛：多模态视觉理解 ｜ 2 学时 ｜ ✅ 已完成

## 概述

本实验通过 **VLM 多模态大模型 + 截图分析 + 元素定位**，为网店客服智能体装上"眼睛"，使其能够"看见"客服工作台界面，理解界面结构和消息内容。

核心思路：

```
截图 → ScreenAnalyzer（VLM 分析）→ UI 结构 + 消息内容 + 可交互元素
截图 → ElementLocator（VLM 定位）→ 目标元素的屏幕坐标
```

实验 9 解决了"收到消息后怎么决策"的问题——但那只是纯文本处理。真实场景中，客服面对的是一个 GUI 工作台，消息在聊天窗口里，按钮在界面上。本节实验的目的就是让智能体**从截图中提取结构化信息**，并**定位界面元素的位置**，为后续的 GUI 自动化操作提供感知能力。

## 功能清单

| 功能 | 命令 | 说明 |
|------|------|------|
| 截图分析 | `python main.py --image screenshot.png --mode analyze` | 识别 UI 区域、提取消息文本、标注可交互元素 |
| 元素定位 | `python main.py --image screenshot.png --mode locate --target "发送按钮"` | 用自然语言描述目标，VLM 返回像素坐标 |

## 文件结构

```
02-vision/
├── config.yaml                    # VLM 配置（Pydantic v2 校验）
├── config.yaml.example            # 多厂商配置模板（DeepSeek / Qwen / 智谱 / OpenAI / 火山方舟）
├── requirements.txt               # 实验依赖
│
├── data/                          # 数据文件
│   ├── tests/
│   │   └── screenshot.png         #   测试用客服工作台截图
│   └── eshop_service/
│       └── message_category/
│           ├── core.json          #   4 个消息大类定义（继承自实验 9）
│           └── sub.json           #   13 个消息子类 + 策略规则
│
├── prompts/                       # Jinja2 提示词模板
│   └── agents/eshop_service/
│       └── vision/
│           ├── analyze.j2         #   截图分析提示词（区域识别 + 消息提取）
│           └── locate.j2          #   元素定位提示词（自然语言 → 坐标）
│
├── src/                           # 核心代码
│   ├── main.py                    #   CLI 入口（analyze / locate 两种模式）
│   ├── config.py                  #   Pydantic v2 配置模型
│   ├── vlm/
│   │   └── client.py              #   VLM 客户端（双后端自适应：火山方舟 / OpenAI Vision）
│   └── agents/eshop_service/
│       └── vision/
│           ├── screen_analyzer.py #   截图分析器（区域 + 消息 + 元素）
│           ├── element_locator.py #   元素定位器（自然语言 → 屏幕坐标）
│           └── models/
│               └── types.py       #   视觉分析领域模型（6 个 Pydantic DTO）
│
└── docs/                          # 文档
    ├── design.md                  #   当前实现对应的详细设计
    └── 教案讲课稿.md               #   教案式讲课稿
```

## 快速开始

### 1. 安装依赖

```bash
cd ch04-service-agent/02-vision
pip install -r requirements.txt
```

依赖包：

| 包名 | 用途 |
|------|------|
| `openai` | VLM API 调用（兼容 DeepSeek / Qwen / 智谱 / OpenAI / 火山方舟） |
| `PyYAML` | 解析 YAML 配置文件 |
| `pydantic` | 领域模型与配置校验（v2，`model_validate`） |
| `jinja2` | 提示词模板渲染 |
| `Pillow` | 截图加载与 base64 编码 |

### 2. 配置 VLM

```bash
cp config.yaml.example config.yaml
# 编辑 config.yaml，将 vlm 段的 api_key_env 替换为你的 API Key
```

> ⚠️ `config.yaml` 已被 `.gitignore` 排除，不会提交到 Git。

`config.yaml.example` 中已预置多厂商配置模板：

| 厂商 | base_url | 推荐模型 |
|------|----------|---------|
| DeepSeek | `https://api.deepseek.com` | `deepseek-v4-flash` |
| 火山方舟 | `https://ark.cn-beijing.volces.com/api/v3` | `doubao-seed-2-0-lite-260428` |
| Qwen | `https://dashscope.aliyuncs.com/compatible-mode/v1` | `qwen-vl-max` |
| 智谱 | `https://open.bigmodel.cn/api/paas/v4` | `glm-4v` |
| OpenAI | `https://api.openai.com/v1` | `gpt-4o` |

> **注意**：不同厂商对图片的传入方式不同。火山方舟使用 Responses API 的 `input_image`，其他厂商使用 Chat Completions API 的 `image_url`（base64 Data URI）。`VLMClient` 已自动处理这些差异。

### 3. 准备截图

将客服工作台的截图放入 `data/tests/screenshot.png`，或使用你自己的截图文件。

### 4. 运行

```bash
# 进入 src 目录运行
cd src

# ── 模式一：截图分析（识别界面结构 + 提取消息） ──
python main.py --image ../data/tests/screenshot.png --mode analyze

# 带领域上下文约束（帮助 VLM 更准确地理解界面布局）
python main.py --image ../data/tests/screenshot.png --mode analyze \
  --context "三栏布局：左侧客户列表、中间聊天区、右侧信息面板"

# ── 模式二：元素定位（自然语言描述 → 屏幕坐标） ──
python main.py --image ../data/tests/screenshot.png --mode locate --target "发送按钮"

# 也可以指定窗口偏移量（将图片坐标转为屏幕绝对坐标）
python main.py --image ../data/tests/screenshot.png --mode locate \
  --target "客户列表中张三的条目"
```

## 运行效果

### 截图分析（mode=analyze）

```
🔌 VLM: deepseek/deepseek-v4-flash @ https://api.deepseek.com
📷 截图: screenshot.png (1920×1080)

============================================================
📊 截图分析结果
============================================================

👤 活跃客户: 张三

📐 识别到 4 个功能区域：
  ▸ 客户列表区
    边界: (0, 0) → (300, 1080), 300×1080
    可交互元素 (3):
      • 张三的条目 @ (150, 120)
      • 李四的条目 @ (150, 210)
      • 王五的条目 @ (150, 300)
  ▸ 聊天区
    边界: (300, 0) → (1320, 880), 1020×880
    可交互元素 (2):
      • 消息输入框 @ (810, 840)
      • 发送按钮 @ (1260, 840)
  ▸ 客户信息面板
    边界: (1320, 0) → (1920, 1080), 600×1080
    可交互元素 (1):
      • 订单详情标签 @ (1620, 100)
  ▸ 顶部工具栏
    边界: (0, 0) → (1920, 60), 1920×60

💬 聊天区消息 (3 条):
  [张三]🔴: 这个红色的还有M码吗？
  [张三]: 有优惠吗？
  [客服]: 亲，您好！请问有什么可以帮您的？

📝 截图全文识别 (156 字符)，预览:
  客户列表 张三 李四 王五 聊天区 这个红色的还有M码吗？ 有优惠吗？...
```

### 元素定位（mode=locate）

```
🔌 VLM: deepseek/deepseek-v4-flash @ https://api.deepseek.com
📷 截图: screenshot.png (1920×1080)

============================================================
🎯 元素定位结果
============================================================
  元素名称: 发送按钮
  置信度:   95%
  中心坐标: (1260, 840)
  边界框:   (1220, 825) → (1300, 855), 80×30

✅ 完成
```

元素定位结果中的坐标可以直接用于后续的键鼠控制操作。

## 技术架构

### 数据流图

```
截图（PIL Image） + 领域上下文（domain_context）
         │
         ▼
   ┌─────────────┐     ┌──────────────────┐
   │ VLMClient    │ ←── │ config.yaml       │  VLM 配置（双后端自适应）
   │ 双后端       │     │ analyze.j2        │  分析提示词（区域 + 消息）
   │ · 火山方舟   │     │ locate.j2         │  定位提示词（自然语言 → 坐标）
   │ · OpenAI     │     └──────────────────┘
   └──────┬──────┘
          │
    ┌─────┴─────┐
    │           │
    ▼           ▼
┌─────────┐  ┌──────────┐
│Screen   │  │Element   │
│Analyzer │  │Locator   │
│截图分析  │  │元素定位   │
└────┬────┘  └────┬─────┘
     │            │
     ▼            ▼
ScreenAnalysis  ElementLocation
· regions       · element_name
· messages      · center_x/y
· elements      · bbox
· raw_text      · confidence
     │            │
     ▼            ▼
  实验 9        实验 11
  消息分类      GUI 操作
```

### 核心模块

| 模块 | 职责 | 关键类/方法 |
|------|------|------------|
| `vlm/client.py` | VLM 客户端，封装多模态调用，自动适配火山方舟/OpenAI 双后端 | `VLMClient` · `chat_with_image()` · `chat_with_image_json()` |
| `vision/screen_analyzer.py` | 截图分析器，将截图送入 VLM 提取 UI 结构和消息 | `ScreenAnalyzer.analyze()` → `ScreenAnalysis` |
| `vision/element_locator.py` | 元素定位器，自然语言描述 → 屏幕绝对坐标 | `ElementLocator.locate()` → `ElementLocation` |
| `vision/models/types.py` | 视觉分析领域模型 DTO | `BoundingBox` · `UIElement` · `UIRegion` · `CustomerMessage` · `ScreenAnalysis` · `ElementLocation` |
| `config.py` | Pydantic v2 配置模型 | `Config.from_yaml()` → `LLMConfig` + `GenerationConfig` |
| `main.py` | CLI 入口，组装 VLM 客户端 + Analyzer/Locator | `main()` → `analyze` / `locate` 模式 |

### VLM 客户端双后端设计

```
┌─────────────────────────────────────────────────────────┐
│                     VLMClient                           │
│                                                         │
│  chat_with_image(image, prompt) → str                   │
│  chat_with_image_json(image, prompt) → str              │
│                                                         │
│  ┌─────────────────┐    ┌──────────────────────┐       │
│  │ provider=volcano │    │ provider=其他         │       │
│  │                  │    │                       │       │
│  │ Responses API    │    │ Chat Completions API  │       │
│  │ input_image      │    │ image_url (base64)    │       │
│  │ input_text       │    │ text                  │       │
│  │                  │    │ response_format=      │       │
│  │ (JSON: prompt尾  │    │   json_object         │       │
│  │  部追加约束)     │    │                       │       │
│  └─────────────────┘    └──────────────────────┘       │
│                                                         │
│  _encode_image(PIL.Image) → data:image/png;base64,...  │
└─────────────────────────────────────────────────────────┘
```

### 领域模型（6 个 Pydantic DTO）

| 模型 | 用途 | 关键字段 |
|------|------|---------|
| `BoundingBox` | 矩形边界框 | `x`, `y`, `width`, `height`（像素坐标） |
| `UIElement` | 可交互 UI 元素 | `name`, `bbox`, `center_x`, `center_y` |
| `UIRegion` | 界面功能区域 | `name`, `bbox`, `elements: list[UIElement]` |
| `CustomerMessage` | 聊天消息 | `customer_name`, `content`, `has_unread` |
| `ScreenAnalysis` | 截图完整分析结果 | `regions`, `messages`, `active_customer`, `raw_text` |
| `ElementLocation` | 元素定位结果 | `element_name`, `center_x/y`（屏幕绝对坐标）, `confidence` |

### 设计要点

- **领域上下文注入**：`ScreenAnalyzer` 和 `ElementLocator` 通过 `domain_context` 参数注入业务描述（如"三栏布局：左侧客户列表、中间聊天区、右侧信息面板"），分析器本身不耦合具体业务，适用于任何 GUI 截图分析场景
- **双后端自适应**：`VLMClient` 自动区分火山方舟 Responses API 和 OpenAI Vision Chat Completions API，调用代码无需关心底层差异
- **Schema 注入提示词**：通过 `render_model_code()` 将 Pydantic 模型定义渲染为 Python 代码字符串注入 Jinja2 模板，VLM 能准确理解期望的输出结构
- **坐标转换**：`ElementLocator` 自动将 VLM 返回的图片坐标 + `window_offset` 转为屏幕绝对坐标，为 GUI 自动化做好准备
- **@retry 容错**：两个公共方法均装饰 `@retry(max_retries=3, delay_s=2.0)`，应对网络波动
- **VLM 与文本分类分离**：`chat_with_image_json()` 的 JSON 模式对火山方舟通过 prompt 追加约束实现（因其 Responses API 不支持 `response_format` 参数），对 OpenAI 则使用原生 `response_format={"type": "json_object"}`

## 与前后实验的关系

本实验是第四章从"文本决策"迈向"GUI 感知"的关键一步：

| 实验 | 能力 | 与本实验的关系 |
|------|------|---------------|
| 实验 9（场景分析） | 消息分类 + 策略决策 | 本实验提取的消息文本 → 喂给实验 9 的分类器 |
| **实验 10（本实验）** | 截图分析 + 元素定位 | ← 当前实验 |
| 实验 11（GUI 操作） | 键鼠控制 + 操作规划 | 本实验定位的元素坐标 → 驱动实验 11 的键鼠操作 |
| 实验 12（综合实战） | 批量处理 + 质量评估 | 实验 9 + 10 + 11 串联为完整闭环 |

```
实验 10（本实验：感知层）
    │
    ├──→ 截图分析 → 消息文本 → 实验 9（决策层：分类 + 策略）
    │
    └──→ 元素定位 → 屏幕坐标 → 实验 11（执行层：键鼠操作）
```

## 实验流程

| 步骤 | 内容 | 预计时间 |
|------|------|----------|
| 1 | 阅读 `vlm/client.py`，理解 VLM 客户端双后端自适应机制和图片 base64 编码方式 | 10min |
| 2 | 阅读 `prompts/agents/eshop_service/vision/analyze.j2` 和 `locate.j2`，理解视觉提示词的设计模式（领域上下文注入 + Schema 注入） | 15min |
| 3 | 运行 `python main.py --image data/tests/screenshot.png --mode analyze`，观察 UI 区域识别和消息提取结果 | 15min |
| 4 | 运行 `python main.py --image data/tests/screenshot.png --mode locate --target "发送按钮"`，测试多种元素定位（如输入框、客户列表项、订单标签等） | 15min |
| 5 | 带 `--context` 参数指定领域上下文，对比有/无上下文时分析结果的差异，理解领域约束的作用 | 15min |
| 6 | 用自己的客服工作台截图替换测试截图，验证通用性；分析置信度低于预期的情况，思考优化方向 | 20min |
| 7 | （进阶）修改 `analyze.j2` 模板，增加对特定元素的识别要求（如"识别所有未读消息的红点标记"），观察 VLM 输出变化 | 20min |
| **合计** | | **2 学时** |
