"""TaskDecomposer — 初始任务分解模块。

调用 LLM 将用户需求分解为带依赖关系的 SubTask 列表。
通过 render_model_code 注入输出结构，model_validate 校验。
"""

from __future__ import annotations

from openai.types.chat import (
	ChatCompletionSystemMessageParam, ChatCompletionUserMessageParam, ChatCompletionMessageParam
)

from inherit.agents.planning.models.types import DecompositionResult
from inherit.llm.client import LLMClient
from inherit.llm.tool_registry import ToolRegistry
from inherit.prompt.prompt_manager import PromptManager
from inherit.utils.model_render import render_model_code


class TaskDecomposer:
	"""任务分解器 — 调用 LLM 将需求分解为带工具调用的子任务列表。"""


	def __init__(self, llm: LLMClient, pm: PromptManager, registry: ToolRegistry) -> None:
		"""初始化分解器。

		:param llm:      支持 chat_with_json 的基础 LLM 客户端
		:param pm:       PromptManager
		:param registry: 工具注册中心，用于动态生成工具表
		"""
		self._llm = llm
		self._pm = pm
		self._registry = registry


	def plan(self, domain_context: str, requirements_text: str) -> DecompositionResult:
		"""将用户需求分解为子任务列表。

		:param domain_context:    领域相关的额外指导文本（维度清单、规则等），由调用方注入
		:param requirements_text: 格式化后的用户需求文本
		:return: DecompositionResult（含 SubTask 列表 + 推理链）
		"""
		tools = self._registry.list()
		system_prompt: str = self._pm.render(
			"agents/planning/task_decomposer/system.j2",
			tools=tools,
			output_schema=render_model_code(DecompositionResult),
		)
		user_prompt: str = self._pm.render(
			"agents/planning/task_decomposer/decompose.j2",
			domain_context=domain_context,
			requirements=requirements_text,
		)

		messages: list[ChatCompletionMessageParam] = [
			ChatCompletionSystemMessageParam(role="system", content=system_prompt),
			ChatCompletionUserMessageParam(role="user", content=user_prompt),
		]

		raw_json: str = self._llm.chat_with_json(messages, temperature=0.3)

		return DecompositionResult.model_validate_json(raw_json)


if __name__ == "__main__":

	from config import Config

	from inherit.tools.tavily_search import TavilySearch
	from inherit.utils.path import get_prj_root

	# ── 内联分解指导（演示用，不依赖 agents.trip_planning）──
	DECOMPOSE_CONTEXT: str = (
		"出行规划领域：将用户需求拆为独立的子任务，"
		"覆盖交通、住宿、景点、天气、美食、补充搜索等维度。"
		"合理设置任务间依赖（如先查天气再建议穿着）。"
	)

	print("=" * 60)
	print("  TaskDecomposer 演示 — 需求 → 子任务分解")
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

	decomposer: TaskDecomposer = TaskDecomposer(llm=llm, pm=pm, registry=registry)

	result: DecompositionResult = decomposer.plan(
		DECOMPOSE_CONTEXT,
		"出发：北京 → 成都，日期：2026-07-20~07-23，偏好：自然风光、美食",
	)

	print(f"推理: {result.reasoning}")
	print(f"子任务 ({len(result.tasks)}):")
	for t in result.tasks:
		deps = f" ← {', '.join(t.depends_on)}" if t.depends_on else ""
		print(f"  ◻ {t.id}: {t.description}{deps}")
		for tc in t.tool_calls:
			print(f"     → {tc.to_display()}")
