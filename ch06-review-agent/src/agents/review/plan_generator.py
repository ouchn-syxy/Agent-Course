"""计划生成器 — 程序排序 + LLM 逐天生成每日任务。

借鉴 ch03 的 TaskDecomposer 模式：
- 程序部分：基于 KnowledgePoint.priority 纯 Python 排序
- LLM 部分：逐天调用 chat_with_json 生成当日 DailyPlan
每次生成时携带前几天的已规划摘要，确保前后衔接、避免遗漏。
"""

from __future__ import annotations

from collections import defaultdict

from openai.types.chat import (
	ChatCompletionMessageParam,
	ChatCompletionSystemMessageParam,
	ChatCompletionUserMessageParam
)
from pydantic import BaseModel, Field

from agents.review.models.study_state import DailyPlan, DailyTask, KnowledgePoint, TaskStatus, TaskType, DayStatus
from inherit.llm.client import LLMClient
from inherit.prompt.prompt_manager import PromptManager
from inherit.utils.model_render import render_model_code


# ============================================================
# Prompt 输出模型
# ============================================================

class PlannedTask(BaseModel):
	"""LLM 规划的一个每日任务。"""

	id: str = Field(description="任务 ID，格式 task_day{day}_{序号}")
	description: str = Field(description="具体的任务描述")
	knowledge_point_id: str = Field(description="关联的知识点 ID")
	task_type: str = Field(description="任务类型：review / practice / quiz")
	estimated_minutes: int = Field(description="预估耗时（分钟）")


class PlannedDay(BaseModel):
	"""LLM 规划的一个复习日。"""

	day: int = Field(description="第几天，从 1 开始")
	tasks: list[PlannedTask] = Field(description="当日任务列表")


class PlanGenerationOutput(BaseModel):
	"""计划生成智能体的完整输出（一次性全量生成，已弃用）。"""

	daily_plans: list[PlannedDay] = Field(description="每日计划列表")
	planning_reasoning: str = Field(description="整体规划思路说明")


class DayPlanOutput(BaseModel):
	"""单日计划输出（逐天生成模式）。"""

	tasks: list[PlannedTask] = Field(description="当日任务列表")
	day_reasoning: str = Field(description="当日任务的安排思路说明")


class PlanGenerator:
	"""计划生成器。

	用法：
		generator = PlanGenerator(llm_client, prompt_manager)
		plans = generator.generate(knowledge_points, exam_name, total_days, daily_minutes)
	"""


	def __init__(self, llm_client: LLMClient, prompt_manager: PromptManager) -> None:
		self._llm = llm_client
		self._pm = prompt_manager


	def generate(
			self,
			knowledge_points: list[KnowledgePoint],
			exam_name: str,
			total_days: int,
			daily_minutes: int,
	) -> list[DailyPlan]:
		"""逐天生成完整的学习计划。

		每次 LLM 调用只生成一天的计划，但会提供前几天的
		已规划摘要作为上下文，确保计划前后衔接、不遗漏知识点。

		Args:
			knowledge_points: 已诊断的知识点（含 mastery/confidence）
			exam_name: 考试名称
			total_days: 总天数
			daily_minutes: 每天可用学习时间（分钟）

		Returns:
			DailyPlan 列表（day 1~total_days）
		"""

		# Step 1: 基于 KnowledgePoint.priority 排序（计算字段，实时反映掌握度变化）
		sorted_kps: list[KnowledgePoint] = sorted(knowledge_points, key=lambda kp: kp.priority, reverse=True)

		system_prompt: str = self._pm.render(
			"agents/review/plan_generator/system.j2",
			plan_output_schema=render_model_code(DayPlanOutput),
		)

		# Step 2: 逐天生成
		all_plans: list[DailyPlan] = []

		for day in range(1, total_days + 1):
			prev_summary: str = self._build_previous_summary(all_plans)
			user_prompt: str = self._pm.render(
				"agents/review/plan_generator/generate.j2",
				exam_name=exam_name,
				total_days=total_days,
				current_day=day,
				available_minutes=daily_minutes,
				knowledge_points=sorted_kps,
				previous_days_summary=prev_summary,
			)

			messages: list[ChatCompletionMessageParam] = [
				ChatCompletionSystemMessageParam(role="system", content=system_prompt),
				ChatCompletionUserMessageParam(role="user", content=user_prompt),
			]

			output: DayPlanOutput | None = None
			last_error: Exception | None = None
			for attempt in range(1, 4):
				try:
					json_raw: str = self._llm.chat_with_json(messages, temperature=0.3)
					output = DayPlanOutput.model_validate_json(json_raw)
					break
				except Exception as exc:
					last_error = exc
					print(f"  第 {day:2d} 天计划返回无效，正在重试（{attempt}/3）：{exc}")
			if output is None:
				raise RuntimeError(f"第 {day} 天计划生成失败，未写入不完整会话。") from last_error

			tasks: list[DailyTask] = []
			for rt in output.tasks:
				task: DailyTask = DailyTask(
					id=rt.id,
					description=rt.description,
					knowledge_point_id=rt.knowledge_point_id,
					task_type=TaskType(rt.task_type),
					estimated_minutes=int(rt.estimated_minutes),
					status=TaskStatus.PENDING,
				)
				tasks.append(task)

			plan: DailyPlan = DailyPlan(
				day=day,
				available_minutes=daily_minutes,
				tasks=tasks,
				status=DayStatus.IN_PROGRESS if day == 1 else DayStatus.PENDING,
			)
			all_plans.append(plan)

			print(f"  第 {day:2d} 天 → {len(tasks)} 个任务  {'✅' if output.day_reasoning else ''}")

		print(f"\n📋 计划已生成：{len(all_plans)} 天，共 {sum(len(p.tasks) for p in all_plans)} 个任务")

		return all_plans


	@staticmethod
	def _build_previous_summary(plans: list[DailyPlan]) -> str:
		"""将前几天的计划压缩为摘要文本，控制上下文长度。"""
		if not plans:
			return "（尚无已规划的天数）"

		# 统计每个知识点在前几天出现的总预估分钟数

		kp_minutes: dict[str, int] = defaultdict(int)
		lines: list[str] = []
		# 仅保留最近五天任务正文；全量覆盖情况由后面的分钟统计表示。
		for p in plans[-5:]:
			task_descs: list[str] = [t.description for t in p.tasks]
			lines.append(f"第{p.day}天：{'；'.join(task_descs)}")
			for t in p.tasks:
				kp_minutes[t.knowledge_point_id] += t.estimated_minutes

		# 拼接摘要
		parts: list[str] = ["\n".join(lines), "", "已规划知识点累计时长："]
		for kp_id, mins in sorted(kp_minutes.items()):
			parts.append(f"  {kp_id}: {mins} 分钟")
		return "\n".join(parts)


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

	generator: PlanGenerator = PlanGenerator(llm, pm)
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
	plans: list[DailyPlan] = generator.generate(
		knowledge_points=kps,
		exam_name="数据结构期末",
		total_days=3,
		daily_minutes=90,
	)
	print(f"生成了 {len(plans)} 天计划")
	for p in plans:
		print(f"\n  第 {p.day} 天（{p.available_minutes} 分钟）：")
		for t in p.tasks:
			print(f"    [{t.task_type.value}] {t.description} ({t.estimated_minutes}min)")
