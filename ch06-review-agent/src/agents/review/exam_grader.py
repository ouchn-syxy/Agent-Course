"""批改智能体 — 对学生的答案进行三维评分并给出反馈。

借鉴 ch05 的 QualityGate 的评分逻辑。
支持工具调用：search_fact_check 进行事实核查。
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

from agents.review.models.study_state import GradingResult
from agents.review.question_generator import GeneratedQuestion
from agents.review.tools.search_fact_check import SearchFactCheck
from inherit.llm.tool_client import ToolLLMClient
from inherit.llm.tool_registry import ToolRegistry
from inherit.prompt.prompt_manager import PromptManager
from inherit.utils.model_render import render_model_code


class ExamGrader:
	"""批改智能体，支持工具调用进行事实核查。

	用法：
		grader = ExamGrader(
			llm_client, prompt_manager,
			search_fact_check=SearchFactCheck(...),
		)
		result = grader.grade(question_info, user_answer)

	工具调用流程：
		1. LLM 判断是否需要搜索验证学生答案中的关键陈述
		2. 如需核查 → 执行 search_fact_check → 结果追加到消息 → 重新评审
		3. LLM 不再调用工具 → 解析 JSON 评分结果
	"""


	def __init__(
		self,
		llm_client: ToolLLMClient,
		prompt_manager: PromptManager,
		*,
		search_fact_check: SearchFactCheck | None = None,
	) -> None:
		"""初始化批改智能体。

		Args:
			llm_client: 支持 Function Calling 的 LLM 客户端
			prompt_manager: Prompt 管理器
			search_fact_check: 事实核查工具实例，为 None 则不注册
		"""
		self._llm: ToolLLMClient = llm_client
		self._pm: PromptManager = prompt_manager

		self._registry: ToolRegistry = ToolRegistry()
		if search_fact_check is not None:
			self._registry.register(search_fact_check.to_tool_def())


	def grade(self, question_info: GeneratedQuestion, user_answer: str) -> GradingResult:
		"""批改学生答案。

		Args:
			question_info: QuestionGenerator.generate() 的返回值
			user_answer: 学生的答案文本

		Returns:
			GradingResult 对象
		"""
		system_prompt: str = self._pm.render(
			"agents/review/exam_grader/system.j2",
			grading_result_schema=render_model_code(GradingResult),
			tools=self._registry.list(),
		)

		user_prompt: str = self._pm.render(
			"agents/review/exam_grader/grade.j2",
			question_info=question_info,
			user_answer=user_answer,
		)

		messages: list[ChatCompletionMessageParam] = [
			ChatCompletionSystemMessageParam(role="system", content=system_prompt),
			ChatCompletionUserMessageParam(role="user", content=user_prompt),
		]

		tools: list = [t.to_openai_tool() for t in self._registry.list()]

		max_turns: int = 3
		for _ in range(max_turns):
			content, tool_calls = self._llm.chat_with_tools(messages, tools, temperature=0.2)
			if not tool_calls:
				if content:
					return GradingResult.model_validate_json(content)
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
			content="请基于以上工具返回的信息，直接输出最终 JSON 评分结果。不要再调用工具。",
		))
		json_raw: str = self._llm.chat_with_json(messages, temperature=0.2)
		result: GradingResult = GradingResult.model_validate_json(json_raw)
		return result


if __name__ == "__main__":
	from agents.review.models.study_state import DimensionScores
	from config import Config
	from inherit.utils.path import get_prj_root
	from agents.review.question_generator import (
		GradingCriteria,
		GradingCriteriaClarity,
		GradingCriteriaCompleteness,
		GradingCriteriaCorrectness,
	)
	from agents.review.tools.search_fact_check import SearchFactCheck

	config: Config = Config.from_yaml()
	pm: PromptManager = PromptManager(get_prj_root() / "prompts")
	llm: ToolLLMClient = ToolLLMClient(
		api_key=config.llm.api_key_env,
		base_url=config.llm.base_url,
		model=config.llm.model,
	)

	agent: ExamGrader = ExamGrader(
		llm, pm,
		search_fact_check=SearchFactCheck(
			tavily_api_key=config.tavily.api_key,
			max_results=config.tavily.max_results,
		),
	)
	question: GeneratedQuestion = GeneratedQuestion(
		question="请简述二叉树的三种遍历方式及其特点。",
		reference_answer="前序：根左右；中序：左根右；后序：左右根。",
		grading_criteria=GradingCriteria(
			correctness=GradingCriteriaCorrectness(max_score=5.0, description="遍历顺序是否正确"),
			completeness=GradingCriteriaCompleteness(max_score=3.0, description="是否覆盖三种遍历"),
			clarity=GradingCriteriaClarity(max_score=2.0, description="表达是否清晰"),
		),
		key_points=["三种遍历的定义", "递归/非递归实现"],
	)
	result: GradingResult = agent.grade(question, "前序遍历是根左右，中序遍历是左根右。")
	print(f"得分：{result.score}/10")
	print(f"反馈：{result.feedback}")
	ds: DimensionScores = result.dimension_scores
	print(f"维度得分：correctness={ds.correctness}, completeness={ds.completeness}, clarity={ds.clarity}")
	if result.strengths:
		print(f"优点：{result.strengths}")
	if result.weaknesses:
		print(f"不足：{result.weaknesses}")
