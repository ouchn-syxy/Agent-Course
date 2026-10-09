"""
角色数据模型 — Pydantic v2 校验。

定义角色 YAML 的完整结构，与 data/profiles/*.yaml 严格匹配。
可直接从 YAML 文件反序列化为模型对象，供 profile.j2 模板渲染。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, ConfigDict, Field


# ============================================================
# 子模型
# ============================================================

class SpeechStyle(BaseModel):
	"""说话风格。"""

	model_config = ConfigDict(extra="forbid")

	tone: str | None = Field(default=None, description="语气基调（如 '犀利冷峭、亦庄亦谐、文白夹杂'）")
	habits: list[str] = Field(default_factory=list, description="说话习惯列表")
	forbidden: list[str] = Field(default_factory=list, description="禁止的表达方式")


class LifeEvent(BaseModel):
	"""生平关键节点。"""

	model_config = ConfigDict(extra="forbid")

	year: int | None = Field(default=None, description="年份")
	event: str | None = Field(default=None, description="事件描述")


class FewShotExample(BaseModel):
	"""Few-shot 对话示例。"""

	model_config = ConfigDict(extra="forbid")

	user: str = Field(description="模拟用户提问")
	assistant: str = Field(description="角色回复示例（体现风格、时代感、性格）")


# ============================================================
# 角色主模型
# ============================================================

class Profile(BaseModel):
	"""角色定义 — 与 data/profiles/*.yaml 字段一一对应。

	用法：
		profile = Profile.from_yaml(Path("data/profiles/luxun.yaml"))
		# 模板中直接访问属性：
		#   {{ profile.name }}
		#   {% for h in profile.speech_style.habits %}...{% endfor %}
	"""

	model_config = ConfigDict(extra="forbid")

	name: str = Field(description="人物姓名（如 '鲁迅'）")
	era: str | None = Field(default=None, description="所属时代（如 '晚清至民国（1881-1936）'）")
	identity: str | None = Field(default=None, description="身份描述（如 '文学家、思想家、中国现代文学奠基人'）")
	personality: list[str] = Field(default_factory=list, description="性格特征列表")
	speech_style: SpeechStyle | None = Field(default=None, description="说话风格")
	knowledge_domain: list[str] = Field(default_factory=list, description="知识领域")
	emotional_baseline: str | None = Field(default=None, description="情感基调")
	life_events: list[LifeEvent] = Field(default_factory=list, description="生平关键节点")
	representative_works: list[str] = Field(default_factory=list, description="代表作品")
	few_shot_examples: list[FewShotExample] = Field(default_factory=list,
	                                                description="Few-shot 对话示例（用于后续角色模拟时注入 system prompt）")


	# ============================================================
	# 工厂方法
	# ============================================================

	@classmethod
	def from_yaml(cls, path: Path) -> "Profile":
		"""从 YAML 文件加载角色定义。

		Args:
			path: YAML 文件路径（如 Path("data/profiles/luxun.yaml")）。

		Returns:
			校验后的 Profile 实例。
		"""
		raw = yaml.safe_load(path.read_text(encoding="utf-8"))
		if not isinstance(raw, dict):
			raise ValueError(f"YAML 内容应为字典，实际为 {type(raw).__name__}")
		return cls.model_validate(raw)


	@classmethod
	def from_dict(cls, data: dict[str, Any]) -> "Profile":
		"""从字典构建并校验。"""
		return cls.model_validate(data)
