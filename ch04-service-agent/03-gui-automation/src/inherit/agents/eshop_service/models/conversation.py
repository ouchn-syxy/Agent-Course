"""沟通记录提取 — VLM 截图 → 结构化对话 Pydantic 模型。"""

from pydantic import BaseModel, Field


class ConversationMessage(BaseModel):
	"""沟通记录中的单条消息。"""

	role: str = Field(description="发言者身份: customer / assistant")
	content: str = Field(description="消息的完整原文")


class Conversation(BaseModel):
	"""多轮对话消息历史。"""

	messages: list[ConversationMessage] = Field(
		default_factory=list,
		description="去重后的完整消息列表，按时间顺序排列",
	)
