# 实验 11：GUI 操作规划与键鼠控制

> 对应章节 4.3 手眼协调：操作规划与键鼠控制 ｜ 2 学时 ｜ ✅ 已完成

## 概述

本实验在实验 10（多模态视觉理解）的基础上，将 **VLM 视觉决策** 与 **键鼠操作执行** 结合，搭建完整的 GUI 自动化消息处理闭环。

核心思路：

```
浏览器截图 → VLM 看图决策（Function Calling）→ 键鼠工具执行
                 ↑                                    │
                 └────── 操作结果回传 ←─────────────────┘
                              (ReAct 循环)
```

VLM 作为"眼睛+大脑"，观察客服工作台截图，自主决定每一步操作（点击哪里、输入什么、是否滚动）；键鼠控制程序作为"手"，通过子进程调用执行实际操作。实验 10 解决了"怎么看"的问题，本实验解决"怎么做"——真正让智能体操控真实的浏览器界面。

> ⚠️ **前置要求**：本实验依赖实验 10 中的 VLM 客户端（`vlm/tool_vlm_client.py`）以及实验 9 中的分类器、策略引擎和回复生成器。运行前请确保已完成实验 9 和实验 10 的代码。

## 功能清单

| 功能 | 命令 | 说明 |
|------|------|------|
| 当前会话自动回复 | `python main.py` | 启动 ReAct 循环，处理工作台当前选中的客户会话 |
| 限制步数 | `python main.py --max-steps 20` | 设置最大操作步数，防止死循环 |
| 安静模式 | `python main.py --quiet` | 减少日志输出，仅显示关键信息 |

## 架构总览

```
┌─────────────────────────────────────────────────┐
│                  main.py (CLI 入口)               │
│  组装 LLM/VLM 客户端、PromptManager               │
│  分类器、策略引擎、回复生成器、GUIReplyAgent        │
└──────────────────────┬──────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────┐
│              GUIReplyAgent (编排器)               │
│  VLM 驱动的 ReAct 循环引擎                        │
│                                                   │
│  外层循环（每次截图一轮）：                         │
│    1. 定位浏览器窗口 (Window.find)                 │
│    2. 截取窗口截图 (Window.screenshot)             │
│    3. 内层 ReAct（VLM ↔ 工具 多轮交互）            │
│       ├─ VLM 看图 + 对话历史 → 工具调用             │
│       ├─ 执行工具 (click/type/scroll/clipboard)   │
│       └─ 结果回传 VLM → 继续决策                  │
│    4. VLM 输出纯文本 → 本轮结束，继续下一轮         │
└──────────────────────┬──────────────────────────┘
                       │
          ┌────────────┼────────────┐
          ▼            ▼            ▼
┌──────────────┐ ┌──────────┐ ┌────────────────────┐
│ ToolVLMClient│ │  Input   │ │ 回复流水线(继承自01) │
│ VLM+FC 调用   │ │ 键鼠操作  │ │ 分类→策略→生成回复  │
└──────┬───────┘ └────┬─────┘ └────────────────────┘
       │              │
       │    ┌─────────┴─────────┐
       │    │  tools CLI 子进程  │
       │    │  input / screenshot│
       │    └───────────────────┘
       │
   VLM API (DeepSeek/Qwen/OpenAI…)
```

## 文件结构

```
03-gui-automation/
├── config.yaml                    # LLM + VLM 配置（Pydantic v2 校验）
├── config.yaml.example            # 多厂商配置模板
├── requirements.txt               # 实验依赖
│
├── prompts/                       # Jinja2 提示词模板
│   └── agents/eshop_service/
│       ├── gui_reply_agent/
│       │   ├── system.j2           #   GUI 编排器系统提示词（动态注入工具 Schema）
│       │   └── extract_conversation.j2  # 对话提取专家提示词
│       ├── strategy_engine/        #   （继承自实验 9）
│       ├── message_classifier/     #   （继承自实验 9）
│       ├── reply_generator/        #   （继承自实验 9）
│       └── vision/                 #   （继承自实验 10）
│
├── src/                           # 核心代码
│   ├── main.py                    #   CLI 入口 — 组装编排器并启动 ReAct 循环
│   ├── config.py                  #   Pydantic v2 配置模型（LLM + VLM）
│   ├── vlm/
│   │   └── tool_vlm_client.py     #   VLM-FC 客户端（截图 + 工具调用）
│   ├── agents/eshop_service/
│   │   ├── gui_reply_agent.py     #   ★ GUI 编排器 — ReAct 循环引擎
│   │   └── tools/
│   │       ├── _base.py           #   子进程调用辅助（run_tool_cli）
│   │       ├── input.py           #   ★ 键鼠 + 剪贴板工具（Click/Type/Scroll/Clipboard）
│   │       ├── wait.py            #   等待工具
│   │       └── window.py          #   ★ 窗口查找 + 截图工具
│   └── inherit/                   #   继承代码（来自 01/02/前序章节）
│       ├── agents/eshop_service/
│       │   ├── message_category_manager.py
│       │   ├── message_classifier.py
│       │   ├── strategy_engine.py
│       │   └── reply_generator.py
│       ├── llm/
│       ├── prompt/
│       ├── tts/
│       └── utils/
│
├── data/                          # 数据文件
│   └── eshop_service/
│       └── message_category/      #   消息分类 JSON 配置（继承自实验 9）
│
├── tmp/                           # 运行时截图缓存
│
└── docs/                          # 文档
    ├── design.md                  #   当前实现对应的详细设计
    └── 教案讲课稿.md               #   教案式讲课稿
```

## 快速开始

### 1. 安装依赖

```bash
cd ch04-service-agent/03-gui-automation
pip install -r requirements.txt
```

依赖包：

| 包名 | 用途 |
|------|------|
| `openai` | LLM / VLM API 调用（兼容 DeepSeek / Qwen / 智谱 / OpenAI） |
| `PyYAML` | 解析 YAML 配置文件 |
| `pydantic` | 领域模型与配置校验（v2） |
| `jinja2` | 提示词模板渲染 |
| `Pillow` | 截图图片处理 |

此外，课程提供的 `tools/input` 和 `tools/screenshot` 模块各需安装 macOS 系统依赖：

```bash
# 键鼠模拟
pip install pynput

# 截图（macOS）
pip install mss pyobjc-framework-Quartz
```

### 2. macOS 系统权限

键鼠模拟和截图功能需要授予系统权限：

| 权限 | 路径 | 授予对象 |
|------|------|---------|
| **辅助功能**（键鼠） | 系统设置 → 隐私与安全性 → 辅助功能 | VS Code / 终端 |
| **屏幕录制**（截图） | 系统设置 → 隐私与安全性 → 屏幕录制 | VS Code / 终端 |

> 授予权限后**重启该应用**方生效。

### 3. 配置 LLM / VLM

```bash
cp config.yaml.example config.yaml
# 编辑 config.yaml，填写 llm 和 vlm 的 api_key_env
```

> ⚠️ `config.yaml` 已被 `.gitignore` 排除，不会提交到 Git。

### 4. 启动客服工作台

分别启动 `eshop-service-workbench` 的后端和前端：

```bash
# 终端一：后端
cd ch04-service-agent/eshop-service-workbench/backend
uvicorn main:app --reload --port 8000

# 终端二：前端
cd ch04-service-agent/eshop-service-workbench/frontend
npm run dev
```

用外部 Google Chrome 打开前端地址，确认标签页标题含“网店客服工作台”，并在运行前手动选中要处理的客户。程序只激活已打开的 Chrome 并严格查找该标题，不会自动新建标签页，也不会退化为操作任意 Chrome 窗口。

### 5. 运行

```bash
# 进入 src 目录运行
cd src
python main.py

# 限制最大步数
python main.py --max-steps 20

# 安静模式
python main.py --quiet
```

## 核心模块说明

### GUIReplyAgent — ReAct 循环编排器

```python
class GUIReplyAgent:
    """VLM 驱动的 GUI 自动化编排器。

    双层循环结构：
    - 外层：每轮截图一次 → 定位窗口 → 截取 → 进入内层
    - 内层：VLM 看图决策 → 调用工具 → 结果回传 → 继续，直到 VLM 输出纯文本
    """
    def run(self) -> str:
        while self._step_count < self._max_steps:
            # 1) 定位浏览器窗口
            self._current_window_info = self._window.find()
            # 2) 截图
            screenshot = self._window.screenshot(…)
            # 3) 内层 ReAct
            while self._step_count < self._max_steps:
                content, tool_calls = self._vlm.chat_with_image_and_tools(
                    image=screenshot.image, messages=messages, tools=tools
                )
                if not tool_calls:  # VLM 纯文本 → 本轮结束
                    return content
                for tc in tool_calls:
                    result = self._execute_tool(tc)  # 执行并做坐标转换
                    messages.append(tool_result)
```

### 操作原语（Function Calling 工具）

| 工具名 | 类型 | 描述 | 关键参数 |
|--------|------|------|---------|
| `click` | 鼠标 | 在截图坐标处点击左键 | `x`, `y`（截图相对坐标） |
| `type` | 键盘 | 在已聚焦的输入框中逐字键入 | `text`（要输入的文本） |
| `scroll` | 鼠标 | 滚动鼠标滚轮 | `dx`, `dy`（滚动量） |
| `clipboard_write` | 剪贴板 | 将文本写入系统剪贴板 | `text` |
| `clipboard_paste` | 剪贴板 | 在光标处粘贴剪贴板内容 | — |
| `generate_reply` | 业务 | 基于提取的沟通记录生成回复 | `messages`（对话记录列表） |

### 坐标转换机制

VLM 在截图上标注的坐标为**截图相对坐标**，需转换为**屏幕绝对坐标**才能操作：

```python
if name == "click":
    # 截图相对坐标 → 屏幕绝对坐标
    args["x"] = int(args["x"]) + window_info.x   # 加上窗口偏移
    args["y"] = int(args["y"]) + window_info.y
    # 归一化坐标 [0,999] → 实际像素
    args["x"] = round(args["x"] / 1000 * window_info.width)
    args["y"] = round(args["y"] / 1000 * window_info.height)
```

## 运行效果

以下为当前会话自动回复的典型输出。实际模型名称、窗口尺寸和坐标随本机配置与窗口状态变化。

```
🔌 LLM: deepseek/deepseek-v4-flash @ https://api.deepseek.com
🔌 VLM: deepseek/deepseek-v4-flash @ https://api.deepseek.com

============================================================
🚀 GUI 自动化编排器 启动 (VLM-FC Agent)
   VLM: deepseek-v4-flash (ToolVLM) @ deepseek
   最大步数: 50
   工具: ['click', 'type', 'scroll', 'clipboard_write', 'clipboard_paste', 'generate_reply']
============================================================
── Step 1 ──
✅ 已确认 Google Chrome 位于最前台，准备查找工作台窗口
✅ 找到 网店客服工作台 窗口: Google Chrome - 网店客服工作台 (1280x832 @ (100, 50))
📸 截图完成: 1280x832 → screenshot_1784822301948.png
  🔧 generate_reply → 亲，您好！😊 非常抱歉给您带来不便。关于您提到的退货退款问题…
  💬 收到沟通记录: 3 条
  ✏️ 生成回复: 亲，非常抱歉给您带来不便。关于您提到的退货退款问题...

📋 写入剪贴板: 亲，非常抱歉给您带来不便。关于您提到的退货退款问题...
🖱️  点击: (640, 720)
📋 已在光标处粘贴剪贴板内容
🖱️  点击: (1150, 720)
  🔎 发送动作已执行，等待页面更新后重新截图验证
── Step 2 ──
📸 截图完成: 1280x832 → screenshot_1784823115812.png
  ✅ 处理完成: 发送验证成功
```

## 操作原语演示

键鼠控制程序可通过 CLI 独立运行，便于调试和验证坐标。从 `ch04-service-agent/tools/` 目录下执行：

```bash
# 获取鼠标当前位置
PYTHONPATH=$PWD python -m input mouse pos

# 移动到指定坐标并点击
PYTHONPATH=$PWD python -m input mouse move --to 500 300 -d 0.15
PYTHONPATH=$PWD python -m input mouse click

# 滚轮滚动
PYTHONPATH=$PWD python -m input mouse scroll --dy -3      # 向上
PYTHONPATH=$PWD python -m input mouse scroll --dy 3       # 向下

# 键盘输入
PYTHONPATH=$PWD python -m input keyboard type "你好，这是测试文字"

# 剪贴板操作
PYTHONPATH=$PWD python -m input clipboard write "剪贴板测试文本"
PYTHONPATH=$PWD python -m input clipboard paste

# 截图 — 查看窗口列表
PYTHONPATH=$PWD python -m screenshot list-windows -f "客服"

# 截图 — 截取窗口
PYTHONPATH=$PWD python -m screenshot window -t "客服工作台"
```
