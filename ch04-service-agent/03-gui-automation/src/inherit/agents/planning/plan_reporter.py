"""PlanReporter — 方案报告模块。

汇总所有已收集信息，调用 LLM 生成最终 Markdown 格式的方案报告。
"""

from __future__ import annotations

from openai.types.chat import (
	ChatCompletionMessageParam, ChatCompletionSystemMessageParam, ChatCompletionUserMessageParam
)

from inherit.agents.planning.models.types import TaskExecutionRecord
from inherit.llm.client import LLMClient
from inherit.prompt.prompt_manager import PromptManager


class PlanReporter:
	"""方案报告器 — 基于收集的综合信息输出完整方案报告。"""


	def __init__(self, llm: LLMClient, pm: PromptManager) -> None:
		"""初始化报告器。

		:param llm: LLM 客户端（支持长文本 chat）
		:param pm:  PromptManager
		"""
		self._llm = llm
		self._pm = pm


	def generate(self, domain_context: str, requirements: str, records: list[TaskExecutionRecord]) -> str:
		"""生成最终方案报告。

		:param domain_context: 领域相关的输出格式与指导文本，由调用方注入
		:param requirements:   用户需求文本
		:param records:        所有已执行任务的记录
		:return:               Markdown 格式的方案报告
		"""
		collected: str = "\n\n---\n\n".join(r.to_context_string() for r in records)

		system_prompt: str = self._pm.render("agents/planning/plan_reporter/system.j2")
		user_prompt: str = self._pm.render(
			"agents/planning/plan_reporter/report.j2",
			domain_context=domain_context,
			requirements=requirements,
			collected_info=collected,
		)

		messages: list[ChatCompletionMessageParam] = [
			ChatCompletionSystemMessageParam(role="system", content=system_prompt),
			ChatCompletionUserMessageParam(role="user", content=user_prompt),
		]

		return self._llm.chat(messages, temperature=0.6, max_tokens=4096)


if __name__ == "__main__":
	from config import Config

	from inherit.agents.planning.models.types import SubTask, TaskStatus, ToolResult
	from inherit.utils.path import get_prj_root

	# ── 内联报告格式指导（演示用，不依赖 agents.trip_planning）──
	PLAN_CONTEXT: str = (
		"用 Markdown 输出行程报告：## 行程概览 → ## 交通方案 → ## 住宿推荐 → "
		"## 每日行程（按天排布）→ ## 美食清单 → ## 预算估算（表格）。"
		"报告应具体、可执行，直接引用已收集的数据。"
	)

	print("=" * 60)
	print("  PlanReporter 演示 — 碎片信息 → Markdown 报告")
	print("=" * 60)

	cfg: Config = Config.from_yaml()
	llm: LLMClient = LLMClient(
		api_key=cfg.llm.api_key_env,
		base_url=cfg.llm.base_url,
		model=cfg.llm.model,
		temperature=cfg.generation.temperature,
		top_p=cfg.generation.top_p,
		max_tokens=cfg.generation.max_tokens,
	)
	pm: PromptManager = PromptManager(templates_dir=get_prj_root() / "prompts")

	reporter: PlanReporter = PlanReporter(llm=llm, pm=pm)

	# ── 2 条记录：航班 + 酒店，信息足够生成简要报告 ──
	records: list[TaskExecutionRecord] = [
		TaskExecutionRecord(
			task=SubTask(id="task-1", description="查航班", status=TaskStatus.COMPLETED),
			results=[
				ToolResult(
					tool_name="flight_search",
					arguments={"dep": "北京", "arr": "成都", "date": "2026-07-20"},
					result="CA1401 07:30-10:25 ¥780 | HU7148 14:00-16:55 ¥620 | 3U8882 18:30-21:20 ¥450"
				)
			],
		),
		TaskExecutionRecord(
			task=SubTask(id="task-2", description="查酒店", status=TaskStatus.COMPLETED),
			results=[
				ToolResult(
					tool_name="hotel_search",
					arguments={"city": "成都", "budget": "3000-5000"},
					result="锦江宾馆 ¥320/晚（评分 4.2，春熙路旁）| 成都希尔顿 ¥480/晚（评分 4.6，天府广场）"
				)
			],
		),
	]

	print("📦 记录:", ", ".join(r.task.description for r in records))
	print("⏳ 生成报告中...\n")

	report: str = reporter.generate(
		domain_context=PLAN_CONTEXT,
		requirements="出发：北京 → 成都，日期：2026-07-20~07-23，偏好：自然风光、美食",
		records=records,
	)

	print(report)
