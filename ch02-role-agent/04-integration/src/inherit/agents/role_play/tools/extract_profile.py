"""
文本提取工具 — 从搜索结果等文本中提取结构化的人物 Profile。

接收文本，调用 LLM 从中提取结构化的人物特征信息。
输出 Profile 对象，可与 save_yaml 配合使用。

设计要点：
  - 独立 LLM 调用（temperature=0.3），不依赖 Agent 主循环的消息上下文
  - 通过 render_model_code 将 Profile 模型结构注入 Prompt
  - 提取失败返回含 error 键的字典（不抛异常），便于 Agent 处理
"""

from __future__ import annotations

import json

from openai.types.chat import (
	ChatCompletionMessageParam,
	ChatCompletionSystemMessageParam,
	ChatCompletionUserMessageParam,
)

from inherit.agents.role_play.models.profile import Profile
from inherit.llm.tool_client import ToolLLMClient
from inherit.llm.tool_registry import ToolDef
from inherit.prompt.prompt_manager import PromptManager
from inherit.utils.model_render import render_model_code
from inherit.utils.retry import retry


class ExtractProfile:
	"""从文本中提取结构化人物 Profile 的工具。

	Agent 循环中的典型用法：
	  → web_search("鲁迅 性格") 返回搜索结果
	  → extract_features(text=搜索结果) 返回 Profile
	  → 多轮提取后调用 save_yaml 合并保存

	用法：
		tool = ExtractProfile(llm, pm)
		profile = tool.extract(text="...")
	"""


	def __init__(self, llm: ToolLLMClient, pm: PromptManager) -> None:
		"""
		Args:
			llm: 已初始化的 ToolLLMClient 实例（用于提取时的 LLM 调用）。
			pm: PromptManager 实例，用于加载 tools/extract_profile/system.j2 模板。
		"""
		self._llm = llm
		self._pm = pm


	def extract(self, text: str) -> Profile:
		"""从给定文本中提取结构化人物特征。

		Args:
			text: 待提取的文本（搜索结果 JSON 字符串或纯文本均可）。

		Returns:
			Profile 对象。

		Raises:
			ValueError: LLM 返回的 JSON 解析失败或格式不符合要求。
		"""
		model_code = render_model_code(Profile)
		system_prompt = self._pm.render("agents/role_play/tools/extract_profile/system.j2", model_code=model_code)
		user_prompt = f"## 待提取文本\n{text}"

		messages: list[ChatCompletionMessageParam] = [
			ChatCompletionSystemMessageParam(role="system", content=system_prompt),
			ChatCompletionUserMessageParam(role="user", content=user_prompt),
		]

		# 1. 调用 LLM（网络层瞬时故障由 @retry 自动处理）
		response = self._extract_raw(messages)

		# 2. 业务层校验（内容问题不重试，直接抛异常）
		try:
			data = json.loads(response)
		except json.JSONDecodeError:
			raise ValueError("提取结果 JSON 解析失败") from None

		try:
			data = ExtractProfile._clean_none(data)
			return Profile.model_validate(data)
		except Exception:
			raise ValueError("提取结果校验失败，数据不符合 Profile 结构") from None


	@retry(max_retries=2, delay_s=3.0, ignore_exceptions=[ValueError, json.JSONDecodeError])
	def _extract_raw(self, messages: list[ChatCompletionMessageParam]) -> str:
		"""纯 LLM 调用：发送提取 prompt 并返回 JSON 字符串。

		仅在网络层瞬时故障（超时、限流等）时重试；
		JSON 解析 / 校验失败属于内容问题，不重试。
		"""
		return self._llm.chat_with_json(messages, temperature=0.3)


	def to_tool_def(self) -> ToolDef:
		"""生成此工具的 ToolDef 注册描述。"""
		return ToolDef(
			name="extract_features",
			description="从搜索结果文本中提取结构化的人物特征信息，返回 Profile 对象。LLM 自动识别文本中出现的所有字段，无信息的字段不会出现在输出中。",
			parameters={
				"text": {
					"type": "string",
					"description": "待提取的文本内容（搜索结果 JSON 或网页正文）",
				},
			},
			required=["text"],
			func=self.extract,
		)


	@staticmethod
	def _clean_none(d: dict | list | object) -> dict | list | object:
		"""递归移除字典和列表中的 None 值，返回清理后的副本。

		用于在调用 model_validate 之前清理 LLM 返回的 JSON 数据，
		避免 Optional 字段的 None 值干扰 Pydantic 校验。
		"""
		if isinstance(d, dict):
			return {k: ExtractProfile._clean_none(v) for k, v in d.items() if v is not None}
		if isinstance(d, list):
			return [ExtractProfile._clean_none(v) for v in d if v is not None]
		return d


if __name__ == "__main__":
	from config import Config
	from inherit.utils.path import get_prj_root

	print("=" * 60)
	print("  ExtractProfile 演示")
	print("=" * 60)

	cfg = Config.from_yaml()

	llm = ToolLLMClient(
		api_key=cfg.llm.api_key_env,
		base_url=cfg.llm.base_url,
		model=cfg.llm.model,
		temperature=cfg.generation.temperature,
		top_p=cfg.generation.top_p,
		max_tokens=cfg.generation.max_tokens,
	)

	prompts_dir = get_prj_root() / "prompts"
	pm = PromptManager(prompts_dir)

	tool = ExtractProfile(llm, pm)

	sample_text = """
	鲁迅（1881年9月25日—1936年10月19日），原名周樟寿，后改名周树人，
	字豫山，后改字豫才，浙江绍兴人。著名文学家、思想家、革命家、教育家、
	民主战士，新文化运动的重要参与者，中国现代文学的奠基人之一。
	代表作品有《呐喊》《彷徨》《朝花夕拾》《野草》《故事新编》等。
	鲁迅的写作风格犀利冷峻，善于以讽刺手法揭露社会黑暗面。
	他说话直接坦率，不拐弯抹角，常用反语讽刺时弊。
	"""

	print(f"\n📝 待提取文本（{len(sample_text)} 字符）：")
	print(sample_text.strip())

	print("\n⏳ 正在提取 Profile...")
	profile = tool.extract(sample_text)

	print("\n✅ 提取结果：")
	print(profile.model_dump_json(indent=2, ensure_ascii=False))

	print("\n" + "=" * 60)
	print("  演示完成")
	print("=" * 60)
