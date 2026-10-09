"""ReAct 决策模型 — Action 类型、LLM 输出结构。

本实验的 ReAct 不涉及工具调用，Action 全部面向用户交互。
"""

from enum import Enum

from pydantic import BaseModel, Field


# ============================================================
# Action 类型枚举
# ============================================================

class ActionType(str, Enum):
	"""ReAct 循环中 LLM 可选的行动类型。"""

	ASK_QUESTION = "ask_question"
	"""收集缺失信息：向用户提出一个具体问题。"""

	CLARIFY = "clarify"
	"""追问澄清：用户回答模糊，要求更明确的表述。"""

	CONFIRM = "confirm"
	"""确认需求：所有信息已完备，展示摘要请用户确认。"""

	COMPLETE = "complete"
	"""完成收集：用户已确认，需求收集结束。"""


# ============================================================
# LLM JSON 输出模型
# ============================================================

class ActionDetail(BaseModel):
	"""单次行动的具体内容。

	不同 action type 下各字段含义不同：
	  - ask_question: target_slot 为待收集槽位名，message 为提问文本
	  - clarify:      target_slot 为需澄清槽位名，message 为澄清追问
	  - confirm:      target_slot=None, message 为需求摘要确认文本
	  - complete:     target_slot=None, message 通常为空
	"""

	type: ActionType = Field(description="行动类型")
	target_slot: str | None = Field(
		default=None,
		description="目标槽位名（ask_question / clarify 时必填）",
	)
	message: str = Field(description="发给用户的自然语言消息")


class CollectionDecision(BaseModel):
	"""LLM 在每轮需求采集中做出的决策。

	包含推理过程（为什么要这样决策）和具体行动（向用户做什么）。

	格式：
	{
	  "thought": "目的地和日期还缺失，日期决定行程长度和季节适配...",
	  "action": {
	    "type": "ask_question",
	    "target_slot": "destination",
	    "message": "请问您想去哪里旅行呢？"
	  }
	}
	"""

	thought: str = Field(description="推理过程：当前缺失什么信息？为什么重要？")
	action: ActionDetail = Field(description="下一步行动")


# ============================================================
# 槽位值（意图提取输出）
# ============================================================

class SlotValue(BaseModel):
	"""从用户输入中提取的单个槽位键值对。

	LLM 返回包含该类型元素的 JSON 数组，如：
	[{"slot": "destination", "value": "西安"}, {"slot": "budget", "value": "5000元"}]
	"""

	slot: str = Field(
		description="槽位名（destination / departure_city / start_date / end_date / budget / travelers / preferences / constraints）")
	value: str = Field(description="用户提供的值")


# ============================================================
# 每步记录
# ============================================================

class StepRecord(BaseModel):
	"""ReAct 循环中单次迭代的完整记录：推理了什么、做了什么、观察到了什么。"""

	iteration: int = Field(description="迭代序号")
	thought: str = Field(description="LLM 的推理过程")
	action: ActionDetail = Field(description="执行的行动")
	observation: str = Field(description="用户的回答 / 操作结果")


# ============================================================
# 用户出行需求
# ============================================================

class TripRequirement(BaseModel):
	"""从终端交互中收集的结构化出行需求。"""
	destination: str = Field(default="", description="目的地城市/地区")
	departure_city: str = Field(default="", description="出发城市")
	start_date: str = Field(default="", description="出发日期 YYYY-MM-DD")
	end_date: str = Field(default="", description="返回日期 YYYY-MM-DD")
	budget: str = Field(default="", description='预算范围，如「3000-5000」')
	preferences: list[str] = Field(default_factory=list, description='偏好标签，如「自然风光」')
	num_people: str = Field(default="1", description="出行人数")
	additional_notes: str = Field(default="", description="补充说明")


	def to_user_prompt(self) -> str:
		"""转为格式化需求文本，供 prompt 模板使用。"""
		parts = []
		if self.destination:
			parts.append(f"- 目的地：{self.destination}")
		if self.departure_city:
			parts.append(f"- 出发城市：{self.departure_city}")
		if self.start_date and self.end_date:
			parts.append(f"- 出行日期：{self.start_date} ~ {self.end_date}")
		if self.budget:
			parts.append(f"- 预算范围：{self.budget} 元")
		if self.preferences:
			parts.append(f"- 偏好：{', '.join(self.preferences)}")
		if self.num_people and self.num_people != "1":
			parts.append(f"- 人数：{self.num_people}")
		if self.additional_notes:
			parts.append(f"- 补充说明：{self.additional_notes}")
		return "\n".join(parts)
