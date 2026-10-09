"""
统一记忆管理器 —— 滑动窗口 + 摘要压缩 + Token 计数 + 文件持久化。

每轮对话后的处理流程：
1. 将本轮对话加入滑动窗口
2. 若超阈值（轮数或 token 数），触发 LLM 摘要压缩
3. 自动将当前状态落盘到 JSON 文件

用法：
    from memory.conversation_memory import ConversationMemory
    from inherit.prompt.prompt_manager import PromptManager

    pm = PromptManager("prompts")
    memory = ConversationMemory("data/memories", "luxun",
                       llm, pm, max_turns=20, max_tokens=3000)
    # 首次创建 session → 自动加载已有记忆文件
    # 每轮 record_turn → 自动落盘

    # 调用方负责构建 system_prompt（含摘要）
    system_prompt = pm.render("profile.j2", ...)
    messages = [{"role": "system", "content": system_prompt}] + memory.get_messages()
    messages.append({"role": "user", "content": user_input})
    reply = llm.chat(messages)
    memory.record_turn(user_input, reply)
    print(memory.visualize())
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from llm.token_counter import estimate_tokens
from openai.types.chat import ChatCompletionMessageParam, ChatCompletionSystemMessageParam, \
	ChatCompletionUserMessageParam, ChatCompletionAssistantMessageParam

from inherit.llm.client import LLMClient
from inherit.prompt.prompt_manager import PromptManager


class ConversationMemory:
	"""记忆管理器，封装滑动窗口 + LLM 摘要压缩 + 文件持久化。

	设计要点：
	  - 滑动窗口保留最近 N 轮完整对话（user + assistant 为一轮）
	  - 同时监控 token 占用，超过阈值也触发压缩
	  - 压缩时将旧对话发送给 LLM 生成结构化摘要
	  - record_turn() 在每轮 LLM 回复后调用，完成记忆更新并自动落盘
	  - summary 属性返回当前摘要（None 表示未压缩），由调用方渲染到 system prompt
	  - get_messages() 返回记忆层消息列表（摘要 + 窗口轮次），不含角色 system prompt
	  - visualize() 返回格式化的记忆状态面板字符串
	  - 支持按 session_id 持久化到 JSON 文件，构造时自动恢复已有记忆

	Attributes:
		_storage_path: 持久化文件完整路径（由 storage_dir + session_id 拼接）。
		_session_id: 会话标识符（如角色名），用于区分不同会话的持久化文件。
		_llm: LLMClient 实例，用于摘要压缩。
		_pm: PromptManager 实例，用于渲染压缩提示词模板。
		_max_turns: 滑动窗口最大保留轮数（每轮含 user + assistant 两条消息）。
		_max_tokens: 触发压缩的 token 阈值。
	"""


	def __init__(
			self,
			storage_dir: Path,
			session_id: str,
			llm_client: LLMClient,
			prompt_manager: PromptManager,
			max_turns: int = 20,
			max_tokens: int = 3000,
	) -> None:
		"""
		Args:
			storage_dir: 持久化文件存储目录。
			session_id: 会话标识符（如 "luxun"），用于文件持久化。
			llm_client: LLMClient 实例，用于摘要压缩。
			prompt_manager: PromptManager 实例，用于渲染压缩提示词模板（memory/conversation/compression.j2）。
			max_turns: 窗口最多保留的对话轮数（默认 20）。
			max_tokens: 触发压缩的 token 阈值（默认 3000）。
		"""
		self._session_id: str = session_id
		self._storage_path: Path = Path(storage_dir) / f"{session_id}.json"

		self._llm: LLMClient = llm_client
		self._pm: PromptManager = prompt_manager
		self._max_turns: int = max_turns
		self._max_tokens: int = max_tokens
		self._turns: list[ChatCompletionMessageParam] = []
		self._summary: str | None = None

		# 自动加载已有记忆
		if self._storage_path.exists():
			self._load_from_file()


	def record_turn(self, user_msg: str, assistant_msg: str) -> None:
		"""处理一轮对话：记录到滑动窗口 + 可能触发压缩 + 自动落盘。

		调用时机：每次 LLM 返回回复后立即调用。

		Args:
			user_msg: 用户消息。
			assistant_msg: 模型回复。
		"""
		self._turns.append(ChatCompletionUserMessageParam(role="user", content=user_msg))
		self._turns.append(ChatCompletionAssistantMessageParam(role="assistant", content=assistant_msg))

		if self.needs_compression():
			self._compress()

		self._save_to_file()


	# ---- 记忆摘要 ----

	@property
	def summary(self) -> str | None:
		"""压缩后的历史摘要文本，未压缩时为 None。"""
		return self._summary


	# ---- 消息构建 ----

	def get_messages(self) -> list[ChatCompletionMessageParam]:
		"""获取记忆层消息列表（摘要 + 窗口轮次），不含角色 system prompt。

		调用方需自行在列表头部插入角色 system prompt。

		结构：
			[0] system: 对话历史摘要（若有，由 memory/conversation/summary.j2 模板渲染）
			[1..N] 窗口内的 user/assistant 对话消息

		Returns:
			OpenAI messages 格式列表。
		"""
		messages: list[ChatCompletionMessageParam] = []

		if self._summary:
			content: str = self._pm.render("memory/conversation/summary.j2", summary=self._summary)
			messages.append(ChatCompletionSystemMessageParam(role="system", content=content))

		messages.extend(self._get_window_turns())
		return messages


	# ---- 滑动窗口 ----

	def _get_window_turns(self) -> list[ChatCompletionMessageParam]:
		"""获取当前窗口内的对话消息（最近 max_turns 轮）。"""
		max_msgs: int = self._max_turns * 2
		if len(self._turns) <= max_msgs:
			return list(self._turns)
		return self._turns[-max_msgs:]


	# ---- 状态查询 ----

	@property
	def turn_count(self) -> int:
		"""当前累积的总对话轮数（含窗口外的）。"""
		return len(self._turns) // 2


	@property
	def window_turn_count(self) -> int:
		"""当前窗口内的对话轮数。"""
		return min(self.turn_count, self._max_turns)


	@property
	def estimated_tokens(self) -> int:
		"""估算当前窗口内对话占用的 token 数（仅粗略估计，非精确值）。"""
		total: int = 0
		for msg in self._get_window_turns():
			total += estimate_tokens(msg["content"])
		if self._summary:
			total += estimate_tokens(self._summary)
		return total


	def needs_compression(self) -> bool:
		"""判断是否需要触发摘要压缩。"""
		return self.turn_count > self._max_turns or self.estimated_tokens > self._max_tokens


	# ---- 摘要压缩 ----

	def _compress(self) -> None:
		"""调用 LLM 将窗口外的旧对话压缩为结构化摘要。

		压缩策略：
		1. 取窗口之外的所有旧消息
		2. 将旧消息连同已有摘要直接传入 memory/conversation/compression.j2 模板
		3. 将 LLM 返回的摘要存入 self._summary
		4. 清空旧消息，仅保留窗口内的消息
		"""
		if self.turn_count > self._max_turns:
			max_msgs: int = self._max_turns * 2
			old_turns: list[ChatCompletionMessageParam] = self._turns[:-max_msgs]
			self._turns = self._turns[-max_msgs:]
		else:
			old_turns: list[ChatCompletionMessageParam] = list(self._turns)
			self._turns = []

		if not old_turns:
			return

		compression_prompt: str = self._pm.render(
			"memory/conversation/compression.j2",
			summary=self._summary,
			old_turns=old_turns,
		)

		messages: list[ChatCompletionMessageParam] = [
			ChatCompletionSystemMessageParam(role="system", content=""),
			ChatCompletionUserMessageParam(role="user", content=compression_prompt)
		]

		self._summary = self._llm.chat(messages, temperature=0.3, max_tokens=800)


	# ---- 可视化 ----

	def visualize(self) -> str:
		"""生成记忆面板可视化字符串，展示当前记忆状态。

		Returns:
			格式化的记忆面板字符串。
		"""
		lines: list[str] = [
			"=" * 60,
			"  记忆面板",
			"=" * 60,
			f"[记忆] 已记录 {self.turn_count} 轮对话，窗口内约 {self.estimated_tokens} tokens",
		]

		if self._summary:
			summary_preview: str = (
				self._summary[:80] + "..."
				if len(self._summary) > 80
				else self._summary
			)
			lines.append(f"  状态: 已压缩 | 摘要预览: {summary_preview}")
		else:
			lines.append("  状态: 未触发压缩")

		lines.append("=" * 60)
		return "\n".join(lines)


	# ---- 重置 ----

	def reset(self) -> None:
		"""重置记忆（清空对话历史和摘要，并删除持久化文件）。"""
		self._turns = []
		self._summary = None
		if self._storage_path.exists():
			self._storage_path.unlink()


	# ---- 持久化 ----

	@property
	def session_id(self) -> str:
		"""会话标识符。"""
		return self._session_id


	@property
	def storage_path(self) -> Path:
		"""持久化文件路径。"""
		return self._storage_path


	def _save_to_file(self) -> None:
		"""将当前记忆状态落盘为 JSON 文件。"""
		self._storage_path.parent.mkdir(parents=True, exist_ok=True)
		data: dict[str, Any] = {
			"turns": [dict(msg) for msg in self._turns],
			"summary": self._summary,
		}
		self._storage_path.write_text(json.dumps(data, ensure_ascii=False, indent=4), encoding="utf-8")


	def _load_from_file(self) -> None:
		"""从 JSON 文件恢复记忆状态。文件不存在时静默跳过。"""
		if not self._storage_path.exists():
			return
		with open(self._storage_path, encoding="utf-8") as f:
			data: dict[str, Any] = json.load(f)
		self._turns = [
			ChatCompletionUserMessageParam(role=t["role"], content=t["content"])
			if t["role"] == "user"
			else ChatCompletionAssistantMessageParam(role=t["role"], content=t["content"])
			for t in data.get("turns", [])
		]
		self._summary = data.get("summary")


if __name__ == "__main__":

	import tempfile

	from config import Config
	from inherit.utils.path import get_prj_root

	# ── 1. 初始化 LLM ──
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
	print("  ConversationMemory 演示（含持久化）")
	print("=" * 60)
	print(f"  LLM: {llm.info()}")

	# ── 2. __init__（带 session_id + storage_dir）──
	pm: PromptManager = PromptManager(get_prj_root() / "prompts")
	storage: Path = Path(tempfile.mkdtemp())
	memory: ConversationMemory = ConversationMemory(
		storage_dir=storage,
		session_id="demo-session",
		llm_client=llm,
		prompt_manager=pm,
		max_turns=2,
		max_tokens=99999,
	)
	print(f"\n✅ ConversationMemory 已创建")
	print(f"   session_id:    {memory.session_id}")
	print(f"   storage_path:  {memory.storage_path}")
	print(f"   max_turns:     {memory._max_turns}")
	print(f"   max_tokens:    {memory._max_tokens}")

	# ── 3. 初始状态 ──
	print(f"\n📊 初始状态:")
	print(f"   turn_count:        {memory.turn_count}")
	print(f"   window_turn_count: {memory.window_turn_count}")
	print(f"   estimated_tokens:  {memory.estimated_tokens}")
	print(f"   needs_compression: {memory.needs_compression()}")
	print(f"   summary:           {memory.summary}")

	# ── 4. record_turn() → 记录对话 + 自动落盘 ──
	print(f"\n📝 record_turn('我叫张三，来自北京', '你好张三！北京是个好地方。')")
	memory.record_turn("我叫张三，来自北京", "你好张三！北京是个好地方。")

	print(f"\n📊 第 1 轮后:")
	print(f"   turn_count:        {memory.turn_count}")
	print(f"   persistence_file:  {'✅ 存在' if memory.storage_path.exists() else '❌ 不存在'}")

	# ── 5. 再记录一轮 ──
	print(f"\n📝 record_turn('我喜欢读鲁迅', '鲁迅是伟大的文学家，他的作品值得细读。')")
	memory.record_turn("我喜欢读鲁迅", "鲁迅是伟大的文学家，他的作品值得细读。")

	print(f"\n📊 第 2 轮后:")
	print(f"   turn_count:        {memory.turn_count}")
	print(f"   window_turn_count: {memory.window_turn_count}")

	# ── 6. 第 3 轮 → 触发压缩（超出 max_turns=2）──
	print(f"\n📝 record_turn('我最近在读《呐喊》', '《呐喊》是鲁迅的经典作品集。') [触发压缩]")
	memory.record_turn("我最近在读《呐喊》", "《呐喊》是鲁迅的经典作品集。")

	# ── 7. 压缩后状态 ──
	print(f"\n📊 压缩后:")
	print(f"   turn_count:        {memory.turn_count}")
	print(f"   window_turn_count: {memory.window_turn_count}")
	print(f"   estimated_tokens:  {memory.estimated_tokens}")
	print(f"   needs_compression: {memory.needs_compression()}")
	print(f"   summary 存在:      {memory.summary is not None}")
	if memory.summary:
		print(f"   summary:           {memory.summary[:120]}...")

	# ── 8. 验证持久化文件内容 ──
	print(f"\n💾 持久化文件内容:")
	if memory.storage_path.exists():
		saved: dict[str, Any] = json.loads(memory.storage_path.read_text(encoding="utf-8"))
		print(f"   session_id:  {saved.get('session_id')}")
		print(f"   turns 数量:  {len(saved.get('turns', []))}")
		print(f"   has_summary: {saved.get('summary') is not None}")

	# ── 9. 模拟重启：新建 ConversationMemory 自动加载 ──
	print(f"\n🔄 模拟重启（新建 ConversationMemory 自动加载持久化文件）...")
	memory2: ConversationMemory = ConversationMemory(
		storage_dir=storage,
		session_id="demo-session",
		llm_client=llm,
		prompt_manager=pm,
		max_turns=2,
		max_tokens=99999,
	)
	print(f"   memory2.turn_count:  {memory2.turn_count}")
	print(f"   memory2.summary:     {'存在' if memory2.summary else 'None'}")

	# ── 10. get_messages() ──
	msgs: list[ChatCompletionMessageParam] = memory.get_messages()
	print(f"\n📋 get_messages() 返回 {len(msgs)} 条消息:")
	for i, msg in enumerate(msgs):
		role: str = str(msg["role"])
		content_preview: str = str(msg["content"])[:60]
		print(f"   [{i}] {role}: {content_preview}...")

	# ── 11. visualize() ──
	print(f"\n{memory.visualize()}")

	# ── 12. reset() ──
	memory.reset()
	print(f"\n🔄 reset() 后:")
	print(f"   turn_count:       {memory.turn_count}")
	print(f"   persistence_file: {'❌ 已删除' if not memory.storage_path.exists() else '⚠️ 仍存在'}")
