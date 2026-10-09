"""知识评估器 — 通过多轮 ReAct 对话了解学生对各知识点的掌握程度。

借鉴 ch03 的 TripRequirementCollector 的 ReAct 多轮对话收集模式：
每轮执行 Thought（LLM 分析）→ Action（向用户提问或结束）→ Observation（用户回复）。
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from openai.types.chat import ChatCompletionMessageParam, ChatCompletionSystemMessageParam, \
	ChatCompletionUserMessageParam, ChatCompletionAssistantMessageParam
from pydantic import BaseModel, Field

from agents.review.models.study_state import KnowledgePoint
from inherit.llm.client import LLMClient
from inherit.prompt.prompt_manager import PromptManager
from inherit.utils.model_render import render_model_code

# 置信度达标阈值：超过此值认为该知识点信息足够
CONFIDENCE_THRESHOLD: float = 0.35


# ============================================================
# 枚举
# ============================================================

class ActionType(StrEnum):
	"""诊断对话动作类型。"""

	ASK_QUESTION = "ask_question"  # 向学生提出下一个问题
	COMPLETE = "complete"  # 诊断完成


# ============================================================
# Prompt 输出模型
# ============================================================

class DiagnosticKnowledgeUpdate(BaseModel):
	"""诊断过程中对单个知识点掌握度的更新。"""

	id: str = Field(description="知识点 ID")
	name: str = Field(description="知识点名称")
	mastery: float = Field(description="掌握度，0.0~1.0，值越高表示掌握越好")
	confidence: float = Field(description="置信度，0.1~1.0，值越高表示判断越确定")
	evidence: str = Field(description="判断依据：LLM 根据学生哪句话得出的结论")


class DiagnosticNextAction(BaseModel):
	"""诊断对话的下一步动作。"""

	type: ActionType = Field(description="动作类型：ask_question（继续提问）或 complete（结束诊断）")
	message: str = Field(description="动作内容：ask_question 时为向学生提出的问题，complete 时为诊断总结")


class DiagnosticDecision(BaseModel):
	"""诊断智能体单轮决策输出 — LLM 每轮返回的结构化决策。"""

	thought: str = Field(description="LLM 对当前对话轮次的分析思考（内部推理，不展示给学生）")
	knowledge_updates: list[DiagnosticKnowledgeUpdate] = Field(
		default_factory=list,
		description="本轮诊断对知识点掌握的评估更新列表",
	)
	next_action: DiagnosticNextAction = Field(description="下一步动作：继续提问或结束诊断")


@dataclass
class ActiveKnowledgePoint:
	"""诊断过程中追踪的单个知识点掌握状态（内部草稿纸）。"""

	mastery: float  # 当前掌握度评估值，0.0~1.0，每轮 LLM 可覆盖更新
	confidence: float  # 当前置信度，0.0~1.0，达到阈值后不再追问该知识点
	evidence: str = ""  # 判断依据：LLM 根据学生哪句话得出的结论


@dataclass
class KnowledgePointUpdate:
	"""用于模板渲染的知识点更新条目（从 ActiveKnowledgePoint 格式化而来）。"""

	id: str  # 知识点唯一标识
	name: str  # 知识点中文名称
	mastery: float  # 当前掌握度，0.0~1.0
	confidence: float  # 当前置信度，0.0~1.0
	evidence: str = ""  # 判断依据


class KnowledgeAssessor:
	"""知识评估器 — ReAct 多轮对话评估知识掌握水平。

	用法：
		assessor = KnowledgeAssessor(llm_client, prompt_manager)
		kps = assessor.run(knowledge_points, exam_name)
	"""


	def __init__(
			self,
			llm_client: LLMClient,
			prompt_manager: PromptManager,
			max_diagnostic_rounds: int = 8,
	) -> None:
		"""初始化知识评估器。

		Args:
			llm_client: LLM 客户端
			prompt_manager: Prompt 管理器
			max_diagnostic_rounds: 诊断最大对话轮数，默认 8
		"""
		self._llm: LLMClient = llm_client
		self._pm: PromptManager = prompt_manager
		self._max_rounds: int = max_diagnostic_rounds


	def run(
			self,
			knowledge_points: list[KnowledgePoint],
			exam_name: str = "",
			initial_message: str | None = None,
	) -> list[KnowledgePoint]:
		"""执行多轮诊断对话，返回更新后的 KnowledgePoint 列表。

		Args:
			knowledge_points: 待诊断的知识点列表（会原地修改）
			exam_name: 考试名称
			initial_message: 用户的首条消息（可选，若提供则跳过多轮对话直接提取）

		Returns:
			更新后的知识点列表（同一对象，已原地修改 mastery/confidence）
		"""
		# 构建知识点 ID → 对象的快速索引
		kp_map: dict[str, KnowledgePoint] = {kp.id: kp for kp in knowledge_points}

		# 追踪每个知识点的活跃掌握度/置信度（随时间累积）
		active: dict[str, ActiveKnowledgePoint] = {}
		# 对话上下文
		history: list[ChatCompletionMessageParam] = []

		# 若提供了首条用户消息，先推入历史，让模板从 history 动态渲染
		initial_message = initial_message or "请开始诊断"
		history.append(ChatCompletionUserMessageParam(role="user", content=initial_message))

		round_num: int
		for round_num in range(1, self._max_rounds + 1):
			# 判断是否所有知识点都已达标
			if self._all_points_confident(kp_map, active):
				print(f"所有知识点置信度达标，诊断提前结束（第 {round_num} 轮）")
				break

			# 构建 prompt 并获取 LLM 决策
			system_prompt: str = self._pm.render(
				"agents/review/knowledge_assessor/system.j2",
				diagnostic_decision_schema=render_model_code(DiagnosticDecision),
			)
			prompt: str = self._pm.render(
				"agents/review/knowledge_assessor/diagnose.j2",
				exam_name=exam_name,
				knowledge_points=knowledge_points,
				active_updates=self._format_active_updates(active, kp_map),
				history=history,
			)

			messages: list[ChatCompletionMessageParam] = [
				ChatCompletionSystemMessageParam(role="system", content=system_prompt),
				ChatCompletionUserMessageParam(role="user", content=prompt),
			]
			json_raw: str = self._llm.chat_with_json(messages, temperature=0.3)
			decision: DiagnosticDecision = DiagnosticDecision.model_validate_json(json_raw)

			# 处理知识点更新
			for upd in decision.knowledge_updates:
				if upd.id in kp_map:
					active[upd.id] = ActiveKnowledgePoint(
						mastery=upd.mastery,
						confidence=upd.confidence,
						evidence=upd.evidence,
					)

			# 检查是否结束
			next_action: DiagnosticNextAction = decision.next_action
			action_type: ActionType = next_action.type

			if action_type == ActionType.COMPLETE:
				print(f"LLM 决定完成诊断（第 {round_num} 轮）")
				print(f"\n💡 诊断总结：{next_action.message}")
				break

			# 向用户提问
			question: str = next_action.message or "请告诉我你对这些知识点的掌握情况"
			print(f"\n[诊断第 {round_num} 轮] {question}")
			user_reply: str = input("> ").strip()

			history.append(ChatCompletionAssistantMessageParam(role="assistant", content=question))
			history.append(ChatCompletionUserMessageParam(role="user", content=user_reply))

		# 将活跃状态写入知识点
		kp_id: str
		info: ActiveKnowledgePoint
		for kp_id, info in active.items():
			kp: KnowledgePoint | None = kp_map.get(kp_id)
			if not kp:
				continue
			kp.mastery = info.mastery
			kp.confidence = info.confidence

		return knowledge_points


	@staticmethod
	def _all_points_confident(
			all_points: dict[str, KnowledgePoint],
			active_points: dict[str, ActiveKnowledgePoint],
	) -> bool:
		"""是否所有知识点都已达到置信度阈值。"""
		if not all_points:
			return False
		if not active_points:
			return False
		for kp_id in all_points:
			if kp_id not in active_points:
				return False
			if active_points[kp_id].confidence < CONFIDENCE_THRESHOLD:
				return False
		return True


	@staticmethod
	def _format_active_updates(
			active: dict[str, ActiveKnowledgePoint],
			kp_map: dict[str, KnowledgePoint],
	) -> list[KnowledgePointUpdate]:
		"""格式化活跃知识点更新用于模板渲染。"""
		result: list[KnowledgePointUpdate] = []
		for kp_id, info in active.items():
			kp: KnowledgePoint | None = kp_map.get(kp_id)
			name: str = kp.name if kp else kp_id
			result.append(KnowledgePointUpdate(
				id=kp_id,
				name=name,
				mastery=info.mastery,
				confidence=info.confidence,
				evidence=info.evidence,
			))
		return result


if __name__ == "__main__":
	from config import Config
	from inherit.utils.path import get_prj_root

	config: Config = Config.from_yaml()
	pm: PromptManager = PromptManager(get_prj_root() / "prompts")
	llm: LLMClient = LLMClient(
		api_key=config.llm.api_key_env,
		base_url=config.llm.base_url,
		model=config.llm.model,
	)

	assessor: KnowledgeAssessor = KnowledgeAssessor(llm, pm)
	kps: list[KnowledgePoint] = [
		KnowledgePoint(
			id="linear_list", name="线性表", category="线性结构",
			description="线性表是最基本、最简单、最常用的一种数据结构，包括顺序表和链表",
			mastery=0.5, confidence=0.3
		),
		KnowledgePoint(
			id="stack_queue", name="栈与队列", category="线性结构",
			description="栈是后进先出（LIFO）的线性表，队列是先进先出（FIFO）的线性表",
			mastery=0.4, confidence=0.3
		),
		KnowledgePoint(
			id="binary_tree", name="二叉树", category="非线性结构",
			description="二叉树是每个节点最多有两个子树的树形结构，包括遍历、二叉搜索树等",
			mastery=0.6, confidence=0.3
		),
	]
	result: list[KnowledgePoint] = assessor.run(kps, exam_name="数据结构期末")
	print("\n诊断完成：")
	for kp in result:
		print(f"  {kp.name}: mastery={kp.mastery:.2f}, confidence={kp.confidence:.2f}")
