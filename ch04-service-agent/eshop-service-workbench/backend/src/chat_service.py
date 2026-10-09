"""
聊天状态管理服务。

在内存中维护所有客户会话的聊天记录。
"""

import json
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


@dataclass
class Message:
    """单条聊天消息。"""

    id: str
    sender: str  # "customer" | "agent"
    content: str
    timestamp: str
    customer_id: str


@dataclass
class CustomerSession:
    """单个客户的会话状态。"""

    customer_id: str
    customer: dict  # 来自 customers.json 的原始数据
    messages: list[Message] = field(default_factory=list)
    is_handled: bool = False  # 是否已处理完毕
    need_human: bool = False  # 是否需要转人工


class ChatService:
    """聊天状态管理服务（内存存储）。"""

    def __init__(self, data_path: Optional[Path] = None) -> None:
        if data_path is None:
            data_path = Path(__file__).parent.parent / "data" / "customers.json"
        with open(data_path, "r", encoding="utf-8") as f:
            self._customers: list[dict] = json.load(f)

        # customer_id → CustomerSession
        self._sessions: dict[str, CustomerSession] = {}

        self._init_sessions()

    def _init_sessions(self) -> None:
        """初始化所有客户会话，插入初始消息。"""
        for cust in self._customers:
            session = CustomerSession(
                customer_id=cust["id"],
                customer=cust,
            )
            # 插入客户的首条消息
            initial_msg = Message(
                id=str(uuid.uuid4()),
                sender="customer",
                content=cust["initial_message"],
                timestamp=self._now(),
                customer_id=cust["id"],
            )
            session.messages.append(initial_msg)
            self._sessions[cust["id"]] = session

    @staticmethod
    def _now() -> str:
        return time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())

    def get_all_customers(self) -> list[dict]:
        """获取所有客户及其最新消息摘要。"""
        result: list[dict] = []
        for session in self._sessions.values():
            last_msg = session.messages[-1] if session.messages else None
            unread_count = sum(
                1 for m in session.messages if m.sender == "customer"
            )
            # 只返回有 agent 回复过的才算已处理；否则统计所有 customer 消息
            has_agent_reply = any(m.sender == "agent" for m in session.messages)
            if has_agent_reply:
                unread_count = 0
            result.append({
                "id": session.customer_id,
                "name": session.customer["name"],
                "avatar": session.customer["avatar"],
                "level": session.customer["level"],
                "last_message": last_msg.content[:50] if last_msg else "",
                "last_message_time": last_msg.timestamp if last_msg else "",
                "last_sender": last_msg.sender if last_msg else "",
                "unread_count": unread_count,
                "is_handled": session.is_handled,
                "need_human": session.need_human,
            })
        return result

    def get_customer_detail(self, customer_id: str) -> Optional[dict]:
        """获取客户详情（含个人信息和订单）。"""
        session = self._sessions.get(customer_id)
        if not session:
            return None
        return session.customer

    def get_chat_history(self, customer_id: str) -> list[dict]:
        """获取与某客户的完整聊天记录。"""
        session = self._sessions.get(customer_id)
        if not session:
            return []
        return [
            {
                "id": m.id,
                "sender": m.sender,
                "content": m.content,
                "timestamp": m.timestamp,
            }
            for m in session.messages
        ]

    def add_agent_message(self, customer_id: str, content: str) -> dict:
        """添加客服回复消息。"""
        session = self._sessions.get(customer_id)
        if not session:
            raise ValueError(f"客户不存在: {customer_id}")

        msg = Message(
            id=str(uuid.uuid4()),
            sender="agent",
            content=content,
            timestamp=self._now(),
            customer_id=customer_id,
        )
        session.messages.append(msg)
        return {
            "id": msg.id,
            "sender": msg.sender,
            "content": msg.content,
            "timestamp": msg.timestamp,
        }

    def add_customer_message(self, customer_id: str, content: str) -> dict:
        """添加客户消息（由 LLM 模拟生成）。"""
        session = self._sessions.get(customer_id)
        if not session:
            raise ValueError(f"客户不存在: {customer_id}")

        msg = Message(
            id=str(uuid.uuid4()),
            sender="customer",
            content=content,
            timestamp=self._now(),
            customer_id=customer_id,
        )
        session.messages.append(msg)
        return {
            "id": msg.id,
            "sender": msg.sender,
            "content": msg.content,
            "timestamp": msg.timestamp,
        }

    def mark_handled(self, customer_id: str, handled: bool = True) -> None:
        """标记客户会话为已处理/未处理。"""
        session = self._sessions.get(customer_id)
        if session:
            session.is_handled = handled

    def mark_need_human(self, customer_id: str, need: bool = True) -> None:
        """标记是否需要转人工。"""
        session = self._sessions.get(customer_id)
        if session:
            session.need_human = need

    def get_session(self, customer_id: str) -> Optional[CustomerSession]:
        """获取原始会话对象（供 simulator 使用）。"""
        return self._sessions.get(customer_id)

    def reset(self) -> None:
        """重置所有会话到初始状态。"""
        self._sessions.clear()
        self._init_sessions()
