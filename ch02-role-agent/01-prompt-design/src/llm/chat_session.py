"""
对话引擎 —— 管理多轮对话的 messages 列表与 LLM 交互。

职责单一：维护 messages 列表的增删改查，不涉及 prompt 构建或评估逻辑。

用法：
    from chat import ChatSession
    session = ChatSession(llm_client, system_prompt="...")
    reply = session.send("你好")
"""

from typing import Optional

from llm.client import LLMClient
from openai.types.chat import (
	ChatCompletionAssistantMessageParam,
	ChatCompletionMessageParam,
	ChatCompletionSystemMessageParam,
	ChatCompletionUserMessageParam,
)


class ChatSession:
	"""
	一次多轮对话会话，维护 system + user + assistant 消息列表。

	设计要点：
	  - messages 列表公开可读（方便调试），但推荐通过 send() 方法追加
	  - send() 自动将 model reply 追加到 messages，保持列表完整
	  - reset() 不清除 LLM 连接，只清空对话历史
	"""


	def __init__(self, llm: LLMClient, system_prompt: str) -> None:
		"""
		Args:
			llm: 已初始化的 LLMClient 实例。
			system_prompt: 由 PromptManager.render() 生成的 system prompt。
		"""
		self._llm: LLMClient = llm
		self.messages: list[ChatCompletionMessageParam] = [
			ChatCompletionSystemMessageParam(role="system", content=system_prompt)
		]


	@property
	def llm(self) -> LLMClient:
		return self._llm


	def send(self, user_input: str) -> str:
		"""
		发送一轮用户消息并获取模型回复。

		同时将 user 消息和 assistant 回复追加到 messages 列表，
		保证后续调用能继承完整对话历史。

		Args:
			user_input: 用户输入的文本。

		Returns:
			模型回复的文本内容。
		"""
		self.messages.append(
			ChatCompletionUserMessageParam(role="user", content=user_input)
		)
		reply: str = self._llm.chat(self.messages)
		self.messages.append(
			ChatCompletionAssistantMessageParam(role="assistant", content=reply)
		)
		return reply


	@property
	def turn_count(self) -> int:
		"""已进行的对话轮数（一轮 = 一次 user + 一次 assistant）。"""
		return sum(1 for m in self.messages if m["role"] == "user")


	def peek_last(self, role: str = "assistant") -> str:
		"""
		获取最近一条指定角色的消息内容，不影响 messages 列表。

		Args:
			role: 消息角色（"system" / "user" / "assistant"），默认 "assistant"。

		Returns:
			找到的消息内容，若未找到则返回空字符串。
		"""
		# 从末尾向前遍历，保证 O(1) 在大多数情况下（最后一条即目标角色）
		for m in reversed(self.messages):
			if m["role"] == role:
				return m["content"]
		return ""


	def reset(self, system_prompt: Optional[str] = None) -> None:
		"""
		重置对话历史，保留 LLM 连接。

		Args:
			system_prompt: 新的 system prompt。为 None 时沿用原来的。
		"""
		new_system: str = system_prompt if system_prompt is not None else self.messages[0]["content"]
		self.messages = [
			ChatCompletionSystemMessageParam(role="system", content=new_system)
		]


if __name__ == "__main__":
	from config import Config

	cfg: Config = Config.from_yaml()
	llm = LLMClient(
		api_key=cfg.llm.api_key_env,
		base_url=cfg.llm.base_url,
		model=cfg.llm.model,
		temperature=cfg.generation.temperature,
		top_p=cfg.generation.top_p,
		max_tokens=cfg.generation.max_tokens,
	)

	# ── __init__ ──
	session = ChatSession(llm, system_prompt="你是一个助手，请用中文简短回答。")
	print(f"初始化完成，LLM: {llm.info()}")
	print(f"system prompt: {session.messages[0]['content']}")

	# ── send ──
	reply1 = session.send("你好，我叫小明")
	print(f"\nsend('你好，我叫小明') =>\n{reply1}")

	# ── turn_count ──
	print(f"\nturn_count: {session.turn_count}")

	# ── peek_last ──
	last_user = session.peek_last("user")
	last_assistant = session.peek_last("assistant")
	print(f"peek_last('user') => {last_user}")
	print(f"peek_last('assistant') => {last_assistant}")

	# ── send 第二轮（验证多轮上下文继承）──
	reply2 = session.send("我叫什么名字？")
	print(f"\nsend('我叫什么名字？') =>\n{reply2}")
	print(f"turn_count: {session.turn_count}")

	# ── reset ──
	session.reset("你是一个诗人，请用中文回答。")
	print(f"\nreset 后 messages 长度: {len(session.messages)}")
	print(f"reset 后 system prompt: {session.messages[0]['content']}")
	print(f"reset 后 turn_count: {session.turn_count}")
	reply3 = session.send("写一句关于秋天的诗")
	print(f"\nsend('写一句关于秋天的诗') =>\n{reply3}")

	print("\n✅ ChatSession 全部方法演示完成")
	print(f"reset 后 messages 长度: {len(session.messages)}")
	print(f"reset 后 system prompt: {session.messages[0]['content']}")
	print(f"reset 后 turn_count: {session.turn_count}")

	print("\n✅ ChatSession 全部方法演示完成")
