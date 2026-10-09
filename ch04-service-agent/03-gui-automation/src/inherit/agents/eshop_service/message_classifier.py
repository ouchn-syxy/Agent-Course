"""消息分类器 — 基于 LLM few-shot 将客服与买家的沟通记录分类。

输入：客服与买家沟通记录（list[ConversationMessage]）
输出：MessageClassification（针对未回复买家消息的综合分类结果）
"""

from openai.types.chat import ChatCompletionMessageParam, ChatCompletionUserMessageParam

from inherit.agents.eshop_service.message_category_manager import MessageCategoryManager
from inherit.agents.eshop_service.models.conversation import ConversationMessage
from inherit.agents.eshop_service.models.types import FewShotExample, MessageClassificationResult
from inherit.llm.client import LLMClient
from inherit.prompt.prompt_manager import PromptManager
from inherit.utils.model_render import render_model_code
from inherit.utils.path import get_prj_root

# Few-shot 示例，仅保留四大类的典型代表，让模型基于分类标准自主推理子类型
_FEW_SHOT_EXAMPLES: list[FewShotExample] = [
	FewShotExample(
		conversation=[
			ConversationMessage(role="customer", content="这个红色的还有M码吗？"),
		],
		result=MessageClassificationResult(
			parent="售前咨询", name="库存查询", confidence=0.95, sentiment="中性", urgency="普通",
			key_info={"product": "红色连衣裙", "size": "M"},
		),
	),
	FewShotExample(
		conversation=[
			ConversationMessage(role="customer", content="鞋子穿了三天就开胶了，我要退货！"),
		],
		result=MessageClassificationResult(
			parent="售后服务", name="退货退款", confidence=0.95, sentiment="负面", urgency="紧急",
			key_info={"product": "鞋子", "issue": "开胶"},
		),
	),
	FewShotExample(
		conversation=[
			ConversationMessage(role="customer", content="你们卖的羽绒服是次品！钻绒还脏！坑人！"),
		],
		result=MessageClassificationResult(
			parent="投诉", name="商品质量投诉", confidence=0.95, sentiment="愤怒", urgency="紧急",
			key_info={"product": "羽绒服", "issue": "钻绒、污渍"},
		),
	),
	FewShotExample(
		conversation=[
			ConversationMessage(role="customer", content="加我微信 xxxxx，有优惠"),
		],
		result=MessageClassificationResult(
			parent="垃圾广告", name="引流广告", confidence=0.95, sentiment="中性", urgency="普通",
		),
	),
]


class MessageClassifier:
	"""LLM few-shot 消息分类器。

	使用示例::

		from config import Config
		from message_classifier import MessageClassifier
		from inherit.llm.client import LLMClient
		from inherit.prompt.prompt_manager import PromptManager

		cfg = Config.from_yaml()
		llm = LLMClient(
			api_key=cfg.llm.api_key_env,
			base_url=cfg.llm.base_url,
			model=cfg.llm.model,
			temperature=cfg.generation.temperature or 0.3,
		)
		pm = PromptManager(cfg.project_root / "prompts")
		classifier = MessageClassifier(llm=llm, pm=pm)
		result = classifier.classify("这个红色的还有M码吗？")
		print(result.parent, result.name)
	"""


	def __init__(
			self,
			llm: LLMClient,
			pm: PromptManager,
			category_mgr: MessageCategoryManager,
	) -> None:
		self._client: LLMClient = llm
		self._prompt_manager: PromptManager = pm
		self._category_mgr: MessageCategoryManager = category_mgr


	def classify(self, conversation: list[ConversationMessage]) -> MessageClassificationResult:
		"""基于客服与买家的完整沟通记录，对最新未回复的买家消息进行分类。

		:param conversation: 客服与买家的沟通记录
		:return: MessageClassification
		"""
		if not conversation:
			return MessageClassificationResult(
				parent="垃圾广告",
				name="无关内容",
				confidence=0.0,
				sentiment="中性",
				urgency="普通",
			)

		prompt: str = self._prompt_manager.render(
			"agents/eshop_service/message_classifier/classify.j2",
			message_classification_result_schema=render_model_code(MessageClassificationResult),
			examples=_FEW_SHOT_EXAMPLES,
			core_categories=self._category_mgr.core_categories,
			sub_categories=self._category_mgr.sub_categories,
			conversation=conversation,
		)

		messages: list[ChatCompletionMessageParam] = [
			ChatCompletionUserMessageParam(role="user", content=prompt)
		]

		try:
			json_text: str = self._client.chat_with_json(messages)
			return MessageClassificationResult.model_validate_json(json_text)
		except Exception as e:
			last_msg = conversation[-1].content if conversation else ""
			print(f"[警告] 分类失败: {e}，最后消息: {last_msg[:50]}")
			return MessageClassificationResult(
				parent="垃圾广告",
				name="无关内容",
				confidence=0.0,
				sentiment="中性",
				urgency="普通",
			)


# ──────────────────────────────────────────────
# 简易演示：直接运行本文件即可体验分类效果
# ──────────────────────────────────────────────
if __name__ == "__main__":

	from config import Config
	from inherit.agents.eshop_service.message_category_manager import MessageCategoryManager

	cfg: Config = Config.from_yaml()
	llm: LLMClient = LLMClient(
		api_key=cfg.llm.api_key_env,
		base_url=cfg.llm.base_url,
		model=cfg.llm.model,
		temperature=cfg.generation.temperature,
		max_tokens=cfg.generation.max_tokens,
	)
	pm: PromptManager = PromptManager(get_prj_root() / "prompts")
	category_mgr: MessageCategoryManager = MessageCategoryManager(
		get_prj_root() / "data" / "eshop_service" / "message_category"
	)
	classifier: MessageClassifier = MessageClassifier(llm=llm, pm=pm, category_mgr=category_mgr)

	demo_conversations: list[list[ConversationMessage]] = [
		[ConversationMessage(role="customer", content="这个红色的还有M码吗？")],
		[ConversationMessage(role="customer", content="我身高165体重55，这个衬衫选什么码比较好？")],
		[ConversationMessage(role="customer", content="鞋子穿了三天就开胶了，我要退货！")],
		[ConversationMessage(role="customer", content="快递怎么三天没更新了？")],
		[ConversationMessage(role="customer", content="你们卖的羽绒服是次品！钻绒还脏！坑人！")],
		[ConversationMessage(role="customer", content="加我微信 xxxxx，有优惠")],
	]

	print("\n🛒 电商客服消息分类器 — 演示\n")
	for conv in demo_conversations:
		last_msg = conv[-1].content
		r: MessageClassificationResult = classifier.classify(conv)
		print(f"📨 {last_msg}")
		print(f"   → {r.parent} / {r.name}  (置信度: {r.confidence:.2f}, 情感: {r.sentiment}, 紧急度: {r.urgency})")
		print()
