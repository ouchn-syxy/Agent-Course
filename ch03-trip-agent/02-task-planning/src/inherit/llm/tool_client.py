"""
支持 Function Calling 的 LLM 客户端。

继承 inherit.llm.client.LLMClient，新增 chat_with_tools() 方法，
将 tools 参数透传给 OpenAI SDK，返回 content 和 tool_calls 元组。

用法：
    from llm.tool_llm_client import ToolLLMClient
    llm = ToolLLMClient(...)
    content, tool_calls = llm.chat_with_tools(messages, tools)
"""

from __future__ import annotations

from collections.abc import Iterable

from json_repair import repair_json
from openai.types.chat import (
	ChatCompletionMessageParam,
	ChatCompletionToolChoiceOptionParam,
	ChatCompletionToolParam,
	ChatCompletionMessageFunctionToolCall,
)

from inherit.llm.client import LLMClient
from inherit.utils.retry import retry


class ToolLLMClient(LLMClient):
	"""支持 Function Calling 的 LLM 客户端，继承 LLMClient。

	新增 chat_with_tools() 方法，将 tools 参数透传给 OpenAI SDK，
	同时返回文本回复和 tool_calls。
	"""


	@retry(max_retries=3, delay_s=2.0)
	def chat_with_tools(
			self,
			messages: Iterable[ChatCompletionMessageParam],
			tools: Iterable[ChatCompletionToolParam],
			tool_choice: ChatCompletionToolChoiceOptionParam = "auto",
			temperature: float | None = None,
			top_p: float | None = None,
			max_tokens: int | None = None,
	) -> tuple[str | None, list[ChatCompletionMessageFunctionToolCall]]:
		"""
		发送消息并获取模型回复（可能包含 tool_calls）。

		与 chat() 的区别：附加 tools 参数，支持 Function Calling。
		当模型决定调用工具时，content 通常为 None，tool_calls 非空；
		当模型直接回复时，tool_calls 为 None，content 非空。
		网络层瞬时故障由 @retry 自动处理。

		Args:
			messages: OpenAI messages 格式列表。
			tools: OpenAI Function Calling tools 格式列表。
			tool_choice: 工具选择策略（"auto" / "none" / "required"）。
			temperature: 温度（None 则使用实例默认值）。
			top_p: 核采样阈值（None 则使用实例默认值）。
			max_tokens: 最大输出 token 数（None 则使用实例默认值）。

		Returns:
			(content, tool_calls) 元组：
			  - content: 模型文本回复（可能为 None）
			  - tool_calls: 工具调用列表，每项含 id/function.name/function.arguments
		"""
		completion = self._client.chat.completions.create(
			model=self.model,
			messages=messages,
			tools=tools,
			tool_choice=tool_choice,
			temperature=temperature if temperature is not None else self._temperature,
			top_p=top_p if top_p is not None else self._top_p,
			max_tokens=max_tokens if max_tokens is not None else self._max_tokens,
		)

		choice = completion.choices[0]
		message = choice.message

		content: str | None = message.content
		tool_calls: list[ChatCompletionMessageFunctionToolCall] = []

		if content is not None:
			content = repair_json(content)

		if message.tool_calls:
			for tc in message.tool_calls:
				if isinstance(tc, ChatCompletionMessageFunctionToolCall):
					tool_calls.append(tc)

		return content, tool_calls


if __name__ == "__main__":

	from typing import Any, Callable, List, Tuple
	import json

	from openai.types.chat import (
		ChatCompletionUserMessageParam,
		ChatCompletionAssistantMessageParam,
		ChatCompletionToolMessageParam,
		ChatCompletionMessageFunctionToolCallParam,
	)

	from config import Config


	# 1. 定义几个真实函数作为工具
	def get_weather(city: str) -> str:
		"""查询指定城市的天气信息（演示用模拟数据）。"""
		weather_data = {
			"北京": "晴天，32°C，湿度 45%，东南风 3 级",
			"上海": "多云转阵雨，28°C，湿度 75%，东风 4 级",
			"深圳": "雷阵雨，30°C，湿度 85%，南风 2 级",
			"杭州": "阴天，25°C，湿度 60%，北风 3 级",
		}
		return weather_data.get(city, f"暂无 {city} 的天气数据，请尝试其他城市。")


	def calculator(expression: str) -> str:
		"""计算数学表达式（支持 + - * / ** ^ 等基本运算，^ 自动转为 **）。"""
		import ast
		import operator as op

		# 将 ^ 替换为 **（方便日常习惯）
		expression = expression.replace("^", "**")

		allowed_ops: dict[type, Any] = {
			ast.Add: op.add, ast.Sub: op.sub,
			ast.Mult: op.mul, ast.Div: op.truediv,
			ast.Pow: op.pow, ast.USub: op.neg,
		}


		def _eval(node: ast.AST) -> Any:
			match node:
				case ast.Expression(body=body):
					return _eval(body)
				case ast.Constant(value=value):
					return value
				case ast.BinOp(left=left, op=op_node, right=right):
					return allowed_ops[type(op_node)](_eval(left), _eval(right))
				case ast.UnaryOp(op=op_node, operand=operand):
					return allowed_ops[type(op_node)](_eval(operand))
				case _:
					raise ValueError(f"不支持的运算: {ast.dump(node)}")


		try:
			result = _eval(ast.parse(expression, mode="eval"))
			return str(result)
		except Exception as e:
			return f"计算错误: {e}"


	# 2. 构建 OpenAI Function Calling tools schema

	tool_map: dict[str, Callable[..., str]] = {"get_weather": get_weather, "calculator": calculator}
	tools: list[ChatCompletionToolParam] = [
		{
			"type": "function",
			"function": {
				"name": "get_weather",
				"description": "查询指定城市的实时天气信息",
				"parameters": {
					"type": "object",
					"properties": {
						"city": {"type": "string", "description": "城市名称，如 北京、上海、深圳"},
					},
					"required": ["city"],
				},
			},
		},
		{
			"type": "function",
			"function": {
				"name": "calculator",
				"description": "计算数学表达式的结果，支持加减乘除和幂运算",
				"parameters": {
					"type": "object",
					"properties": {
						"expression": {"type": "string", "description": "数学表达式，如 '(3 + 5) * 2'"},
					},
					"required": ["expression"],
				},
			},
		},
	]

	# 3. 加载配置并创建 ToolLLMClient
	cfg = Config.from_yaml()
	llm = ToolLLMClient(
		api_key=cfg.llm.api_key_env,
		base_url=cfg.llm.base_url,
		model=cfg.llm.model,
		temperature=cfg.generation.temperature,
		max_tokens=cfg.generation.max_tokens,
	)

	print(f"🤖 模型: {cfg.llm.model}")
	print(f"🔧 已注册工具: get_weather, calculator")
	print()

	# 4. 测试用例 — 覆盖多种场景
	test_cases = [
		"北京今天天气怎么样？",  # 天气查询
		"帮我算一下 (128 + 256) * 3 / 2 等于多少？",  # 四则运算
		"深圳和杭州哪个城市更热？",  # 连查两个城市天气
		"2 的 10 次方是多少？",  # 幂运算
		"今天适合做户外运动吗，推荐一个城市",  # 天气 + 综合分析（模型决定查哪个城市）
		"你好，请问你能做什么？",  # 无需调用工具
	]

	for i, query in enumerate(test_cases, 1):
		print(f"{'=' * 60}")
		print(f"📝 测试 {i}: {query}")
		print(f"{'=' * 60}")

		messages: list[ChatCompletionMessageParam] = [ChatCompletionUserMessageParam(role="user", content=query)]

		# 第一轮：LLM 决定是否调用工具
		content, tool_calls = llm.chat_with_tools(messages, tools)

		if tool_calls:
			# 先执行所有工具调用，收集结果
			assistant_tool_calls: list[ChatCompletionMessageFunctionToolCallParam] = []
			tool_results: List[Tuple[str, str]] = []

			for tc in tool_calls:
				fn_name = tc.function.name
				fn_args = json.loads(tc.function.arguments)
				print(f"  🔧 LLM 决定调用: {fn_name}({json.dumps(fn_args, ensure_ascii=False)})")

				result = tool_map[fn_name](**fn_args)
				print(f"  📦 工具返回: {result}")

				assistant_tool_calls.append(ChatCompletionMessageFunctionToolCallParam(
					id=tc.id,
					type="function",
					function={"name": fn_name, "arguments": tc.function.arguments},
				))
				tool_results.append((tc.id, result))

			# 构造 assistant 消息（所有 tool_calls 合并在一条消息中）
			messages.append(ChatCompletionAssistantMessageParam(
				role="assistant",
				content=content,
				tool_calls=assistant_tool_calls,
			))

			# 逐个追加 tool 结果消息
			for tool_call_id, result in tool_results:
				messages.append(ChatCompletionToolMessageParam(
					role="tool",
					tool_call_id=tool_call_id,
					content=result,
				))

			# 第二轮：LLM 根据工具结果生成最终回复
			final_content, _ = llm.chat_with_tools(messages, tools)
			print(f"  💬 最终回复: {final_content}")
		else:
			print(f"  💬 直接回复: {content}")

		print()
