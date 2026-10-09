"""GUI 自动化编排器 — VLM 驱动的 ReAct 循环引擎。

职责：组合视觉决策（ToolVLMClient）和键鼠执行（Window / Input → ToolRegistry），
通过 VLM Function Calling 驱动完整的「观察 → 思考 → 行动」闭环。

核心循环：
  截图 → 内层 ReAct（VLM 看图决策 → 调用工具 → 结果回传 → 链式操作 → 纯文本结束）
  → 如有新消息则再次截图 → ...

设计原则：
  - VLM 是自主决策者：看图判断是否需要回复，自主提取会话并调用工具
  - generate_reply 封装了「分类 → 策略 → 生成回复」流水线，VLM 直接传入提取的会话
  - 所有工具通过 ToolRegistry 统一管理
  - 工具 Schema 动态渲染到系统提示词，而非硬编码
  - wait 由编排器自动执行，不暴露给 VLM
  - 所有工具均为无状态设计
"""

from __future__ import annotations

import json
import re
import time
import traceback
from dataclasses import dataclass
from typing import Any

from openai.types.chat import (
	ChatCompletionAssistantMessageParam,
	ChatCompletionMessageFunctionToolCall,
	ChatCompletionMessageFunctionToolCallParam,
	ChatCompletionMessageParam,
	ChatCompletionSystemMessageParam,
	ChatCompletionToolMessageParam,
	ChatCompletionUserMessageParam,
)

from inherit.agents.eshop_service.message_classifier import MessageClassifier
from inherit.agents.eshop_service.models.conversation import Conversation, ConversationMessage
from inherit.agents.eshop_service.models.types import ResponseMode
from agents.eshop_service.reply_generator import ReplyGenerator
from inherit.agents.eshop_service.strategy_engine import StrategyEngine
from inherit.agents.eshop_service.tools.input import Input
from inherit.agents.eshop_service.tools.window import ScreenshotResult, Window, WindowInfo
from inherit.llm.tool_registry import ToolRegistry, ToolDef
from inherit.prompt.prompt_manager import PromptManager
from inherit.utils.path import get_prj_root
from inherit.vlm.tool_vlm_client import ToolVLMClient


# ═══════════════════════════════════════════════════════════════════════
# 回复决策 DTO
# ═══════════════════════════════════════════════════════════════════════


@dataclass
class ReplyDecision:
	"""回复决策结果 — 穷举所有不回复原因的结构化 DTO。

	仅 reply_text 非空时为正常回复；其余 bool 字段穷举不回复原因。
	"""

	reply_text: str | None = None
	no_messages: bool = False
	customer_not_spoken: bool = False
	ignored: bool = False
	needs_human: bool = False


# ═══════════════════════════════════════════════════════════════════════
# GUI 编排器
# ═══════════════════════════════════════════════════════════════════════


class GUIReplyAgent:
	"""GUI 自动化编排器 — VLM 驱动的 ReAct 循环引擎。

	VLM 直接观察截图，通过 Function Calling 调用执行工具
	（click / type_text / scroll），每步只需一次 VLM 调用。
	回复内容由独立的回复流水线（分类→策略→生成）产生。

	使用方式：
		agent = GUIReplyAgent(
			vlm=tool_vlm_client,
			pm=prompt_manager,
			classifier=message_classifier,
			strategy_engine=strategy_engine,
			reply_generator=reply_generator,
			max_steps=30,
		)
		result = agent.run()
	"""


	def __init__(
			self,
			vlm: ToolVLMClient,
			pm: PromptManager,
			classifier: MessageClassifier,
			strategy_engine: StrategyEngine,
			reply_generator: ReplyGenerator,
			max_steps: int = 50,
			verbose: bool = True,
	) -> None:
		"""初始化编排器。

		Args:
			vlm: 支持 Function Calling 的 VLM 客户端。
			pm: Prompt 管理器（inherit）。
			classifier: 消息分类器。
			strategy_engine: 策略引擎。
			reply_generator: 回复生成器。
			max_steps: 最大 ReAct 循环步数。
			verbose: 是否输出详细日志。
		"""
		self._vlm: ToolVLMClient = vlm
		self._pm: PromptManager = pm
		self._window: Window = Window(get_prj_root() / "tmp")
		self._classifier: MessageClassifier = classifier
		self._strategy_engine: StrategyEngine = strategy_engine
		self._reply_generator: ReplyGenerator = reply_generator
		self._max_steps: int = max_steps
		self._verbose: bool = verbose

		# 工具注册中心 — 管理所有工具的 schema 与执行路由
		self._registry: ToolRegistry = ToolRegistry()

		for td in Input().to_tool_defs():
			self._registry.register(td)

		# generate_reply — 基于 VLM 提取的沟通记录生成回复
		reply_tool: ToolDef = self._create_generate_reply_tool()
		self._registry.register(reply_tool)

		# 运行时状态
		self._step_count: int = 0
		self._current_window_info: WindowInfo | None = None
		self._last_generated_reply: str | None = None
		self._last_sent_text: str | None = None
		self._awaiting_send_verification: bool = False


	# ── 内部工具方法 ──────────────────────────────────────

	def _log(self, msg: str) -> None:
		"""verbose=True 时打印消息。"""
		if self._verbose:
			print(msg)


	def _generate_reply(
			self,
			conversation: Conversation,
			customer_context: dict[str, Any] | None = None,
	) -> ReplyDecision:
		"""基于提取的沟通记录，通过分类→策略→生成流水线生成回复。

		Args:
			conversation: 当前截图提取的沟通记录。

		Returns:
			ReplyDecision，穷举所有不回复原因；仅 reply_text 非空时表示可自动回复。
		"""
		messages = conversation.messages
		if not messages:
			return ReplyDecision(no_messages=True)

		# 最后一条消息非客户发送 → 客户未发新消息，无需回复
		if messages[-1].role != "customer":
			return ReplyDecision(customer_not_spoken=True)

		classification = self._classifier.classify(messages)
		strategy = self._strategy_engine.decide(messages, classification)

		if strategy.response_mode == ResponseMode.IGNORE:
			return ReplyDecision(ignored=True)

		if strategy.response_mode == ResponseMode.HUMAN:
			return ReplyDecision(needs_human=True)

		try:
			reply: str = self._reply_generator.generate(
				messages,
				classification,
				strategy,
				customer_context=customer_context,
			)
		except Exception as e:
			self._log(f"  ⚠️ 回复生成失败: {e}")
			return ReplyDecision(needs_human=True)
		return ReplyDecision(reply_text=reply)


	def _handle_generate_reply(
		self,
		messages: list[dict[str, str]],
		customer_context: dict[str, Any] | None = None,
	) -> str:
		"""generate_reply 工具的执行函数。

		由 VLM 从截图中提取沟通记录后作为参数传入，
		后端流水线自动完成「分类→策略→生成回复」。

		Args:
			messages: VLM 从截图聊天区提取的沟通记录。

		Returns:
			结构化结果文本，供 VLM 根据结果执行后续操作：
			- 有回复时：回复文本（VLM 下一步输入并发送）
			- 需人工时：明确指示 VLM 在输入框输入 [需人工介入]
			- 无需回复时：说明原因
		"""
		if not messages:
			return "聊天区暂无消息记录，无需回复。"

		conversation_messages = [
			ConversationMessage(role=m["role"], content=m["content"])
			for m in messages
		]
		conversation = Conversation(messages=conversation_messages)

		self._log(f"  💬 收到沟通记录: {len(messages)} 条")

		decision: ReplyDecision = self._generate_reply(conversation, customer_context)

		if decision.reply_text:
			self._last_generated_reply = decision.reply_text
			self._log(f"  ✏️ 生成回复: {decision.reply_text[:120]}{'...' if len(decision.reply_text) > 120 else ''}")
			return decision.reply_text

		# 穷举不回复原因 → 返回结构化说明文本
		reasons: list[str] = []
		if decision.no_messages:
			reasons.append("聊天区无消息记录")
		if decision.customer_not_spoken:
			reasons.append("客户尚未发送新消息")
		if decision.ignored:
			reasons.append("该消息被识别为垃圾广告，已忽略")
		if decision.needs_human:
			reasons.append("需要人工客服介入")

		result: str = "；".join(reasons)
		self._log(f"  ⏸️ {result}")

		if decision.needs_human:
			return f"需要人工介入（原因: {result}）。请将 [需人工介入] 粘贴到输入框，不要发送。"

		return f"当前无需回复（{result}）。"


	# ── 工具封装 ──────────────────────────────────────────

	def _create_generate_reply_tool(self) -> ToolDef:
		"""创建 generate_reply 工具定义。

		VLM 从截图中提取沟通记录后，通过此工具调用后端流水线
		自动完成「分类→策略→生成回复」全流程。

		Returns:
			ToolDef，name="generate_reply"。
		"""
		return ToolDef(
			name="generate_reply",
			description=(
				"根据从截图聊天区提取的客户沟通记录，"
				"自动分析客户意图并生成回复话术。"
				"可能返回：①可自动回复的文本 ②需人工介入 ③无需回复。"
				"调用时机：已从截图聊天区提取到客户沟通记录，需要生成回复时。"
			),
			parameters={
				"messages": {
						"type": "array",
						"description": (
							"从截图聊天区按时间顺序提取的沟通记录列表。"
							"消息位于左侧为 customer（买家），位于右侧为 assistant（客服）。"
						),
						"items": {
							"type": "object",
							"properties": {
								"role": {
									"type": "string",
									"enum": ["customer", "assistant"],
									"description": "发言者身份",
								},
								"content": {
									"type": "string",
									"description": "消息的完整原文",
								},
							},
							"required": ["role", "content"],
						},
				},
				"customer_context": {
					"type": "object",
					"description": "从右侧客户和订单面板提取的业务事实；看得到时必须传入。",
					"properties": {
						"customer_name": {"type": "string", "description": "客户姓名"},
						"order_id": {"type": "string", "description": "订单号"},
						"order_status": {"type": "string", "description": "订单状态"},
						"product_name": {"type": "string", "description": "订单中的商品名称"},
						"ordered_size": {"type": "string", "description": "原购买尺码"},
						"ordered_color": {"type": "string", "description": "原购买颜色"},
					},
				},
			},
			required=["messages"],
			func=self._handle_generate_reply,
		)


	# ── 公开方法 ────────────────────────────────────────────

	def run(self) -> None:
		"""启动 VLM 驱动的 ReAct 循环，执行 GUI 自动化消息处理。

		VLM 自主决策何时调用 generate_reply 生成回复话术、
		何时执行 GUI 操作（click / type_text / scroll）。

		流程：
		  1. 加载系统提示词（动态注入工具 Schema）
		  2. 外层循环（每轮一次截图）：
		     a) 定位窗口 → b) 截图
		     c) 内层 ReAct（同一截图内 VLM ↔ 工具多轮交互）：
		        VLM 看图决策 → 调用工具 → 结果回传 → VLM 继续决策
		        → 直到 VLM 纯文本输出（如"已将回复输入并发送"）
		  3. VLM 纯文本输出 → 结束

		Returns:
			最终结果描述文本。
		"""

		# 每个用户都是一次独立运行，不能沿用上一位用户的步数和验证状态
		self._step_count = 0
		self._last_generated_reply = None
		self._last_sent_text = None
		self._awaiting_send_verification = False

		# 1) 获取全部工具，通过 Jinja2 模板渲染工具简要描述
		all_tools: list[ToolDef] = self._registry.list()
		system_prompt: str = self._pm.render(
			"agents/eshop_service/gui_reply_agent/system.j2",
			tools=all_tools,
		)

		self._log(
			"=" * 60 + "\n"
			           f"🚀 GUI 自动化编排器 启动 (VLM-FC Agent)\n"
			           f"   VLM: {self._vlm.info()}\n"
			           f"   最大步数: {self._max_steps}\n"
			           f"   工具: {[t.name for t in all_tools]}\n"
			           "=" * 60
		)

		# 2) VLM 驱动的 ReAct 循环（外层：每次截图一轮）
		while self._step_count < self._max_steps:
			self._log(f"── Step {self._step_count + 1} ──")

			# a) 先将 Chrome 置前，避免截图区域被 VS Code 或终端覆盖
			try:
				self._window.activate()
			except RuntimeError as e:
				raise RuntimeError(f"❌ 无法将工作台置于前台: {e}")

			# b) 定位浏览器窗口
			try:
				self._current_window_info = self._window.find()
			except (ValueError, RuntimeError) as e:
				raise RuntimeError(f"❌ 窗口定位失败: {e}")

			self._log(f"🪟 窗口: {self._current_window_info.title} (id={self._current_window_info.window_id})")

			# c) 截图
			try:
				screenshot: ScreenshotResult = self._window.screenshot(self._current_window_info.window_id)
			except (ValueError, RuntimeError) as e:
				raise RuntimeError(f"❌ 截图失败: {e}")

			openai_tools: list = [tool.to_openai_tool() for tool in all_tools]

			# 每轮截图构建全新消息列表
			if self._awaiting_send_verification:
				user_instruction = (
					"请仅验证上一条客服回复是否已经作为右侧客服气泡出现在聊天区。"
					f"实际粘贴发送的文本开头是：{(self._last_sent_text or self._last_generated_reply or '')[:80]}。"
					f"实际文本结尾是：{(self._last_sent_text or self._last_generated_reply or '')[-100:]}。"
					"页面可能把 Markdown 标记渲染成样式，匹配可忽略星号、换行和表情的显示差异。"
					"聊天区可能自动滚动到底部，开头不可见；只要可见的正文结尾或关键事实与目标一致，也应判定成功。"
					"不要处理客户随后产生的新消息，不要再次调用 generate_reply。"
					"如果已经出现，直接输出“发送验证成功”；否则说明失败原因。"
				)
			else:
				user_instruction = (
					"请查看当前客服工作台截图，判断聊天区是否有客户新消息需要处理。"
					"调用 generate_reply 时，除 messages 外，还要把右侧客户与订单面板中可见的事实"
					"放入 customer_context。"
					"如需发送回复，请在同一次响应中批量输出多个工具调用"
					"（clipboard_write + click + clipboard_paste + click 发送按钮），"
					"不要逐个操作、多次往返调用。"
				)

			messages: list[ChatCompletionMessageParam] = [
				ChatCompletionSystemMessageParam(role="system", content=system_prompt),
				ChatCompletionUserMessageParam(
					role="user",
					content=user_instruction,
				),
			]

			# c) 内层 ReAct：同一截图内 VLM ↔ 工具 多轮交互
			while self._step_count < self._max_steps:
				content, tool_calls = self._vlm.chat_with_image_and_tools(
					image=screenshot.image,
					messages=messages,
					tools=openai_tools,
					tool_choice="auto",
				)

				if not tool_calls:
					# VLM 纯文本 → 本截图处理完毕
					self._log(f"  ✅ 处理完成: {content or '(空)'}")
					return

				# 构建 assistant 消息（含工具调用）
				assistant_tool_calls: list[ChatCompletionMessageFunctionToolCallParam] = [
					ChatCompletionMessageFunctionToolCallParam(
						id=tc.id,
						type="function",
						function={"name": tc.function.name, "arguments": tc.function.arguments},
					)
					for tc in tool_calls
				]
				messages.append(
					ChatCompletionAssistantMessageParam(
						role="assistant",
						content=content,
						tool_calls=assistant_tool_calls,
					)
				)

				# 执行工具并将结果回传 VLM
				tool_names_in_batch: set[str] = {tc.function.name for tc in tool_calls}
				for tc in tool_calls:
					tool_result: str = self._execute_tool(tc)
					self._step_count += 1
					self._log(f"  🔧 {tc.function.name} → {tool_result[:120]}")
					messages.append(
						ChatCompletionToolMessageParam(
							role="tool",
							tool_call_id=tc.id,
							content=tool_result,
						)
					)
					time.sleep(1)

				# 发送动作完成后必须跳出内层循环，重新截图验证页面真实状态
				if (
					self._last_generated_reply
					and "clipboard_paste" in tool_names_in_batch
					and "click" in tool_names_in_batch
				):
					self._awaiting_send_verification = True
					self._log("  🔎 发送动作已执行，等待页面更新后重新截图验证")
					time.sleep(2)
					break

		raise RuntimeError(f"⚠️ 达到最大步数限制 ({self._max_steps})，强制结束")


	# ── 内部：工具执行路由 ─────────────────────────────────

	def _execute_tool(self, tc: ChatCompletionMessageFunctionToolCall) -> str:
		"""路由并执行单个工具调用。

		Args:
			tc: ChatCompletionMessageFunctionToolCall。

		Returns:
			工具执行结果的文本描述。
		"""
		name: str = tc.function.name

		try:
			args: dict[str, Any] = json.loads(tc.function.arguments)
		except json.JSONDecodeError as e:
			return f"工具参数 JSON 解析失败: {e}。原始参数: {tc.function.arguments[:200]}"

		# 坐标转换：VLM 返回截图相对坐标 → 绝对屏幕坐标
		if name == "click":
			window_info: WindowInfo = self._window.find()
			# seed 模型标注时, 会归一化到 1000*1000 的比例坐标，取值范围 [0, 999]
			# 文档见: https://console.volcengine.com/ark/region:cn-beijing/docs/82379/1616136?lang=zh
			# 个别响应会把两个坐标合并成 "730 949"，统一从 x/y 字段中提取前两个数。
			coordinate_values = re.findall(
				r"-?\d+(?:\.\d+)?",
				f"{args.get('x', '')} {args.get('y', '')}",
			)
			if len(coordinate_values) < 2:
				return f"点击坐标格式错误: x={args.get('x')!r}, y={args.get('y')!r}"
			rel_x = max(0, min(1000, round(float(coordinate_values[0]))))
			rel_y = max(0, min(1000, round(float(coordinate_values[1]))))
			args["x"] = round(rel_x / 1000 * window_info.width) + window_info.x
			args["y"] = round(rel_y / 1000 * window_info.height) + window_info.y
		elif name == "clipboard_write" and isinstance(args.get("text"), str):
			# 验证必须比较真正粘贴的正文，而不是 generate_reply 可能附带的说明性包装。
			self._last_sent_text = args["text"]

		try:
			return self._registry.execute(name, **args)
		except KeyError:
			return f"未知工具: {name}"
		except Exception as e:
			traceback.print_exc()
			return f"执行失败: {type(e).__name__}: {e}"
