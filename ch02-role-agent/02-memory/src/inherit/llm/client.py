"""
统一的 LLM 调用封装。

接收显式参数，提供与 OpenAI SDK 兼容的 chat 接口。
与配置文件完全解耦：连接参数和生成参数均由外部显式传入。

设计要点：
  - 与配置文件解耦：所有参数由外部显式传入
  - 生成参数可逐次覆盖：chat(messages, temperature=0.3) 覆盖默认值
  - JSON 模式独立方法：避免 response_format 与其他参数冲突
"""

from collections.abc import Iterable

from json_repair import repair_json
from openai import OpenAI
from openai.types.chat import ChatCompletionMessageParam
from openai.types.shared_params import ResponseFormatJSONObject


class LLMClient:
	"""
	统一的 LLM 客户端，封装 OpenAI SDK 调用。

	使用方式：
		llm = LLMClient(
			api_key="sk-xxx",
			base_url="https://api.deepseek.com",
			model="deepseek-v4-flash",
			temperature=0.8,
			max_tokens=1024,
		)
		reply = llm.chat([{"role": "user", "content": "你好"}])
	"""


	def __init__(
			self,
			api_key: str,
			base_url: str,
			model: str,
			temperature: float | None = None,
			top_p: float | None = None,
			max_tokens: int | None = None,
	) -> None:
		"""
		初始化 LLM 客户端。

		Args:
			api_key: API 密钥。
			base_url: API 基础地址。
			model: 模型名称。
			temperature: 温度（0-2），None 表示不设置。
			top_p: 核采样阈值（0-1），None 表示不设置。
			max_tokens: 最大输出 token 数，None 表示不限制。
		"""
		self._api_key: str = api_key
		self._base_url: str = base_url
		self._model: str = model
		self._temperature: float | None = temperature
		self._top_p: float | None = top_p
		self._max_tokens: int | None = max_tokens

		self._client: OpenAI = OpenAI(
			api_key=api_key,
			base_url=base_url,
		)


	@property
	def model(self) -> str:
		"""当前使用的模型名称。"""
		return self._model


	def chat(
			self,
			messages: Iterable[ChatCompletionMessageParam],
			temperature: float | None = None,
			top_p: float | None = None,
			max_tokens: int | None = None,
	) -> str:
		"""
		发送消息并返回模型文本回复。

		Args:
			messages: OpenAI messages 格式列表。
			temperature: 温度（None 则使用实例默认值）。
			top_p: 核采样阈值（None 则使用实例默认值）。
			max_tokens: 最大输出 token 数（None 则使用实例默认值）。

		Returns:
			模型回复的文本内容。若模型返回空内容则返回空字符串。
		"""

		completion = self._client.chat.completions.create(
			model=self.model,
			messages=messages,
			temperature=temperature if temperature is not None else self._temperature,
			top_p=top_p if top_p is not None else self._top_p,
			max_tokens=max_tokens if max_tokens is not None else self._max_tokens,
		)
		return completion.choices[0].message.content or ""


	def chat_with_json(
			self,
			messages: Iterable[ChatCompletionMessageParam],
			temperature: float | None = None,
			top_p: float | None = None,
			max_tokens: int | None = None,
	) -> str:
		"""
		发送消息并以 JSON 格式获取回复。

		与 chat() 的区别：强制设置 response_format={"type": "json_object"}，
		确保模型输出合法的 JSON 字符串。评估、结构化提取等场景使用。

		Args:
			messages: OpenAI messages 格式列表。
			temperature: 温度（None 则使用实例默认值）。
			top_p: 核采样阈值（None 则使用实例默认值）。
			max_tokens: 最大输出 token 数（None 则使用实例默认值）。

		Returns:
			模型回复的 JSON 文本内容。
		"""

		completion = self._client.chat.completions.create(
			model=self.model,
			messages=messages,
			response_format=ResponseFormatJSONObject(type="json_object"),
			temperature=temperature if temperature is not None else self._temperature,
			top_p=top_p if top_p is not None else self._top_p,
			max_tokens=max_tokens if max_tokens is not None else self._max_tokens,
		)
		return repair_json(completion.choices[0].message.content or "")


	def info(self) -> str:
		"""返回当前 LLM 连接信息的可读字符串，用于终端展示。"""
		return f"{self._model} @ {self._base_url}"


if __name__ == "__main__":
	from openai.types.chat import ChatCompletionUserMessageParam

	from config import Config

	cfg: Config = Config.from_yaml()
	llm = LLMClient(
		api_key=cfg.llm.api_key_env,
		base_url=cfg.llm.base_url,
		model=cfg.llm.model,
		temperature=cfg.generation.temperature,
		top_p=cfg.generation.top_p,
		max_tokens=cfg.generation.max_tokens,
	)

	print(f"LLM: {llm.info()}")

	# ── chat ──
	reply = llm.chat([
		ChatCompletionUserMessageParam(role="user", content="用一句话介绍你自己。")
	])
	print(f"chat 回复：{reply}")

	# ── chat_with_json ──
	json_reply = llm.chat_with_json([
		ChatCompletionUserMessageParam(role="user", content='返回 JSON：{"name": "...", "version": "..."} 介绍你自己。')
	])
	print(f"chat_with_json 回复：{json_reply}")
