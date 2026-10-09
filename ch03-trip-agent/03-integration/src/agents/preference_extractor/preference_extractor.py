"""PreferenceExtractor — 从用户对话中提取偏好的智能体。

调用 LLM 分析用户消息，提取偏好（tag/value 对），

用法：
    extractor = PreferenceExtractor(llm=llm, pm=pm)
    entries: list[PreferenceEntry] = extractor.extract(user_message)
    for entry in entries:
        pref_mgr.record_preference(entry.tag, entry.value)
"""

from __future__ import annotations

import json

from openai.types.chat import ChatCompletionSystemMessageParam, ChatCompletionUserMessageParam

from inherit.llm.client import LLMClient
from inherit.prompt.prompt_manager import PromptManager
from inherit.utils.model_render import render_model_code
from memory.preference_memory import PreferenceEntry


class PreferenceExtractor:
	"""偏好提取智能体。

	调用时机由调用方决定：当用户回答中包含偏好时，调用 extract() 进行偏好更新。
	"""


	def __init__(self, llm: LLMClient, pm: PromptManager) -> None:
		self._llm: LLMClient = llm
		self._pm: PromptManager = pm


	# ================================================================
	# 提取
	# ================================================================

	def extract(self, user_message: str) -> list[PreferenceEntry]:
		"""从用户消息中提取偏好。

		Args:
			user_message: 用户消息文本

		Returns:
			提取到的 PreferenceEntry 列表，未提取到则返回空列表。
		"""
		system_prompt: str = self._pm.render(
			"agents/preference_extractor/system.j2",
			preference_entry_schema=render_model_code(PreferenceEntry),
		)
		user_prompt: str = self._pm.render(
			"agents/preference_extractor/extract.j2",
			user_message=user_message,
		)

		response: str = self._llm.chat_with_json(
			messages=[
				ChatCompletionSystemMessageParam(role="system", content=system_prompt),
				ChatCompletionUserMessageParam(role="user", content=user_prompt),
			],
			temperature=0.1
		)

		raw_list: list = json.loads(response)
		return [PreferenceEntry.model_validate(item) for item in raw_list]


if __name__ == "__main__":

	from config import Config
	from inherit.utils.path import get_prj_root

	cfg: Config = Config.from_yaml()

	llm: LLMClient = LLMClient(
		api_key=cfg.llm.api_key_env,
		base_url=cfg.llm.base_url,
		model=cfg.llm.model,
		temperature=cfg.generation.temperature,
		top_p=cfg.generation.top_p,
		max_tokens=cfg.generation.max_tokens,
	)

	pm: PromptManager = PromptManager(get_prj_root() / "prompts")
	extractor: PreferenceExtractor = PreferenceExtractor(llm=llm, pm=pm)

	# ── 测试用例 ──
	test_messages: list[str] = [
		"我比较喜欢简洁直接的沟通方式，不喜欢绕弯子。",
		"订酒店的话我偏好海景房，预算控制在 500 以内，最好是含早的。",
		"今天天气不错。",
	]

	for msg in test_messages:
		print(f"\n{'=' * 60}")
		print(f"📩 用户消息：{msg}")
		entries: list[PreferenceEntry] = extractor.extract(msg)
		if entries:
			for e in entries:
				print(f"  🏷️  {e.tag} → {e.value}")
		else:
			print("  (无偏好)")
