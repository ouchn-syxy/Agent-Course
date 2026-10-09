"""出题器 — 根据知识点掌握度生成练习题。

借鉴 ch05 的 AgentRunner JSON Schema 约束。
支持工具调用：search_reference_questions、lookup_knowledge_point。
"""

from __future__ import annotations

import json

from openai.types.chat import (
	ChatCompletionMessageParam,
	ChatCompletionSystemMessageParam,
	ChatCompletionUserMessageParam,
	ChatCompletionAssistantMessageParam,
	ChatCompletionToolMessageParam,
	ChatCompletionMessageFunctionToolCallParam,
)
from pydantic import BaseModel, Field

from agents.review.models.study_state import KnowledgePoint, TaskType
from agents.review.tools.lookup_knowledge_point import LookupKnowledgePoint
from agents.review.tools.search_reference_questions import SearchReferenceQuestions
from inherit.llm.tool_client import ToolLLMClient
from inherit.llm.tool_registry import ToolRegistry
from inherit.prompt.prompt_manager import PromptManager
from inherit.utils.model_render import render_model_code


# ============================================================
# Prompt 输出模型
# ============================================================

class GradingCriteriaCorrectness(BaseModel):
	"""正确性维度的评分标准。"""

	max_score: float = Field(description="满分")
	description: str = Field(description="该维度的评分标准描述")


class GradingCriteriaCompleteness(BaseModel):
	"""完整性维度的评分标准。"""

	max_score: float = Field(description="满分")
	description: str = Field(description="该维度的评分标准描述")


class GradingCriteriaClarity(BaseModel):
	"""清晰度维度的评分标准。"""

	max_score: float = Field(description="满分")
	description: str = Field(description="该维度的评分标准描述")


class GradingCriteria(BaseModel):
	"""题目评分标准。"""

	correctness: GradingCriteriaCorrectness = Field(description="正确性评分标准")
	completeness: GradingCriteriaCompleteness = Field(description="完整性评分标准")
	clarity: GradingCriteriaClarity = Field(description="清晰度评分标准")


class GeneratedQuestion(BaseModel):
	"""出题器的输出 — 一道完整的练习题。"""

	question: str = Field(description="题目正文")
	reference_answer: str = Field(description="参考答案（详细）")
	grading_criteria: GradingCriteria = Field(description="评分标准")
	key_points: list[str] = Field(description="参考答案中必须包含的关键要点")


# ============================================================
# 出题器
# ============================================================

class QuestionGenerator:
	"""出题器 — 根据知识点掌握度生成练习题，支持工具调用搜索参考题目。

	用法：
		gen = QuestionGenerator(
			llm_client, prompt_manager,
			search_reference_questions=SearchReferenceQuestions(...),
			lookup_knowledge_point=LookupKnowledgePoint(),
		)
		question = gen.generate(knowledge_point)

	工具调用流程：
		1. LLM 判断是否需要搜索参考题目或百科定义
		2. 如需搜索 → 执行工具 → 结果追加到消息 → 重新推理
		3. LLM 不再调用工具 → 解析 JSON 输出
	"""


	def __init__(
		self,
		llm_client: ToolLLMClient,
		prompt_manager: PromptManager,
		*,
		search_reference_questions: SearchReferenceQuestions | None = None,
		lookup_knowledge_point: LookupKnowledgePoint | None = None,
	) -> None:
		"""初始化出题器。

		Args:
			llm_client: 支持 Function Calling 的 LLM 客户端
			prompt_manager: Prompt 管理器
			search_reference_questions: 搜索参考题目工具实例，为 None 则不注册
			lookup_knowledge_point: Wikipedia 知识点查询工具实例，为 None 则不注册
		"""
		self._llm: ToolLLMClient = llm_client
		self._pm: PromptManager = prompt_manager

		self._registry: ToolRegistry = ToolRegistry()
		for tool in (search_reference_questions, lookup_knowledge_point):
			if tool is not None:
				self._registry.register(tool.to_tool_def())


	def generate(
			self,
			knowledge_point: KnowledgePoint,
			task_type: TaskType = TaskType.PRACTICE,
	) -> GeneratedQuestion:
		"""生成一道针对指定知识点的练习题。

		Args:
			knowledge_point: 知识点对象
			task_type: 任务类型

		Returns:
			GeneratedQuestion 对象
		"""

		system_prompt: str = self._pm.render(
			"agents/review/question_generator/system.j2",
			generated_question_schema=render_model_code(GeneratedQuestion),
			tools=self._registry.list(),
		)
		user_prompt: str = self._pm.render(
			"agents/review/question_generator/generate.j2",
			knowledge_point_schema=render_model_code(KnowledgePoint),
			knowledge_point_data=knowledge_point.model_dump_json(indent=4, ensure_ascii=False),
			task_type=task_type,
		)

		messages: list[ChatCompletionMessageParam] = [
			ChatCompletionSystemMessageParam(role="system", content=system_prompt),
			ChatCompletionUserMessageParam(role="user", content=user_prompt),
		]

		tools: list = [t.to_openai_tool() for t in self._registry.list()]

		max_turns: int = 5
		for _ in range(max_turns):
			content, tool_calls = self._llm.chat_with_tools(messages, tools, temperature=0.5)
			if not tool_calls:
				if content:
					return GeneratedQuestion.model_validate_json(content)
				raise RuntimeError("LLM 返回空响应，未调用工具也未输出 JSON")

			assistant_tool_calls: list[ChatCompletionMessageFunctionToolCallParam] = []
			tool_messages: list[tuple[str, str]] = []

			for tc in tool_calls:
				fn_name: str = tc.function.name
				print(f"调用工具: {fn_name}")
				fn_args: dict = json.loads(tc.function.arguments)
				result: str = self._registry.execute(fn_name, **fn_args)

				assistant_tool_calls.append(ChatCompletionMessageFunctionToolCallParam(
					id=tc.id,
					type="function",
					function={"name": fn_name, "arguments": tc.function.arguments},
				))
				tool_messages.append((tc.id, result))

			messages.append(ChatCompletionAssistantMessageParam(
				role="assistant",
				content=content,
				tool_calls=assistant_tool_calls,
			))
			for tid, res in tool_messages:
				messages.append(ChatCompletionToolMessageParam(
					role="tool",
					tool_call_id=tid,
					content=res,
				))

		# 达到最大轮次，强制 LLM 输出最终结果
		messages.append(ChatCompletionUserMessageParam(
			role="user",
			content="请基于以上工具返回的信息，直接输出最终 JSON 结果。不要再调用工具。",
		))
		json_raw: str = self._llm.chat_with_json(messages, temperature=0.5, max_tokens=2048)
		question: GeneratedQuestion = GeneratedQuestion.model_validate_json(json_raw)
		return question


if __name__ == "__main__":
	from config import Config
	from inherit.utils.path import get_prj_root
	from agents.review.tools.lookup_knowledge_point import LookupKnowledgePoint
	from agents.review.tools.search_reference_questions import SearchReferenceQuestions

	config: Config = Config.from_yaml()
	pm: PromptManager = PromptManager(get_prj_root() / "prompts")
	llm: ToolLLMClient = ToolLLMClient(
		api_key=config.llm.api_key_env,
		base_url=config.llm.base_url,
		model=config.llm.model,
	)

	gen: QuestionGenerator = QuestionGenerator(
		llm, pm,
		search_reference_questions=SearchReferenceQuestions(
			tavily_api_key=config.tavily.api_key,
			max_results=config.tavily.max_results,
		),
		lookup_knowledge_point=LookupKnowledgePoint(),
	)
	kp: KnowledgePoint = KnowledgePoint(
		id="linear_list", name="线性表", category="线性结构",
		description="线性表是最基本、最简单、最常用的一种数据结构，包括顺序表和链表",
		mastery=0.5, confidence=0.3
	)
	result: GeneratedQuestion = gen.generate(kp)
	print(f"题目：{result.question}")
	print(f"参考答案：{result.reference_answer}")
	print(f"评分标准：correctness={result.grading_criteria.correctness.max_score}, "
	      f"completeness={result.grading_criteria.completeness.max_score}, "
	      f"clarity={result.grading_criteria.clarity.max_score}")
