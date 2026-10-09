"""回复生成器 — 基于分类结果和策略决策，通过 Tool Calling 生成客服回复。

核心流程：
1. 渲染 reply_generator.j2 提示词模板（注入对话、分类、策略）
2. 发送给 LLM（带工具定义），模型决定是否需要查询外部数据
3. 若模型调用工具 → 执行 Mock 查询 → 结果追加到消息历史 → 继续对话
4. 直到模型生成最终回复文本后返回

使用示例::

    from agent.eshop_service.reply_generator import ReplyGenerator, build_reply_generator

    gen = build_reply_generator(cfg)
    reply = gen.generate(conversation, classification_result, strategy)
    print(reply)
"""

import json
from typing import Any

from openai.types.chat import (
	ChatCompletionAssistantMessageParam,
	ChatCompletionMessageFunctionToolCall,
	ChatCompletionMessageFunctionToolCallParam,
	ChatCompletionMessageParam,
	ChatCompletionToolMessageParam,
	ChatCompletionToolParam,
	ChatCompletionUserMessageParam,
)

from agents.eshop_service.models.conversation import ConversationMessage
from agents.eshop_service.models.types import HandlingStrategy, MessageClassificationResult
from agents.eshop_service.sal.api import TOOLS
from inherit.llm.tool_client import ToolLLMClient
from inherit.llm.tool_registry import ToolDef
from inherit.prompt.prompt_manager import PromptManager


class ReplyGenerator:
	"""客服回复生成器 — 基于 LLM Tool Calling 的智能回复。

	职责：
	- 接收对话上下文 + 分类结果 + 策略决策
	- 自动调用 mock 工具查询商品/订单/物流/售后等外部数据
	- 生成不含幻觉的专业客服回复
	"""


	def __init__(
			self,
			llm: ToolLLMClient,
			pm: PromptManager,
			max_tool_rounds: int = 5,
			verbose: bool = True,
	) -> None:
		"""初始化回复生成器。

		:param llm:             支持 chat_with_tools 的 ToolLLMClient
		:param pm:              PromptManager
		:param max_tool_rounds: 工具调用循环最大轮次
		:param verbose:         是否打印详细过程
		"""
		self._llm: ToolLLMClient = llm
		self._pm: PromptManager = pm
		self._max_tool_rounds: int = max_tool_rounds
		self._verbose: bool = verbose


	def _log(self, msg: str) -> None:
		"""verbose=True 时打印消息。"""
		if self._verbose:
			print(msg)


	def generate(
			self,
			conversation: list[ConversationMessage],
			classification: MessageClassificationResult,
			strategy: HandlingStrategy,
	) -> str:
		"""生成客服回复文本。

		Args:
			conversation: 完整会话历史
			classification: 消息分类结果
			strategy: 策略引擎的最终决策

		Returns:
			生成的客服回复文本
		"""
		prompt = self._pm.render(
			"agents/eshop_service/reply_generator/generate.j2",
			conversation=[m.model_dump() for m in conversation],
			classification=classification,
			strategy=strategy,
		)

		messages: list[ChatCompletionMessageParam] = [
			ChatCompletionUserMessageParam(role="user", content=prompt),
		]

		tools: list[ChatCompletionToolParam] = [t.to_openai_tool() for t in TOOLS.values()]
		for _ in range(self._max_tool_rounds):
			content: str | None
			tool_calls: list[ChatCompletionMessageFunctionToolCall]
			content, tool_calls = self._llm.chat_with_tools(messages, tools)

			if not tool_calls:
				# 无 tool_calls → 模型直接回复
				if not content:
					raise RuntimeError("LLM 未生成回复内容")
				return content
			assistant_tool_calls: list[ChatCompletionMessageFunctionToolCallParam] = []
			for tc in tool_calls:
				item: ChatCompletionMessageFunctionToolCallParam = ChatCompletionMessageFunctionToolCallParam(
					id=tc.id,
					type="function",
					function={"name": tc.function.name, "arguments": tc.function.arguments},
				)
				assistant_tool_calls.append(item)

			assistant_msg: ChatCompletionAssistantMessageParam = ChatCompletionAssistantMessageParam(
				role="assistant",
				content=content,
				tool_calls=assistant_tool_calls,
			)
			messages.append(assistant_msg)

			for tc in tool_calls:
				tool_name: str = tc.function.name

				if tool_name not in TOOLS:
					tool_result: str = f"未知工具: {tool_name}"
					self._log(f"  🔧 [{tool_name}] → {tool_result}...")
					messages.append(
						ChatCompletionToolMessageParam(role="tool", tool_call_id=tc.id, content=tool_result)
					)
					continue

				tool_def: ToolDef = TOOLS[tool_name]
				try:
					args: dict[str, Any] = json.loads(tc.function.arguments)
				except json.JSONDecodeError as e:
					tool_result: str = f"工具参数 JSON 解析失败: {e}"
					self._log(f"  🔧 [{tool_name}] → {tool_result}...")
					messages.append(
						ChatCompletionToolMessageParam(role="tool", tool_call_id=tc.id, content=tool_result)
					)
					continue

				try:
					tool_result: str = tool_def.func(**args)
				except Exception as e:
					tool_result: str = f"工具执行失败: {e}"
					self._log(f"  🔧 [{tool_name}] → {tool_result}...")
					messages.append(
						ChatCompletionToolMessageParam(role="tool", tool_call_id=tc.id, content=tool_result)
					)
					continue

				self._log(f"  🔧 [{tool_name}] → {tool_result[:80]}...")
				messages.append(
					ChatCompletionToolMessageParam(role="tool", tool_call_id=tc.id, content=tool_result)
				)

		# 超出最大工具调用轮次仍未生成回复
		raise RuntimeError(
			f"工具调用超出最大轮次（{self._max_tool_rounds}），未能在限定轮次内生成回复"
		)


if __name__ == "__main__":
	from dataclasses import dataclass

	from agents.eshop_service.models.types import ResponseMode
	from config import Config
	from inherit.utils.path import get_prj_root

	cfg: Config = Config.from_yaml()

	llm: ToolLLMClient = ToolLLMClient(
		api_key=cfg.llm.api_key_env,
		base_url=cfg.llm.base_url,
		model=cfg.llm.model,
		temperature=cfg.generation.temperature,
		max_tokens=cfg.generation.max_tokens,
	)
	pm: PromptManager = PromptManager(get_prj_root() / "prompts")

	generator: ReplyGenerator = ReplyGenerator(llm, pm)


	@dataclass
	class _TestScenario:
		name: str
		messages: list[ConversationMessage]
		classification: MessageClassificationResult
		strategy: HandlingStrategy


	# 测试场景
	test_cases: list[_TestScenario] = [
		_TestScenario(
			name="商品查询",
			messages=[ConversationMessage(role="customer", content="红色连衣裙有M码吗？多少钱？")],
			classification=MessageClassificationResult(
				parent="售前咨询",
				name="商品查询",
				confidence=0.95,
				sentiment="中性",
				urgency="普通",
				key_info={"product_name": "红色连衣裙", "size": "M"},
			),
			strategy=HandlingStrategy(
				response_mode=ResponseMode.AUTO,
				need_product_query=True,
				action_hints=["查询商品信息", "查询库存"],
			),
		),
		_TestScenario(
			name="售后查询",
			messages=[
				ConversationMessage(role="customer", content="我的订单 ORD123456 已经签收了，但尺码不合适能换吗？")
			],
			classification=MessageClassificationResult(
				parent="售后问题",
				name="换货咨询",
				confidence=0.88,
				sentiment="中性",
				urgency="普通",
				key_info={"order_id": "ORD123456"},
			),
			strategy=HandlingStrategy(
				response_mode=ResponseMode.AUTO,
				need_order_query=True,
				action_hints=["查询订单信息", "查询换货政策"],
			),
		),
		_TestScenario(
			name="物流查询",
			messages=[ConversationMessage(role="customer", content="我的订单 ORD123457 到哪里了？")],
			classification=MessageClassificationResult(
				parent="售后问题",
				name="物流查询",
				confidence=0.95,
				sentiment="中性",
				urgency="普通",
				key_info={"order_id": "ORD123457"},
			),
			strategy=HandlingStrategy(
				response_mode=ResponseMode.AUTO,
				need_order_query=True,
				action_hints=["查询物流配送信息"],
			),
		),
		_TestScenario(
			name="愤怒投诉",
			messages=[ConversationMessage(role="customer", content="鞋子穿了三天就开胶了，你们卖的什么垃圾！我要退货！")],
			classification=MessageClassificationResult(
				parent="售后问题",
				name="退货投诉",
				confidence=0.92,
				sentiment="愤怒",
				urgency="紧急",
				key_info={"product_name": "鞋子", "issue": "开胶"},
			),
			strategy=HandlingStrategy(
				response_mode=ResponseMode.AUTO_WITH_ESCALATION,
				need_product_query=True,
				action_hints=["安抚情绪", "查询商品售后政策", "升级准备"],
			),
		),
	]

	for case in test_cases:
		print(f"\n{'=' * 60}")
		print(f"📌 场景: {case.name}")
		print(f"👤 客户: {case.messages[0].content}")
		print(f"{'=' * 60}")

		reply: str = generator.generate(case.messages, case.classification, case.strategy)
		print(f"\n💬 回复:\n{reply}")
