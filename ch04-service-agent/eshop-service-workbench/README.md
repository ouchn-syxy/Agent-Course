# 网店客服模拟平台

> 对应章节 4.x 网店客服智能体 ｜ 模拟平台基础设施 ｜ ✅ 已完成

## 概述

本平台为第四章「网店客服智能体」课程提供**可交互的模拟客服环境**。

平台由一个预设的虚拟网店支撑，包含 **8 位不同人设的客户**（售前咨询、售后投诉、换货、垃圾广告等）和 **12 款真实商品**（含详细描述和售后政策）。客服发送消息后，后端调用 LLM 以客户的身份自动生成自然回复，形成完整的多轮对话闭环。

技术栈：

```
Vue 3 + TypeScript（客服工作台 UI）
        ↕ REST API
FastAPI + Uvicorn（后端服务）
        ↕ OpenAI SDK
LLM（DeepSeek / Qwen / 智谱 / OpenAI 均可）
```

## 功能清单

| 功能 | 说明 |
|------|------|
| 客户列表 | 展示 8 位客户，含头像、会员等级、最新消息摘要、已处理标记 |
| 多轮聊天 | 选择客户进入对话，文本输入框支持 Enter 发送 / Shift+Enter 换行 |
| 乐观更新 | 客服消息发送后立即显示，无需等 LLM 回复 |
| LLM 模拟客户 | 后端根据客户 persona 自动生成符合人设的自然语言回复 |
| 对话结束检测 | 客户消息含 `[END]` 时自动标记为已处理 |
| 客户详情 & 订单 | 右侧面板展示客户个人信息和历史订单 |
| 商品搜索 | 按名称/分类/描述/售后政策搜索商品，展示完整详情 |
| 一键重置 | 清空所有会话恢复初始状态 |

## 文件结构

```
eshop-service-workbench/
├── API.md                        # API 接口文档（7 个端点完整说明）
├── README.md                     # 本文件
│
├── backend/                      # 后端 — FastAPI
│   ├── config.yaml               # LLM 配置（API Key、模型、生成参数）
│   ├── config.yaml.example       # LLM 配置参照（复制并填入密钥）
│   ├── requirements.txt          # Python 依赖
│   ├── main.py                   # FastAPI 入口（lifespan 初始化 + 8 个路由）
│   ├── data/                     #   预设数据
│   │   ├── customers.json        #     8 位客户（含 persona、订单、首条消息）
│   │   └── products.json         #     12 款商品（含详细描述、保修、退换、提示）
│   └── src/                      #   核心模块
│       ├── llm_client.py         #     OpenAI SDK 封装（chat 方法）
│       ├── chat_service.py       #     聊天会话管理（内存存储）
│       ├── customer_simulator.py #     LLM 模拟客户回复（persona → message）
│       └── product_service.py    #     商品查询服务（搜索含售后字段）
│
└── frontend/                     # 前端 — Vue 3 + TypeScript + Vite
    ├── index.html                #   SPA 入口
    ├── package.json              #   依赖 & 脚本
    ├── vite.config.ts            #   Vite 配置（proxy /api → localhost:8000）
    └── src/
        ├── main.ts               #   Vue 应用入口
        ├── App.vue               #   根组件（三栏布局 + 乐观更新逻辑）
        ├── style.css             #   全局样式（inter 字体 + reset）
        ├── api/
        │   └── index.ts          #   全部 API 调用封装
        ├── types/
        │   └── index.ts          #   TypeScript 类型（Customer, Product, ChatMessage 等）
        └── components/
            ├── CustomerList.vue      # 左侧客户列表
            ├── ChatWindow.vue        # 中间聊天窗口（自动滚动）
            ├── ChatInput.vue         # 底部消息输入框（固定在页面底部）
            └── CustomerInfoPanel.vue  # 右侧客户信息 + 商品搜索面板
```

## 快速开始

### 1. 安装依赖

```bash
# 后端
cd ch04-service-agent/eshop-service-workbench/backend
pip install -r requirements.txt

# 前端
cd ../frontend
npm install
```

后端依赖：

| 包名 | 用途 |
|------|------|
| `openai` | LLM API 调用（兼容 DeepSeek / Qwen / 智谱 / OpenAI） |
| `PyYAML` | 解析 `config.yaml` 配置文件 |
| `fastapi` | Web 框架 |
| `uvicorn[standard]` | ASGI 服务器 |
| `pydantic` | 请求/响应模型校验 |

前端依赖：

| 包名 | 用途 |
|------|------|
| `vue` | UI 框架 |
| `typescript` | 类型检查 |
| `vite` | 构建工具 |
| `vue-tsc` | Vue TypeScript 编译器 |

### 2. 配置 LLM

```bash
cd ch04-service-agent/eshop-service-workbench/backend
cp config.yaml.example config.yaml
# 编辑 config.yaml，填入 api_key
# 如需切换模型，修改 provider、base_url、model 字段
```

> ⚠️ `config.yaml` 已被 `.gitignore` 排除，不会提交到 Git。

配置示例：

```yaml
llm:
  provider: "deepseek"
  base_url: "https://api.deepseek.com"
  model: "deepseek-v4-flash"
  api_key: "sk-..."
  temperature: 0.9
  top_p: 0.95
  max_tokens: 1024
```

### 3. 启动

```bash
# 终端 1 — 启动后端（端口 8000）
cd ch04-service-agent/eshop-service-workbench/backend
uvicorn main:app --reload --port 8000

# 终端 2 — 启动前端开发服务器（端口 5173）
cd ch04-service-agent/eshop-service-workbench/frontend
npm run dev
```

浏览器打开 `http://localhost:5173` 即可使用。

> 前端开发服务器会自动将 `/api` 请求代理到后端 8000 端口，详见 `vite.config.ts`。

## 客户人设

| 客户 | 类型 | 特点 |
|------|------|------|
| 👩 张三 | 售前咨询 | VIP 会员，对连衣裙尺码和库存有疑问，语气友善 |
| 👨 李四 | 售后投诉 | 普通会员，跑鞋开胶要求退货退款 |
| 👩‍🦰 王五 | 投诉 | VIP 会员，羽绒服污渍 + 钻绒，情绪激动 |
| 👩‍💼 赵六 | 售前咨询 | 新用户，想买衬衫和休闲裤，询问搭配和库存 |
| 👨‍💼 钱七 | 换货 | 普通会员，衬衫 XL 换 L，询问换货运费 |
| 🤖 孙八 | 垃圾广告 | 新用户，发布微信号引流，不理会客服回复 |
| 👩 周九 | 复购 | VIP 会员，T恤回购 + 询问新品手提包 |
| 👨 吴十 | 物流查询 | 普通会员，查询订单物流不更新问题 |

## 商品概览

| ID | 名称 | 分类 | 价格 | 库存 |
|----|------|------|------|------|
| P001 | 红色连衣裙 | 女装 | ¥299 | 50 |
| P002 | 白色衬衫 | 女装 | ¥199 | 120 |
| P003 | 黑色休闲裤 | 女装 | ¥259 | 80 |
| P004 | 蓝色牛仔裤 | 女装 | ¥329 | 65 |
| P005 | 运动跑鞋 | 鞋履 | ¥459 | 35 |
| P006 | 羊绒围巾 | 配饰 | ¥189 | 150 |
| P007 | 皮质手提包 | 箱包 | ¥599 | 20 |
| P008 | 太阳镜 | 配饰 | ¥159 | 200 |
| P009 | 纯棉T恤 | 女装 | ¥99 | 300 |
| P010 | 羽绒服 | 女装 | ¥899 | 15 |
| P011 | 真丝睡衣 | 内衣家居 | ¥269 | 45 |
| P012 | 牛皮皮带 | 配饰 | ¥239 | 90 |

> 每款商品均包含详尽的描述信息（面料成分、版型、尺码参考、洗涤保养）以及售后三要素（保修政策、退换规则、使用提示）。详见 `backend/data/products.json` 或右侧面板「商品搜索」功能。

## 技术架构

```
                    ┌──────────────────────────┐
                    │   客服工作台 (Browser)     │
                    │   Vue 3 + TypeScript      │
                    │   localhost:5173           │
                    └────────────┬─────────────┘
                                 │ REST API
                                 │ (proxy /api → :8000)
                    ┌────────────▼─────────────┐
                    │   后端服务 (FastAPI)       │
                    │   localhost:8000           │
                    │                            │
                    │  ┌──────────────────────┐ │
                    │  │ ChatService          │ │
                    │  │ (内存会话管理)        │ │
                    │  └──────────┬───────────┘ │
                    │             │              │
                    │  ┌──────────▼───────────┐ │
                    │  │ CustomerSimulator    │ │
                    │  │ (LLM 模拟客户)        │ │
                    │  └──────────┬───────────┘ │
                    │             │              │
                    │  ┌──────────▼───────────┐ │
                    │  │ ProductService       │ │
                    │  │ (商品查询)            │ │
                    │  └──────────────────────┘ │
                    └────────────┬─────────────┘
                                 │ OpenAI SDK
                    ┌────────────▼─────────────┐
                    │   LLM API                 │
                    │   (DeepSeek / Qwen / …)   │
                    └──────────────────────────┘
```

### 消息流转

```
1. 客服在 UI 输入消息 → 前端乐观更新（立即显示）
2. POST /api/chat/{id}/send → 后端保存客服消息
3. CustomerSimulator 构建 system prompt（角色名 + 订单 + persona）
4. 拼接完整对话历史 → 调用 LLM
5. LLM 返回客户回复 → 后端保存 → 返回完整消息列表
6. 前端替换消息列表 + 自动滚动到底部
```

### API 端点

| 方法 | 路径 | 说明 |
|------|------|------|
| `GET` | `/api/customers` | 客户列表（含最新消息摘要） |
| `GET` | `/api/customers/{id}` | 客户详情（个人信息 + 订单） |
| `GET` | `/api/chat/{customer_id}` | 聊天记录 |
| `POST` | `/api/chat/{customer_id}/send` | 发送客服消息（触发 LLM 模拟客户回复） |
| `GET` | `/api/products` | 商品列表（支持 `?search=关键词`） |
| `GET` | `/api/products/{id}` | 商品详情 |
| `POST` | `/api/reset` | 重置所有会话 |

> 完整接口文档见 [API.md](./API.md)。
