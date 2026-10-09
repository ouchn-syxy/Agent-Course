"""InfoInspector — 信息充分性审查模块。

调用 LLM 审视已收集的信息，判断是否足以生成最终方案。
不足时生成补充工具调用。
通过 render_model_code 注入输出结构，model_validate 校验。
"""

from __future__ import annotations

from openai.types.chat import (
	ChatCompletionMessageParam, ChatCompletionSystemMessageParam, ChatCompletionUserMessageParam
)

from inherit.agents.planning.models.types import InspectionResult, TaskExecutionRecord
from inherit.llm.client import LLMClient
from inherit.llm.tool_registry import ToolRegistry
from inherit.prompt.prompt_manager import PromptManager
from inherit.utils.model_render import render_model_code


class InfoInspector:
	"""信息审查器 — 审视已收集信息并决定是否需要补充。"""


	def __init__(
			self,
			llm: LLMClient,
			pm: PromptManager,
			registry: ToolRegistry,
	) -> None:
		"""初始化审查器。

		:param llm:       支持 chat_with_json 的 LLM 客户端
		:param pm:        PromptManager
		:param registry:  工具注册中心，直接传入模板动态渲染工具表
		"""
		self._llm: LLMClient = llm
		self._pm: PromptManager = pm
		self._registry: ToolRegistry = registry


	def inspect(
			self,
			domain_context: str,
			requirements: str,
			records: list[TaskExecutionRecord],
	) -> InspectionResult:
		"""检查信息充分性。

		:param domain_context: 领域相关的审核标准文本，由调用方注入
		:param requirements:   用户需求文本
		:param records:        所有已执行任务的记录
		:return:               InspectionResult
		"""
		collected: str = "\n\n".join(r.to_context_string() for r in records)

		system_prompt: str = self._pm.render(
			"agents/planning/info_inspector/system.j2",
			tools=self._registry.list(),
			output_schema=render_model_code(InspectionResult),
		)
		user_prompt: str = self._pm.render(
			"agents/planning/info_inspector/inspect.j2",
			domain_context=domain_context,
			requirements=requirements,
			collected_info=collected,
		)

		messages: list[ChatCompletionMessageParam] = [
			ChatCompletionSystemMessageParam(role="system", content=system_prompt),
			ChatCompletionUserMessageParam(role="user", content=user_prompt),
		]

		raw_json: str = self._llm.chat_with_json(messages, temperature=0.3)
		return InspectionResult.model_validate_json(raw_json)


if __name__ == "__main__":

	from config import Config

	from inherit.agents.planning.models.types import SubTask, TaskStatus, ToolResult
	from inherit.tools.tavily_search import TavilySearch
	from inherit.utils.path import get_prj_root

	# ── 内联领域审查标准（演示用，不依赖 agents.trip_planning）──
	INSPECT_CONTEXT: str = (
		"信息充分性审查标准：交通需有航班（含时间价格），"
		"住宿需 2-3 个酒店选项，景点需 3-5 个，天气需覆盖出行每天，美食需有当地推荐。"
		"如果某维度仅有 1 条或缺失，则为不充分。"
	)

	print("=" * 60)
	print("  InfoInspector 演示 — 信息充分性审查")
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

	registry: ToolRegistry = ToolRegistry()
	registry.register(TavilySearch(api_key=cfg.tavily.api_key, include_answer=False).to_tool_def())

	inspector: InfoInspector = InfoInspector(llm=llm, pm=pm, registry=registry)

	# ── 2 条记录：航班 OK，酒店仅 1 家（明显不充分）──
	records: list[TaskExecutionRecord] = [
		TaskExecutionRecord(
			task=SubTask(id="task-1", description="查航班", status=TaskStatus.COMPLETED),
			results=[
				ToolResult(
					tool_name="flight_search",
					arguments={"dep": "北京", "arr": "成都", "date": "2026-07-20"},
					result="CA1401 北京→成都 07:30-10:25 ¥780 | HU7148 14:00-16:55 ¥620"
				)
			],
		),
		TaskExecutionRecord(
			task=SubTask(id="task-2", description="查酒店", status=TaskStatus.COMPLETED),
			results=[
				ToolResult(
					tool_name="hotel_search",
					arguments={"city": "成都", "budget": "3000-5000"},
					result="仅找到 1 家：锦江宾馆 ¥320/晚（评分 4.2）"
				)
			],
		),
	]

	print("📦 记录:", ", ".join(r.task.description for r in records))

	inspection: InspectionResult = inspector.inspect(
		domain_context=INSPECT_CONTEXT,
		requirements="出发：北京 → 成都，日期：2026-07-20~07-23，偏好：自然风光、美食",
		records=records,
	)

	print(f"充分性: {'✅ 充足' if inspection.is_sufficient else '❌ 不充分'}")
	print(f"推理: {inspection.reasoning}")
	if inspection.additional_tool_calls:
		print(f"补充调用: {[tc.to_display() for tc in inspection.additional_tool_calls]}")
