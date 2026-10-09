"""每日回顾器 — 日终分析当日学习效果，决定是否需要调整后续计划。

借鉴 ch03 的 InfoInspector 模式。
"""

from __future__ import annotations

from dataclasses import dataclass

from openai.types.chat import (
	ChatCompletionMessageParam,
	ChatCompletionSystemMessageParam,
	ChatCompletionUserMessageParam
)

from agents.review.models.study_state import StudyState, ReflectionResult, DailyPlan, KnowledgePoint
from inherit.llm.client import LLMClient
from inherit.prompt.prompt_manager import PromptManager
from inherit.utils.model_render import render_model_code


@dataclass
class AffectedKnowledgePoint:
	"""受影响的知识点摘要，用于反思模板渲染。"""

	name: str  # 知识点中文名称
	mastery: float  # 当日结束后掌握度
	old_mastery: float  # 当日开始前掌握度
	confidence: float  # 当日结束后置信度
	old_confidence: float  # 当日开始前置信度


class DailyReviewer:
	"""每日回顾器。

	用法：
		reviewer = DailyReviewer(llm_client, prompt_manager)
		result = reviewer.reflect(state)
	"""


	def __init__(self, llm_client: LLMClient, prompt_manager: PromptManager) -> None:
		"""初始化每日回顾器。

		Args:
			llm_client: LLM 客户端
			prompt_manager: Prompt 管理器
		"""
		self._llm: LLMClient = llm_client
		self._pm: PromptManager = prompt_manager


	def reflect(self, state: StudyState) -> ReflectionResult:
		"""对当日学习进行反思。

		Args:
			state: 完整学习状态

		Returns:
			ReflectionResult 对象
		"""
		# 收集今日任务
		current_plan: DailyPlan | None = None
		for plan in state.daily_plans:
			if plan.day == state.current_day:
				current_plan = plan
				break

		if current_plan is None:
			return ReflectionResult( overall_effectiveness=0, task_completion_rate=0, insights="今日没有复习计划。")

		# 构建任务→知识点名称映射
		task_kp_names: dict[str, str] = self._build_task_kp_map(state, current_plan)

		# 收集受今日影响的知识点掌握度变化
		affected_kps: list[AffectedKnowledgePoint] = self._collect_affected_kps(state, current_plan)

		# 未来计划
		future_plans: list[DailyPlan] = [p for p in state.daily_plans if p.day > state.current_day]

		system_prompt: str = self._pm.render(
			"agents/review/daily_reviewer/system.j2",
			reflection_result_schema=render_model_code(ReflectionResult),
		)
		user_prompt: str = self._pm.render(
			"agents/review/daily_reviewer/reflect.j2",
			current_day=state.current_day,
			total_days=state.total_days,
			today_tasks=current_plan.tasks,
			task_kp_names=task_kp_names,
			affected_kps=affected_kps,
			future_plans=future_plans,
		)

		messages: list[ChatCompletionMessageParam] = [
			ChatCompletionSystemMessageParam(role="system", content=system_prompt),
			ChatCompletionUserMessageParam(role="user", content=user_prompt),
		]

		json_raw: str = self._llm.chat_with_json(messages, temperature=0.3, max_tokens=2048)
		result: ReflectionResult = ReflectionResult.model_validate_json(json_raw)
		return result


	@staticmethod
	def _build_task_kp_map(state: StudyState, daily_plan: DailyPlan) -> dict[str, str]:
		"""构建任务 ID → 知识点名称映射。"""
		kp_map: dict[str, KnowledgePoint] = {kp.id: kp for kp in state.knowledge_points}
		result: dict[str, str] = {}
		for task in daily_plan.tasks:
			kp: KnowledgePoint | None = kp_map.get(task.knowledge_point_id)
			if kp is None:
				continue
			result[task.id] = kp.name
		return result


	@staticmethod
	def _collect_affected_kps(state: StudyState, daily_plan: DailyPlan) -> list[AffectedKnowledgePoint]:
		"""收集今日受影响的知识点及其新旧掌握度。"""
		kp_map: dict[str, KnowledgePoint] = {kp.id: kp for kp in state.knowledge_points}
		affected: dict[str, AffectedKnowledgePoint] = {}
		for task in daily_plan.tasks:
			kp: KnowledgePoint | None = kp_map.get(task.knowledge_point_id)
			if kp is None:
				continue
			if kp.id not in affected:
				# 掌握度更新已写入 history；取当天第一条记录，保留真正的日初值。
				today_records = [record for record in kp.history if record.day == state.current_day]
				first_record = today_records[0] if today_records else None
				affected[kp.id] = AffectedKnowledgePoint(
					name=kp.name,
					mastery=kp.mastery,
					old_mastery=first_record.old_mastery if first_record else kp.mastery,
					confidence=kp.confidence,
					old_confidence=first_record.old_confidence if first_record else kp.confidence,
				)

		return list(affected.values())


if __name__ == "__main__":
	from config import Config
	from inherit.utils.path import get_prj_root
	from agents.review.models.study_state import DailyTask, DayStatus, TaskStatus, TaskType

	config: Config = Config.from_yaml()
	pm: PromptManager = PromptManager(get_prj_root() / "prompts")
	llm: LLMClient = LLMClient(
		api_key=config.llm.api_key_env,
		base_url=config.llm.base_url,
		model=config.llm.model,
	)

	reviewer: DailyReviewer = DailyReviewer(llm, pm)

	# 构建演示用 StudyState
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
	]
	tasks: list[DailyTask] = [
		DailyTask(
			id="t1", description="复习线性表基本概念", knowledge_point_id="linear_list",
		    task_type=TaskType.REVIEW, estimated_minutes=20, status=TaskStatus.COMPLETED
		),
		DailyTask(
			id="t2", description="二叉树遍历练习", knowledge_point_id="binary_tree",
			task_type=TaskType.PRACTICE, estimated_minutes=30, status=TaskStatus.COMPLETED
		),
	]
	plan: DailyPlan = DailyPlan(day=1, available_minutes=90, tasks=tasks, status=DayStatus.COMPLETED)
	state: StudyState = StudyState(
		exam_name="数据结构期末", total_days=21,
		knowledge_points=kps, daily_plans=[plan], current_day=1,
	)

	result: ReflectionResult = reviewer.reflect(state)
	print(f"整体有效性：{result.overall_effectiveness}")
	print(f"任务完成率：{result.task_completion_rate}")
	print(f"洞见：{result.insights}")
	print(f"需要重规划：{result.needs_replan}")
