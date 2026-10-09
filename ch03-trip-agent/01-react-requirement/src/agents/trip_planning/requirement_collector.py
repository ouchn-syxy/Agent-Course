"""ReAct 循环引擎 — 驱动 Thought → Action → Observation 循环。

核心流程：
  1. Thought: LLM 分析当前槽位状态，推理缺少什么信息
  2. Action: LLM 决定下一步（提问/澄清/确认/完成）
  3. Observation: 用户在终端输入 → 更新槽位 → 记录本轮

本实验不涉及工具调用：所有 Action 都是面向用户的交互。
"""

import json

from agents.trip_planning.models.decision import ActionDetail, ActionType, CollectionDecision, SlotValue, StepRecord
from agents.trip_planning.slot_manager import SlotManager, SlotName
from openai.types.chat import (
	ChatCompletionAssistantMessageParam,
	ChatCompletionMessageParam,
	ChatCompletionSystemMessageParam,
	ChatCompletionUserMessageParam,
)

from inherit.llm.client import LLMClient
from inherit.prompt.prompt_manager import PromptManager
from inherit.utils.model_render import render_model_code


class TripRequirementCollector:
	"""出行需求收集器 — 基于 ReAct 模式的多轮对话引擎。

	通过多轮 Thought → Action → Observation 交互，
	逐步收集用户的出行需求，直到所有槽位确认完毕。

	用法：
		llm = LLMClient(...)
		pm = PromptManager(Path("prompts"))
		collector = TripRequirementCollector(llm, pm, max_iterations=15)
		result = collector.run("我想出去玩几天")
	"""


	def __init__(
			self,
			llm: LLMClient,
			prompt_manager: PromptManager,
			max_iterations: int = 15,
	) -> None:
		"""
		Args:
			llm: LLM 客户端（使用 chat_with_json 获取结构化 JSON）。
			prompt_manager: Jinja2 模板管理器（加载 react_system.j2 / react_user.j2）。
			max_iterations: 最大追问轮数，防止无限循环。
		"""
		self._llm = llm
		self._pm = prompt_manager
		self._max_iterations = max_iterations
		self._slot_manager = SlotManager()
		self._step_records: list[StepRecord] = []
		self._conversation_history: list[ChatCompletionMessageParam] = []


	# ── 公开 ────────────────────────────────────────────────

	def run(self, requirement: str) -> str:
		"""执行 ReAct 循环，逐步收集需求。

		Args:
			requirement: 用户的初始模糊需求（如"我想出去玩几天"）。

		Returns:
			最终需求摘要文本。
		"""
		# 首轮：从初始需求中提取槽位（用户可能一句话带了很多信息）
		intent: list[SlotValue] = self._parse_user_intent(requirement)
		self._apply_intent(intent)
		self._render_panel()

		# 首轮用户消息即为初始输入（已提取过的原始消息）
		user_msg: str = requirement

		for iteration in range(1, self._max_iterations + 1):
			print(f"\n{'=' * 40}")
			print(f"  🔄 第 {iteration} 轮")
			print(f"{'=' * 40}")

			# ── 1. Thought ──
			decision: CollectionDecision = self._think(user_msg)

			# ── 2. Action ──
			observation: str = self._act(decision, iteration)

			# ── 3. Record ──
			self._step_records.append(StepRecord(
				iteration=iteration,
				thought=decision.thought,
				action=decision.action,
				observation=observation,
			))

			# ── 4. 检查终止 ──
			if decision.action.type == ActionType.COMPLETE:
				print(f"\n✅ 需求收集完成！")
				return self._slot_manager.to_summary()

			# 下一轮的"用户消息"是本轮的观察结果
			user_msg = observation

		print(f"\n⚠️ 达到最大迭代次数（{self._max_iterations}），强制结束。")
		return self._slot_manager.to_summary()


	# ── 内部 ────────────────────────────────────────────────

	def _parse_user_intent(self, user_input: str) -> list[SlotValue]:
		"""解析用户意图 — 将自然语言映射为槽位键值对。

		通过 `render_model_code` 将 SlotValue 结构注入提示词，模型定义即提示词格式。
		注入 `_conversation_history` 让 LLM 从完整对话上下文中自行推断用户回答
		对应的槽位，而非由外部指定。

		Args:
			user_input: 用户最新输入。

		Returns:
			解析出的 SlotValue 列表，无匹配时返回空列表。
		"""
		recent_messages = self._conversation_history[-6:]
		system_prompt: str = self._pm.render(
			"agents/trip_planning/requirement_collector/extract_system.j2",
			slot_value_schema=render_model_code(SlotValue),
		)
		user_prompt: str = self._pm.render(
			"agents/trip_planning/requirement_collector/extract_user.j2",
			slots_context=self._slot_manager.to_context(),
			user_input=user_input,
			conversation_history=recent_messages,
		)
		messages: list[ChatCompletionSystemMessageParam | ChatCompletionUserMessageParam] = [
			ChatCompletionSystemMessageParam(role="system", content=system_prompt),
			ChatCompletionUserMessageParam(role="user", content=user_prompt),
		]
		raw_json: str = self._llm.chat_with_json(messages)
		items: list[dict[str, str]] = json.loads(raw_json)
		return [SlotValue.model_validate(item) for item in items]


	def _think(self, user_msg: str) -> CollectionDecision:
		"""调用 LLM 进行推理，输出 Thought + Action。

		Args:
			user_msg: 本轮的用户输入。

		Returns:
			LLM 输出的结构化 CollectionDecision。
		"""
		system_prompt: str = self._pm.render(
			"agents/trip_planning/requirement_collector/react_system.j2",
			collection_decision_schema=render_model_code(CollectionDecision),
		)
		user_prompt: str = self._pm.render(
			"agents/trip_planning/requirement_collector/react_user.j2",
			slots_context=self._slot_manager.to_context(),
			history=self._format_history(),
			user_message=user_msg,
		)

		messages: list[ChatCompletionMessageParam] = [
			ChatCompletionSystemMessageParam(role="system", content=system_prompt),
			ChatCompletionUserMessageParam(role="user", content=user_prompt),
		]

		raw_json: str = self._llm.chat_with_json(messages)
		return CollectionDecision.model_validate_json(raw_json)


	def _apply_intent(self, intent: list[SlotValue]) -> None:
		"""将解析出的用户意图批量应用到 SlotManager。"""
		for sv in intent:
			sv: SlotValue
			try:
				slot_name: SlotName = SlotName(sv.slot)
			except ValueError:
				continue
			was_revised: bool = self._slot_manager.fill(slot_name, sv.value)
			if was_revised:
				print(f"  ⚠️ 已确认的「{slot_name.label}」被覆盖，重新收集。")


	def _act(self, decision: CollectionDecision, iteration: int) -> str:
		"""执行 LLM 决定的行动。

		Args:
			decision: LLM 的本轮决策。
			iteration: 当前轮次。

		Returns:
			观察结果（用户输入或确认反馈）。
		"""
		action: ActionDetail = decision.action

		print(f"\n💭 Thought: {decision.thought}")
		print(f"🎯 Action: {action.type.value}")

		if action.type in (ActionType.ASK_QUESTION, ActionType.CLARIFY):
			# 向用户提问或追问澄清（执行层无区别，语义区分由 LLM 在提示词中控制）

			print(f"\n🤖 {action.message}")
			user_input: str = input("👤 ").strip()

			self._conversation_history.append(
				ChatCompletionAssistantMessageParam(role="assistant", content=action.message))
			self._conversation_history.append(ChatCompletionUserMessageParam(role="user", content=user_input))

			intent: list[SlotValue] = self._parse_user_intent(user_input)
			self._apply_intent(intent)

			self._render_panel()
			return user_input

		elif action.type == ActionType.CONFIRM:
			# 展示摘要，请用户确认

			self._slot_manager.confirm_all_collecting()

			print(f"\n🤖 {action.message}")
			self._render_panel()
			print("\n以上需求是否正确？（y/n）")
			user_input: str = input("👤 ").strip().lower()

			if user_input in ("y", "yes", "是", "确认", "正确", ""):
				return "确认无误"
			else:
				return "需要修改"

		elif action.type == ActionType.COMPLETE:
			self._slot_manager.confirm_all_collecting()
			self._render_panel()
			return ""

		return ""


	def _render_panel(self) -> None:
		"""打印槽位可视化面板。"""
		print(f"\n{self._slot_manager.render_panel()}")


	def _format_history(self) -> str:
		"""格式化步骤记录，供 LLM 参考已完成的推理和行动。

		Returns:
			格式化的历史记录文本，为空时返回占位文本。
		"""
		if not self._step_records:
			return "（尚无历史记录，这是第一轮）"

		lines: list[str] = []
		for step in self._step_records:
			step: StepRecord
			lines.append(f"--- 第 {step.iteration} 轮 ---")
			lines.append(f"Thought: {step.thought}")
			lines.append(f"Action: {step.action.type.value}")
			if step.action.target_slot:
				lines.append(f"Target: {step.action.target_slot}")
			lines.append(f"Message: {step.action.message}")
			lines.append(f"Observation: {step.observation}")
			lines.append("")
		return "\n".join(lines)


# ============================================================
# 演示：真实 LLM 驱动的 T→A→O 交互循环
# ============================================================
if __name__ == "__main__":
	import sys
	from pathlib import Path

	from config import Config
	from inherit.utils.path import get_prj_root

	config: Config = Config.from_yaml()
	prompts_dir: Path = get_prj_root() / "prompts"

	# ── 初始化 ──
	llm: LLMClient = LLMClient(
		api_key=config.llm.api_key_env,
		base_url=config.llm.base_url,
		model=config.llm.model,
		temperature=config.generation.temperature,
		top_p=config.generation.top_p,
		max_tokens=config.generation.max_tokens,
	)
	pm: PromptManager = PromptManager(prompts_dir)
	collector: TripRequirementCollector = TripRequirementCollector(llm, pm, max_iterations=15)

	# ── 欢迎信息 ──
	print("=" * 50)
	print("  🧳 行程规划智能体 — 需求收集")
	print("=" * 50)
	print("💡 试着说：我想出去玩几天，帮我规划一下～")
	print("💡 随时输入 /quit 退出")
	print()

	# ── 初始输入 ──
	user_request: str = input("👤 你的出行需求：").strip()
	if not user_request:
		user_request = "我想出去玩几天"

	if user_request == "/quit":
		print("👋 再见！")
		sys.exit(0)

	# ── 执行 ReAct 循环 ──
	summary: str = collector.run(user_request)
	print(f"\n{summary}")
	print("\n👋 谢谢使用，祝你旅途愉快！")
