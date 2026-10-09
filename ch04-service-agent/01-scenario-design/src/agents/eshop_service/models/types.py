"""消息分类领域模型 — 客服场景下的 Pydantic DTO。"""

from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field

from agents.eshop_service.models.conversation import ConversationMessage


class ResponseMode(str, Enum):
	"""消息回复模式 — 替代 can_auto_reply + need_human 的单一枚举。"""

	AUTO = "auto"  # 机器直接回复
	AUTO_WITH_ESCALATION = "auto_with_escalation"  # 机器先回，触发升级条件时转人工
	HUMAN = "human"  # 必须转人工
	IGNORE = "ignore"  # 不回复（垃圾广告等）


class MessageCoreCategory(BaseModel):
	"""消息大类（对应 core.json 条目）。"""

	name: str = Field(description="大类名称，如 售前咨询")
	description: str = Field(default="", description="大类描述")


class EscalationRule(BaseModel):
	"""升级规则（对应 sub.json 中 escalation_rules 条目）。"""

	condition: str = Field(description="触发条件描述")
	action: str = Field(default="", description="触发后的动作")


class HandlingStrategy(BaseModel):
	"""消息处理策略 — 从 sub.json 的 strategy 块提取。"""

	response_mode: ResponseMode = Field(default=ResponseMode.AUTO, description="回复模式")
	need_product_query: bool = Field(default=False, description="是否需要查询商品")
	need_order_query: bool = Field(default=False, description="是否需要查询订单")
	reply_template: Optional[str] = Field(default=None, description="回复模板")
	action_hints: list[str] = Field(default_factory=list, description="操作提示列表")
	escalation_rules: list[EscalationRule] = Field(default_factory=list, description="升级规则列表")
	escalation_reason: Optional[str] = Field(default=None, description="转人工原因")


class MessageSubCategory(BaseModel):
	"""消息子类（对应 sub.json 条目），策略规则聚合在 strategy 字段中。"""

	name: str = Field(description="子类名称，如 库存查询")
	parent: str = Field(description="所属大类名称，如 售前咨询")
	description: str = Field(default="", description="子类描述")
	strategy: HandlingStrategy = Field(default_factory=HandlingStrategy, description="处理策略")


class MessageClassificationResult(BaseModel):
	"""消息分类结果 — 注入 Prompt 模板让 LLM 按此结构输出。"""

	parent: str = Field(description="所属消息大类")
	name: str = Field(description="消息子类名称")
	confidence: float = Field(default=0.0, ge=0.0, le=1.0, description="分类置信度（0.0 ~ 1.0）")
	sentiment: str = Field(description="情感：正面 / 中性 / 负面 / 愤怒")
	urgency: str = Field(description="紧急度：紧急 / 普通")
	key_info: dict[str, str] = Field(default_factory=dict,
	                                 description="从消息中提取的关键信息（商品名、尺码、颜色、订单号等）")


	def is_valid(self) -> bool:
		"""分类结果是否有效（置信度足够）。"""
		return self.confidence >= 0.5


class FewShotExample(BaseModel):
	"""Few-shot 示例：一段沟通记录及其正确分类结果。"""

	conversation: list[ConversationMessage] = Field(description="沟通记录")
	result: MessageClassificationResult = Field(description="对应的分类结果")
