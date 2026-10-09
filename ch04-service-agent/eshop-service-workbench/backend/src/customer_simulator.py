"""
客户模拟器。

使用 LLM 模拟消费者角色，根据预设的人物设定和对话历史，
生成自然的下一条客户消息。
"""

from src.llm_client import LLMClient
from src.chat_service import ChatService, CustomerSession

CUSTOMER_SIMULATOR_SYSTEM_PROMPT = """你正在模拟一个电商平台的消费者，在与客服进行聊天。

你的角色设定如下：
- 姓名：{name}
- 会员等级：{level}
- 历史订单：{orders}
- 人物特点：{persona}

规则：
1. 你必须始终以消费者的身份说话，不要跳出角色。
2. 你的回复要符合角色设定和情绪状态，保持一致性。
3. 回复应该自然、口语化，像是在手机上和客服聊天。
4. 每次回复控制在 1-3 句话，不要太长。
5. 如果客服已经解决了你的问题，可以表示感谢并结束对话。此时回复末尾加上 [END]。
6. 如果客服的回复让你满意，不要继续纠缠。如果真的解决了问题就说谢谢。
7. 如果你是投诉客户，初始会比较激动，但如果客服态度好并给出解决方案，情绪应该逐渐缓和。
8. 如果你是垃圾消息发送者，继续发广告内容，不理会客服的回复。

请根据以上设定和对话历史，生成你的下一条回复。只输出回复内容本身，不要加任何前缀或说明。"""


class CustomerSimulator:
    """使用 LLM 模拟客户回复。"""

    def __init__(self, llm: LLMClient, chat_service: ChatService) -> None:
        self._llm = llm
        self._chat_service = chat_service

    def generate_reply(self, customer_id: str) -> str:
        """根据对话历史生成客户的下一条回复。"""
        session = self._chat_service.get_session(customer_id)
        if not session:
            return ""

        cust = session.customer

        # 格式化订单信息
        orders_text = "无历史订单"
        if cust.get("orders"):
            order_lines: list[str] = []
            for o in cust["orders"]:
                items = ", ".join(
                    f"{it['product_name']}×{it['quantity']}"
                    for it in o["items"]
                )
                order_lines.append(
                    f"  - 订单{o['order_id']}（{o['date']}，{o['status']}）: {items}，共¥{o['total']}"
                )
            orders_text = "\n".join(order_lines)

        system_prompt = CUSTOMER_SIMULATOR_SYSTEM_PROMPT.format(
            name=cust["name"],
            level=cust["level"],
            orders=orders_text,
            persona=cust["persona"],
        )

        # 构建消息历史
        messages: list[dict] = [{"role": "system", "content": system_prompt}]
        for msg in session.messages:
            role = "assistant" if msg.sender == "customer" else "user"
            messages.append({"role": role, "content": msg.content})

        # 调用 LLM 生成回复
        reply = self._llm.chat(messages, temperature=0.9, max_tokens=256)
        return reply.strip()
