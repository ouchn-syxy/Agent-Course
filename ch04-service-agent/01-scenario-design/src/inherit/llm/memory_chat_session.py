"""
记忆感知对话引擎 —— 继承 ChatSession，覆写 send() 注入记忆上下文。

每轮 send() 调用自动完成：
  1. 从 ConversationMemory 获取含记忆上下文的 messages
  2. 追加当前用户消息，发送给 LLM
  3. 将本轮对话写入短期记忆，必要时触发压缩

用法：
    from llm.memory_chat_session import MemoryChatSession
    session = MemoryChatSession(llm, system_prompt="你是鲁迅…", memory=memory_manager)
    reply = session.send("我叫鲁迅")
"""

from __future__ import annotations

from pathlib import Path

from openai.types.chat import (
	ChatCompletionMessageParam,
	ChatCompletionSystemMessageParam,
	ChatCompletionUserMessageParam,
)

from inherit.llm.chat_session import ChatSession
from inherit.llm.client import LLMClient
from inherit.memory.conversation_memory import ConversationMemory


class MemoryChatSession(ChatSession):
	"""记忆感知对话会话 —— 继承 ChatSession，覆写 send() 注入记忆上下文。

	每轮 send() 调用自动完成：
	  1. 从 ConversationMemory 获取含记忆上下文的 messages
	  2. 追加当前用户消息，发送给 LLM
	  3. 将本轮对话写入短期记忆，必要时触发压缩

	继承自 ChatSession，复用其 turn_count / peek_last() / messages 等能力，
	覆写 send() 将"记忆读写"透明地织入对话流程。

	Attributes:
		_memory: 关联的 ConversationMemory 实例（可读写）。
	"""


	def __init__(self, llm: LLMClient, system_prompt: str, memory: ConversationMemory) -> None:
		"""
		Args:
			llm: 已初始化的 LLMClient 实例。
			system_prompt: 角色 system prompt 文本。
			memory: 已配置好的 ConversationMemory 实例。
		"""
		super().__init__(llm, system_prompt=system_prompt)
		self._memory: ConversationMemory = memory


	@property
	def memory(self) -> ConversationMemory:
		return self._memory


	def send(self, user_input: str) -> str:
		"""覆写父类 send()，注入记忆上下文后发送用户消息并返回 LLM 回复。

		调用方无需手动处理 get_messages / record_turn，
		本方法负责完整的"记忆注入 → LLM 生成 → 记忆更新"闭环。

		Args:
			user_input: 用户输入的文本。

		Returns:
			LLM 回复的文本内容。
		"""
		# 1. 构建角色 system prompt + 记忆层消息（替代父类直接用 self.messages）
		system_prompt: str = self._system_prompt
		messages: list[ChatCompletionMessageParam] = [
			ChatCompletionSystemMessageParam(role="system", content=system_prompt),
		]
		messages += self._memory.get_messages()
		messages.append(ChatCompletionUserMessageParam(role="user", content=user_input))

		# 2. 调用 LLM
		reply: str = self._llm.chat(messages)

		# 3. 更新记忆
		self._memory.record_turn(user_input, reply)

		return reply


	def reset(self) -> None:
		"""重置记忆（清空对话历史和摘要）。"""
		self._memory.reset()


if __name__ == "__main__":

	import tempfile

	from config import Config
	from inherit.prompt.prompt_manager import PromptManager
	from inherit.utils.path import get_prj_root

	# ── 1. 初始化 LLM（从 config.yaml 读取）──
	cfg: Config = Config.from_yaml()
	llm: LLMClient = LLMClient(
		api_key=cfg.llm.api_key_env,
		base_url=cfg.llm.base_url,
		model=cfg.llm.model,
		temperature=cfg.generation.temperature,
		top_p=cfg.generation.top_p,
		max_tokens=cfg.generation.max_tokens,
	)
	print("=" * 60)
	print("  MemoryChatSession 演示")
	print("=" * 60)
	print(f"  LLM: {llm.info()}")

	# ── 2. 初始化 ConversationMemory ──
	storage: Path = Path(tempfile.mkdtemp())
	pm: PromptManager = PromptManager(get_prj_root() / "prompts")
	memory: ConversationMemory = ConversationMemory(
		storage_dir=storage,
		session_id="demo-session",
		llm_client=llm,
		prompt_manager=pm,
		max_turns=2,  # 设小，方便演示压缩触发
		max_tokens=100,  # 设大，只靠轮数触发
	)

	# ── 3. __init__ → 创建会话 ──
	session: MemoryChatSession = MemoryChatSession(
		llm=llm,
		system_prompt="你是一个友好的助手，请用中文简短回答。",
		memory=memory,
	)
	print(f"\n✅ MemoryChatSession 已创建")
	print(f"   system_prompt: {session._system_prompt}")

	# ── 4. turn_count（继承自 ChatSession）──
	#    注：MemoryChatSession.send() 覆写了父类，消息走 ConversationMemory 而非父类 _messages。
	#    因此 session.turn_count 始终为 0，权威轮数见 memory.turn_count。
	print(f"\n📊 turn_count (会话层, 初始): {session.turn_count}")

	# ── 5. send() → 发送消息，自动读写记忆 ──
	print(f"\n📨 send('我叫张三，来自北京')")
	reply1: str = session.send("我叫张三，来自北京")
	print(f"   ↳ 回复: {reply1}")

	print(f"\n📨 send('我喜欢读鲁迅的作品')")
	reply2: str = session.send("我喜欢读鲁迅的作品")
	print(f"   ↳ 回复: {reply2}")

	# ── 6. peek_last()（继承自 ChatSession，查找父类 _messages）──
	print(f"\n👀 peek_last('assistant'): '{session.peek_last('assistant')}'（父类 _messages 为空）")
	print(f"👀 peek_last('user'):      '{session.peek_last('user')}'（父类 _messages 为空）")

	# ── 7. 继续对话，触发压缩（max_turns=2，第 3 轮溢出）──
	print(f"\n📨 send('你还记得我刚才说了什么吗？') [此轮将触发压缩]")
	reply3: str = session.send("你还记得我刚才说了什么吗？")
	print(f"   ↳ 回复: {reply3}")

	# ── 8. 查看记忆状态（ConversationMemory 层的权威数据）──
	print(f"\n📊 会话层 turn_count:   {session.turn_count}")
	print(f"📊 记忆层 turn_count:   {memory.turn_count}")
	print(f"📊 窗口轮数:           {memory.window_turn_count}")
	print(f"📊 estimated_tokens:   {memory.estimated_tokens}")
	summary: str | None = memory.summary
	print(f"📊 summary 存在:       {summary is not None}")
	if summary:
		print(f"   summary 预览:       {summary[:100]}...")

	# ── 9. visualize() ──
	print(f"\n{memory.visualize()}")

	# ── 10. get_messages() ──
	msgs: list[ChatCompletionMessageParam] = memory.get_messages()
	print(f"\n📋 get_messages() 返回 {len(msgs)} 条消息:")
	for i, msg in enumerate(msgs):
		role: str = str(msg["role"])
		content_preview: str = str(msg["content"])[:60]
		print(f"   [{i}] {role}: {content_preview}...")

	# ── 11. reset() → 同时清空 ConversationMemory ──
	session.reset()
	print(f"\n🔄 reset() 后 session.turn_count: {session.turn_count}")
	print(f"🔄 reset() 后 memory.turn_count: {memory.turn_count}")
	print(f"🔄 summary: {memory.summary}")
