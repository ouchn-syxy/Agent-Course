"""策略引擎 — 基于分类结果决定消息的处理策略。

## 决策流程

1. 验证分类结果的合法性（大类是否存在）
2. 查找子类配置，获取预设的 HandlingStrategy
3. 若策略为 auto_with_escalation 模式，调用 LLM 评估是否需要升级为转人工
4. 若消息紧急度为"紧急"且当前为 auto 模式，强制升级为转人工
5. 返回最终策略

输入：ConversationMessage 列表 + MessageClassificationResult
输出：HandlingStrategy（response_mode / 操作提示 / 回复模板）
"""

from typing import Optional

from openai.types.chat import ChatCompletionMessageParam, ChatCompletionUserMessageParam
from pydantic import BaseModel, Field

from inherit.agents.eshop_service.message_category_manager import MessageCategoryManager
from inherit.agents.eshop_service.models.conversation import ConversationMessage
from inherit.agents.eshop_service.models.types import (
	HandlingStrategy,
	MessageClassificationResult,
	MessageSubCategory,
	ResponseMode,
)
from inherit.llm.client import LLMClient
from inherit.prompt.prompt_manager import PromptManager
from inherit.utils.model_render import render_model_code


class EscalationDecision(BaseModel):
	"""升级决策结构 — 由 LLM 返回，用于 auto_with_escalation 模式下的转人工判定。

	当子类策略配置了 escalation_rules 时，策略引擎会调用 LLM 综合会话上下文、
	分类结果和升级规则来评估是否需要转人工，结果由此模型承载。
	"""

	should_escalate: bool = Field(description="是否需要转人工")
	reason: str = Field(description="判断理由")


class StrategyEngine:
	"""策略引擎 — 基于分类配置和 LLM 综合评估，决定消息的最终处理策略。

	核心职责：
	- 根据分类结果查找子类配置中的预设策略（自动回复 / 转人工 / 忽略等）
	- 对于可升级模式，调用 LLM 评估是否需要转人工
	- 紧急消息自动升级为转人工

	使用示例::

		from pathlib import Path
		from strategy_engine import StrategyEngine
		from agent.eshop_service.message_category_manager import MessageCategoryManager

		mgr = MessageCategoryManager(Path("data/eshop_service/message_category"))
		engine = StrategyEngine(mgr, llm_client, prompt_manager)
		decision = engine.decide(conversation, classification_result)
		if decision.response_mode == ResponseMode.HUMAN:
			print(f"需转人工: {decision.escalation_reason}")
	"""


	def __init__(self, category_mgr: MessageCategoryManager, llm: LLMClient, pm: PromptManager) -> None:
		"""初始化策略引擎。

		Args:
			category_mgr: 消息分类管理器，提供大类/子类配置及策略规则
			llm: LLM 客户端，用于升级判定时的 AI 评估
			pm: Prompt 管理器，用于渲染升级评估的提示词模板
		"""
		self._mgr: MessageCategoryManager = category_mgr
		self._llm: LLMClient = llm
		self._pm: PromptManager = pm


	def decide(self, conversation: list[ConversationMessage], result: MessageClassificationResult) -> HandlingStrategy:
		"""根据分类结果和沟通记录决定处理策略。

		决策步骤：
		1. 验证大类合法性 — 未知类型默认转人工
		2. 查找子类预设策略
		3. auto_with_escalation 模式下，调用 LLM 评估升级条件
		4. 紧急 + auto 模式强制升级为转人工

		Args:
			conversation: 完整会话消息列表
			result: 消息分类器的分类结果

		Returns:
			最终处理策略（response_mode / 操作提示 / 回复模板等）
		"""

		# 第一步：验证大类是否存在
		if not self._mgr.find_core(result.parent):
			print(f"[策略引擎] 未知消息类型: {result.parent}，使用默认策略")
			return HandlingStrategy(
				response_mode=ResponseMode.HUMAN,
				need_product_query=False,
				need_order_query=False,
				action_hints=["未知类型", "标记转人工"],
				escalation_reason=f"无法识别的消息类型: {result.parent}",
			)

		# 第二步：查找子类预设策略，未命中则使用默认策略
		sub_category: Optional[MessageSubCategory] = self._mgr.find_sub(result.name, result.parent)
		strategy: HandlingStrategy = sub_category.strategy if sub_category else HandlingStrategy()

		# 第三步：可升级模式下，由 LLM 评估是否需要转为人工
		if strategy.response_mode == ResponseMode.AUTO_WITH_ESCALATION:
			decision: EscalationDecision = self._assess_escalation(conversation, result, sub_category)
			if decision.should_escalate:
				strategy.response_mode = ResponseMode.HUMAN
				parts: list[str | None] = [strategy.escalation_reason, decision.reason]
				parts: list[str] = [p for p in parts if p is not None]
				strategy.escalation_reason = " | ".join(parts)

		# 第四步：紧急消息在自动模式下强制升级为转人工
		if strategy.response_mode == ResponseMode.AUTO and result.urgency == "紧急":
			strategy.response_mode = ResponseMode.HUMAN
			parts: list[str | None] = [strategy.escalation_reason, "紧急消息，自动转人工"]
			parts: list[str] = [p for p in parts if p is not None]
			strategy.escalation_reason = " | ".join(parts)

		return strategy


	def _assess_escalation(
			self,
			conversation: list[ConversationMessage],
			classification: MessageClassificationResult,
			sub_category: Optional[MessageSubCategory] = None,
	) -> EscalationDecision:
		"""评估是否需要升级为转人工 — 由 LLM 综合判断严重性、权限和上下文。

		工作流程：
		1. 从子类配置中提取升级规则（condition / action）
		2. 渲染 escalation_evaluator.j2 提示词模板
		3. 调用 LLM 输出结构化 EscalationDecision
		4. 异常时安全降级：默认不转人工

		Args:
			conversation: 完整沟通记录，用于上下文感知的升级判定
			classification: 消息分类结果
			sub_category: 子类配置（可选），包含 escalation_rules 升级规则列表

		Returns:
			EscalationDecision，包含是否升级及判断理由
		"""
		if sub_category is None:
			return EscalationDecision(should_escalate=False, reason="无子类配置")

		escalation_rules: list[dict[str, str]] = [
			{"condition": r.condition, "action": r.action}
			for r in sub_category.strategy.escalation_rules
		]

		prompt: str = self._pm.render(
			"agents/eshop_service/strategy_engine/evaluate_escalation.j2",
			escalation_decision_schema=render_model_code(EscalationDecision),
			conversation=conversation,
			classification=classification,
			escalation_rules=escalation_rules,
		)

		messages: list[ChatCompletionMessageParam] = [
			ChatCompletionUserMessageParam(role="user", content=prompt)
		]

		try:
			json_text: str = self._llm.chat_with_json(messages)
			decision: EscalationDecision = EscalationDecision.model_validate_json(json_text)
			if decision.should_escalate:
				print(f"[策略引擎] LLM 判定转人工: {decision.reason}")
			return decision
		except Exception as e:
			print(f"[策略引擎] 升级评估失败: {e}，默认不转人工")
			return EscalationDecision(should_escalate=False, reason=str(e))


if __name__ == "__main__":

	# ── 初始化依赖 ──
	from dataclasses import dataclass

	from config import Config
	from inherit.utils.path import get_prj_root

	cfg: Config = Config.from_yaml()
	cat_mgr: MessageCategoryManager = MessageCategoryManager(
		get_prj_root() / "data" / "eshop_service" / "message_category"
	)

	llm: LLMClient = LLMClient(
		api_key=cfg.llm.api_key_env,
		base_url=cfg.llm.base_url,
		model=cfg.llm.model,
		temperature=cfg.generation.temperature,
		max_tokens=cfg.generation.max_tokens,
	)
	pm: PromptManager = PromptManager(get_prj_root() / "prompts")
	engine: StrategyEngine = StrategyEngine(cat_mgr, llm, pm)

	# ── 回复模式与 emoji 映射 ──
	_MODE_EMOJI: dict[ResponseMode, str] = {
		ResponseMode.AUTO: "✅ 自动回复",
		ResponseMode.AUTO_WITH_ESCALATION: "⚠️ 自动回复（可升级）",
		ResponseMode.HUMAN: "❌ 转人工",
		ResponseMode.IGNORE: "🚫 忽略",
	}


	# ── 演示场景：预定义分类结果，与 classifier 解耦 ──
	@dataclass
	class _TestScenario:
		name: str
		messages: list[ConversationMessage]
		classification: MessageClassificationResult


	test_cases: list[_TestScenario] = [
		_TestScenario(
			name="库存查询",
			messages=[ConversationMessage(role="customer", content="这个红色M码还有货吗？")],
			classification=MessageClassificationResult(
				parent="售前咨询",
				name="库存查询",
				confidence=0.95,
				sentiment="中性",
				urgency="普通",
				key_info={"product_name": "红色", "size": "M"},
			),
		),
		_TestScenario(
			name="退货退款",
			messages=[ConversationMessage(role="customer", content="鞋子穿了三天就开胶了，我要退货！")],
			classification=MessageClassificationResult(
				parent="售后服务",
				name="退货退款",
				confidence=0.92,
				sentiment="负面",
				urgency="普通",
				key_info={"issue": "开胶"},
			),
		),
		_TestScenario(
			name="商品质量投诉",
			messages=[
				ConversationMessage(role="customer", content="你们卖的羽绒服是次品！钻绒还脏！坑人！我要退款还要赔偿！")],
			classification=MessageClassificationResult(
				parent="投诉",
				name="商品质量投诉",
				confidence=0.90,
				sentiment="愤怒",
				urgency="紧急",
				key_info={"issue": "钻绒、脏污"},
			),
		),
		_TestScenario(
			name="引流广告",
			messages=[ConversationMessage(role="customer", content="加我微信 xxxxx，有内部优惠价")],
			classification=MessageClassificationResult(
				parent="垃圾广告",
				name="引流广告",
				confidence=0.97,
				sentiment="中性",
				urgency="普通",
				key_info={},
			),
		),
		_TestScenario(
			name="换货",
			messages=[ConversationMessage(role="customer", content="我买的L码太大了想换成M码，怎么操作？")],
			classification=MessageClassificationResult(
				parent="售后服务",
				name="换货",
				confidence=0.93,
				sentiment="中性",
				urgency="普通",
				key_info={"from_size": "L", "to_size": "M"},
			),
		),
	]

	print("\n⚙️  策略引擎 — 演示\n")
	for tc in test_cases:
		last_msg: str = tc.messages[-1].content
		result: MessageClassificationResult = tc.classification
		decision: HandlingStrategy = engine.decide(tc.messages, result)

		print(f"📨 {last_msg}")
		print(f"   🏷️  分类: {result.parent} / {result.name}  (置信度: {result.confidence:.2f})")
		print(f"   😊 情感: {result.sentiment}  |  ⚡ 紧急度: {result.urgency}")
		print(f"   🎯 回复模式: {_MODE_EMOJI.get(decision.response_mode, decision.response_mode.value)}")
		if decision.escalation_reason:
			print(f"   ⚠️  转人工原因: {decision.escalation_reason}")
		if decision.action_hints:
			print(f"   🔧 操作提示: {', '.join(decision.action_hints)}")
		print()
