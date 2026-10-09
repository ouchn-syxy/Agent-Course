"""
网店客服模拟平台 — 后端入口。

提供以下 API：
- GET  /api/customers              客户列表（含最新消息摘要）
- GET  /api/customers/{id}         客户详情（个人信息 + 订单）
- GET  /api/chat/{customer_id}     聊天记录
- POST /api/chat/{customer_id}/send发送客服回复（触发 LLM 模拟客户回应）
- GET  /api/products               商品列表（支持 ?search=关键词）
- GET  /api/products/{id}          商品详情
- POST /api/reset                  重置所有会话

启动方式：
    cd backend
    uvicorn main:app --reload --port 8000
"""

import os
from contextlib import asynccontextmanager
from pathlib import Path

import yaml
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from src.llm_client import LLMClient
from src.chat_service import ChatService
from src.customer_simulator import CustomerSimulator
from src.product_service import ProductService


# ---------------------------------------------------------------------------
# 配置加载
# ---------------------------------------------------------------------------

def _load_config() -> dict:
    config_path = Path(__file__).parent / "config.yaml"
    if not config_path.exists():
        raise FileNotFoundError(
            "请复制 config.yaml.example 为 config.yaml 并填入你的 LLM 配置"
        )
    with open(config_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


# ---------------------------------------------------------------------------
# 全局服务实例（在 lifespan 中初始化）
# ---------------------------------------------------------------------------

chat_service: ChatService
product_service: ProductService
customer_simulator: CustomerSimulator
config: dict


@asynccontextmanager
async def lifespan(app: FastAPI):
    global chat_service, product_service, customer_simulator, config
    config = _load_config()

    # 初始化 LLM
    llm_cfg = config["llm"]
    llm = LLMClient(
        api_key=llm_cfg["api_key"],
        base_url=llm_cfg["base_url"],
        model=llm_cfg["model"],
        temperature=llm_cfg.get("temperature", 0.8),
        top_p=llm_cfg.get("top_p", 0.95),
        max_tokens=llm_cfg.get("max_tokens", 1024),
    )

    # 初始化服务
    chat_service = ChatService()
    product_service = ProductService()
    customer_simulator = CustomerSimulator(llm, chat_service)

    yield


app = FastAPI(title="网店客服模拟平台", lifespan=lifespan)

# CORS 允许前端开发服务器跨域
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# 请求/响应模型
# ---------------------------------------------------------------------------

class SendMessageRequest(BaseModel):
    content: str


# ---------------------------------------------------------------------------
# 客户相关 API
# ---------------------------------------------------------------------------

@app.get("/api/customers")
async def list_customers():
    """获取所有客户及其最新消息摘要。"""
    return chat_service.get_all_customers()


@app.get("/api/customers/{customer_id}")
async def get_customer(customer_id: str):
    """获取客户详情（个人信息 + 订单）。"""
    detail = chat_service.get_customer_detail(customer_id)
    if not detail:
        raise HTTPException(status_code=404, detail="客户不存在")
    return detail


# ---------------------------------------------------------------------------
# 聊天 API
# ---------------------------------------------------------------------------

@app.get("/api/chat/{customer_id}")
async def get_chat_history(customer_id: str):
    """获取与指定客户的聊天记录。"""
    session = chat_service.get_session(customer_id)
    if not session:
        raise HTTPException(status_code=404, detail="客户不存在")
    return {
        "customer_id": customer_id,
        "customer_name": session.customer["name"],
        "messages": chat_service.get_chat_history(customer_id),
    }


@app.post("/api/chat/{customer_id}/send")
async def send_message(customer_id: str, req: SendMessageRequest):
    """
    客服发送回复。

    流程：
    1. 保存客服消息
    2. 调用 LLM 生成客户的下一条消息（模拟消费者回复）
    3. 返回更新后的聊天记录
    """
    session = chat_service.get_session(customer_id)
    if not session:
        raise HTTPException(status_code=404, detail="客户不存在")

    # 保存客服消息
    chat_service.add_agent_message(customer_id, req.content)

    # LLM 模拟客户回复
    customer_reply = customer_simulator.generate_reply(customer_id)

    # 检查是否结束对话
    if customer_reply.endswith("[END]"):
        customer_reply = customer_reply.replace("[END]", "").strip()
        chat_service.mark_handled(customer_id, True)

    # 如果客户还有回复，保存它
    if customer_reply:
        chat_service.add_customer_message(customer_id, customer_reply)

    return {
        "customer_message": customer_reply,
        "messages": chat_service.get_chat_history(customer_id),
        "is_handled": session.is_handled,
    }


# ---------------------------------------------------------------------------
# 商品查询 API
# ---------------------------------------------------------------------------

@app.get("/api/products")
async def list_products(search: str = ""):
    """获取商品列表，支持关键词搜索。"""
    if search:
        return product_service.search(search)
    return product_service.list_all()


@app.get("/api/products/{product_id}")
async def get_product(product_id: str):
    """获取商品详情。"""
    product = product_service.get_by_id(product_id)
    if not product:
        raise HTTPException(status_code=404, detail="商品不存在")
    return product


@app.get("/api/products/{product_id}/stock")
async def check_product_stock(product_id: str, size: str, color: str):
    """核对指定商品、尺码和颜色组合是否可售。"""
    return product_service.check_stock(product_id, size, color)


# ---------------------------------------------------------------------------
# 重置 API
# ---------------------------------------------------------------------------

@app.post("/api/reset")
async def reset_all():
    """重置所有会话到初始状态。"""
    chat_service.reset()
    return {"status": "ok", "message": "所有会话已重置"}


# ---------------------------------------------------------------------------
# 静态文件服务（前端构建产物）
# ---------------------------------------------------------------------------

FRONTEND_DIST = Path(__file__).parent.parent / "frontend" / "dist"

if FRONTEND_DIST.exists():
    app.mount("/", StaticFiles(directory=str(FRONTEND_DIST), html=True), name="frontend")
