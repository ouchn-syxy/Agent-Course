"""重规划器 — 对后续计划进行局部调整。

借鉴 ch03 Replanning 和 ch05 Feedback 模式。
"""

from __future__ import annotations

from openai.types.chat import ChatCompletionMessageParam, ChatCompletionSystemMessageParam, \
	ChatCompletionUserMessageParam
from pydantic import BaseModel, Field

from agents.review.models.study_state import (
	DailyPlan,
	DailyTask,
	DayStatus,
	KnowledgePoint,
	ReflectionResult,
	ReplanChanges,
	StudyState,
	TaskStatus,
	TaskType,
)
from agents.review.plan_generator import PlannedDay
from inherit.llm.client import LLMClient
from inherit.prompt.prompt_manager import PromptManager
from inherit.utils.model_render import render_model_code


# ============================================================
# Prompt 输出模型
# ============================================================

class ReplanOutput(BaseModel):
	"""重规划智能体的输出。"""

	changes_description: str = Field(description="调整说明文字")
	reasoning: str = Field(description="调整推理过程")
	modified_day_plans: list[PlannedDay] = Field(
		default_factory=list,
		description="需要调整的天数（仅输出被修改的天，完整替换 tasks）",
	)


class Replanner:
	"""重规划器。

	用法：
		replanner = Replanner(llm_client, prompt_manager)
		changes = replanner.replan(state, reflection)
	"""


	def __init__(self, llm_client: LLMClient, prompt_manager: PromptManager) -> None:
		"""初始化重规划器。

		Args:
			llm_client: LLM 客户端
			prompt_manager: Prompt 管理器
		"""
		self._llm: LLMClient = llm_client
		self._pm: PromptManager = prompt_manager


	def replan(self, state: StudyState, reflection: ReflectionResult) -> ReplanChanges:
		"""根据当日反思结果，调用 LLM 对后续天计划进行局部重规划。

		流程：
		1. 将 daily_plans 拆分为已完成（day <= current_day）和未完成两部分。
		2. 将当前状态、反思结果、知识点掌握度等信息渲染进 system/user prompt。
		3. 调用 LLM 输出 ReplanOutput（含 modified_day_plans）。
		4. 通过 _convert_plans 将 PlannedDay 转为领域层的 DailyPlan。
		5. 构造 ReplanChanges 并通过 _apply_changes 写回 StudyState。

		Args:
			state: 完整学习状态，包含 daily_plans、knowledge_points、current_day 等。
			reflection: DailyReviewer.reflect() 返回的反思结果，包含
				overall_effectiveness、insights、needs_replan 等信息。

		Returns:
			ReplanChanges，包含 changes_description、reasoning 和
			modified_day_plans（仅被修改的天）。
		"""
		completed_plans: list[DailyPlan] = [p for p in state.daily_plans if p.day <= state.current_day]
		future_plans: list[DailyPlan] = [p for p in state.daily_plans if p.day > state.current_day]

		system_prompt: str = self._pm.render(
			"agents/review/replanner/system.j2",
			replan_output_schema=render_model_code(ReplanOutput),
		)
		user_prompt: str = self._pm.render(
			"agents/review/replanner/replan.j2",
			current_day=state.current_day,
			total_days=state.total_days,
			completed_plans=completed_plans,
			future_plans=future_plans,
			reflection=reflection,
			knowledge_points=state.knowledge_points,
		)

		messages: list[ChatCompletionMessageParam] = [
			ChatCompletionSystemMessageParam(role="system", content=system_prompt),
			ChatCompletionUserMessageParam(role="user", content=user_prompt),
		]

		json_raw: str = self._llm.chat_with_json(messages, temperature=0.3, max_tokens=4096)
		output: ReplanOutput = ReplanOutput.model_validate_json(json_raw)

		modified_plans: list[DailyPlan] = self._convert_plans(state, output.modified_day_plans)

		changes: ReplanChanges = ReplanChanges(
			day=state.current_day,
			changes_description=output.changes_description,
			reasoning=output.reasoning,
			modified_day_plans=modified_plans,
		)

		self._apply_changes(state, changes)
		return changes


	@staticmethod
	def _convert_plans(state: StudyState, planned_days: list[PlannedDay]) -> list[DailyPlan]:
		"""将 LLM 输出的 PlannedDay 列表转换为领域层的 DailyPlan 列表。

		LLM 通过 ReplanOutput.modified_day_plans 返回 PlannedDay（含 PlannedTask），
		其中 PlannedTask.task_type 是字符串。本方法负责：
		- 将 PlannedTask 转为带 TaskStatus.PENDING 的 DailyTask。
		- 将字符串 task_type 转为 TaskType 枚举。
		- 从原有 state.daily_plans 继承 available_minutes（若原计划中无该天则默认 90 分钟）。

		Args:
			state: 完整学习状态，用于查找原计划的 available_minutes。
			planned_days: LLM 返回的 PlannedDay 列表，仅包含需要修改的天。

		Returns:
			转换后的 DailyPlan 列表，每个 DailyPlan 的 status 为 DayStatus.PENDING。
		"""
		old_plan_map: dict[int, DailyPlan] = {p.day: p for p in state.daily_plans}
		result: list[DailyPlan] = []
		for pd in planned_days:
			old_plan: DailyPlan | None = old_plan_map.get(pd.day)
			minutes: int = old_plan.available_minutes if old_plan else 90
			tasks: list[DailyTask] = []
			for pt in pd.tasks:
				task: DailyTask = DailyTask(
					id=pt.id,
					description=pt.description,
					knowledge_point_id=pt.knowledge_point_id,
					task_type=TaskType(pt.task_type),
					estimated_minutes=pt.estimated_minutes,
					status=TaskStatus.PENDING,
				)
				tasks.append(task)
			result.append(DailyPlan(
				day=pd.day,
				available_minutes=minutes,
				tasks=tasks,
				status=DayStatus.PENDING,
			))
		return result


	@staticmethod
	def _apply_changes(state: StudyState, changes: ReplanChanges) -> None:
		"""将重规划结果原地写入 StudyState.daily_plans。

		遍历 state.daily_plans，若某天的 day 在 modified_day_plans 中，
		则用新计划替换原有计划，并将状态重置为 DayStatus.PENDING。
		未出现在 modified_day_plans 中的天保持不变。

		Args:
			state: 待修改的学习状态（原地修改）。
			changes: 包含 modified_day_plans 的重规划变更。
		"""
		modified_days: dict[int, DailyPlan] = {mp.day: mp for mp in changes.modified_day_plans}
		for i, plan in enumerate(state.daily_plans):
			if plan.day in modified_days:
				new_plan: DailyPlan = modified_days[plan.day]
				state.daily_plans[i] = new_plan
				state.daily_plans[i].status = DayStatus.PENDING


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

	replanner: Replanner = Replanner(llm, pm)

	kps: list[KnowledgePoint] = [
		KnowledgePoint(
			id="linear_list", name="线性表", category="线性结构",
			description="线性表是最基本、最简单、最常用的一种数据结构",
			mastery=0.3, confidence=0.8,
		),
		KnowledgePoint(
			id="binary_tree", name="二叉树", category="非线性结构",
			description="二叉树是每个节点最多有两个子树的树形结构",
			mastery=0.5, confidence=0.7,
		),
	]
	plans: list[DailyPlan] = [
		DailyPlan(
			day=1, available_minutes=90,
			tasks=[
				DailyTask(
					id="t1", description="复习线性表", knowledge_point_id="linear_list",
					task_type=TaskType.REVIEW, estimated_minutes=20, status=TaskStatus.COMPLETED
				),
			],
			status=DayStatus.COMPLETED
		),
		DailyPlan(
			day=2, available_minutes=90,
			tasks=[
				DailyTask(
					id="t2", description="二叉树练习", knowledge_point_id="binary_tree",
					task_type=TaskType.PRACTICE, estimated_minutes=30, status=TaskStatus.PENDING
				),
			],
			status=DayStatus.PENDING
		),
	]
	state: StudyState = StudyState(
		exam_name="数据结构期末", total_days=21,
		knowledge_points=kps, daily_plans=plans, current_day=1,
	)
	reflection: ReflectionResult = ReflectionResult(
		overall_effectiveness=0.3,
		task_completion_rate=1.0,
		insights="线性表掌握不佳，需要更多练习",
		needs_replan=True,
	)

	changes: ReplanChanges = replanner.replan(state, reflection)
	print(f"调整说明：{changes.changes_description}")
	print(f"{changes.model_dump_json(indent=4, ensure_ascii=False)}")
