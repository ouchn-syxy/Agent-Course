"""VLM 客户端 — 封装多模态视觉语言模型调用。

支持双后端自适应：
  - 火山方舟 Seed（Responses API）：input_image / input_text
  - 标准 OpenAI Vision（Chat Completions API）：image_url / text

图片统一采用 base64 Data URI 传入，兼容两种后端。
"""

import base64
import io

from PIL import Image
from openai import OpenAI
from openai.types.chat.chat_completion_content_part_image_param import (
	ChatCompletionContentPartImageParam,
	ImageURL,
)
from openai.types.chat.chat_completion_content_part_text_param import ChatCompletionContentPartTextParam
from openai.types.chat.chat_completion_user_message_param import ChatCompletionUserMessageParam
from openai.types.responses import EasyInputMessageParam
from openai.types.responses.response_input_image_param import ResponseInputImageParam
from openai.types.responses.response_input_text_param import ResponseInputTextParam
from openai.types.shared_params import ResponseFormatJSONObject

from inherit.utils.retry import retry


class VLMClient:
	"""视觉语言模型客户端，封装图片+文本的多模态调用。

	使用方式：
		vlm = VLMClient(
			api_key="xxx",
			base_url="https://ark.cn-beijing.volces.com/api/v3",
			model="doubao-seed-2-0-lite-260428",
			provider="volcano",
		)
		reply = vlm.chat_with_image(screenshot, "描述这张截图的内容")
		json_result = vlm.chat_with_image_json(screenshot, "提取消息为 JSON")
	"""


	def __init__(
			self,
			api_key: str,
			base_url: str,
			model: str,
			provider: str = "volcano",
	) -> None:
		"""初始化 VLM 客户端。

		Args:
			api_key: API 密钥。
			base_url: API 基础地址。
			model: 模型名称。
			provider: 后端类型，"volcano" 使用 Responses API，其他使用 Chat Completions API。
		"""
		self._api_key: str = api_key
		self._base_url: str = base_url
		self._model: str = model
		self._provider: str = provider
		self._client: OpenAI = OpenAI(api_key=api_key, base_url=base_url)


	@property
	def model(self) -> str:
		"""当前使用的模型名称。"""
		return self._model


	@property
	def provider(self) -> str:
		"""当前后端类型。"""
		return self._provider


	@staticmethod
	def _encode_image(image: Image.Image) -> str:
		"""将 PIL Image 编码为 base64 PNG Data URI。

		Args:
			image: PIL Image 对象。

		Returns:
			形如 "data:image/png;base64,..." 的 Data URI 字符串。
		"""
		buf = io.BytesIO()
		image.save(buf, format="PNG")
		return f"data:image/png;base64,{base64.b64encode(buf.getvalue()).decode()}"

	@staticmethod
	def _clean_json_response(text: str) -> str:
		"""容错清理模型偶尔附带的 Markdown 围栏或解释文字。"""
		cleaned = text.strip()
		start = cleaned.find("{")
		end = cleaned.rfind("}")
		if start >= 0 and end >= start:
			return cleaned[start:end + 1]
		return cleaned


	@retry(max_retries=3, delay_s=2.0)
	def chat_with_image(self, image: Image.Image, prompt: str) -> str:
		"""发送图片+文本到 VLM，返回文本回复。

		Args:
			image: 截图 PIL Image。
			prompt: 文本提示词。

		Returns:
			模型回复的文本内容。
		"""
		image_uri = self._encode_image(image)

		if self._provider == "volcano":
			return self._call_volcano(image_uri, prompt)
		else:
			return self._call_openai_vision(image_uri, prompt)


	@retry(max_retries=3, delay_s=2.0)
	def chat_with_image_json(self, image: Image.Image, prompt: str) -> str:
		"""发送图片+文本到 VLM，返回 JSON 文本。

		火山方舟 Responses API 不支持 response_format 参数，
		通过 prompt 追加 JSON 输出约束实现。

		Args:
			image: 截图 PIL Image。
			prompt: 文本提示词（应已包含 JSON schema 说明）。

		Returns:
			模型回复的 JSON 文本内容。
		"""
		if self._provider == "volcano":
			json_prompt = (
					prompt
					+ "\n\n【重要】请严格输出纯 JSON，"
					+ "不要包含 Markdown 代码块标记（如 ```json），"
					+ "不要添加任何解释性文字。\n"
					+ "字符串值中的换行符必须用 \\n 转义，双引号必须用 \\\" 转义，"
					+ "确保输出是合法 JSON。"
			)
			return self._clean_json_response(
				self._call_volcano(self._encode_image(image), json_prompt)
			)
		else:
			return self._clean_json_response(
				self._call_openai_vision_json(self._encode_image(image), prompt)
			)


	# ── 私有：后端调用 ─────────────────────────────────────────────

	def _call_volcano(self, image_uri: str, prompt: str) -> str:
		"""火山方舟 Responses API 调用。"""

		user_msg: EasyInputMessageParam = EasyInputMessageParam(role="user", content=[
			ResponseInputImageParam(type="input_image", image_url=image_uri, detail="auto"),
			ResponseInputTextParam(type="input_text", text=prompt)
		])
		response = self._client.responses.create(
			model=self._model,
			input=[user_msg],
		)
		return response.output_text


	def _call_openai_vision(self, image_uri: str, prompt: str) -> str:
		"""标准 OpenAI Vision Chat Completions API 调用。"""

		user_msg: ChatCompletionUserMessageParam = ChatCompletionUserMessageParam(role="user", content=[
			ChatCompletionContentPartImageParam(type="image_url", image_url=ImageURL(url=image_uri, detail="auto")),
			ChatCompletionContentPartTextParam(type="text", text=prompt),
		])
		response = self._client.chat.completions.create(
			model=self._model,
			messages=[user_msg],
		)
		return response.choices[0].message.content or ""


	def _call_openai_vision_json(self, image_uri: str, prompt: str) -> str:
		"""标准 OpenAI Vision Chat Completions API 调用（JSON 模式）。"""

		user_msg: ChatCompletionUserMessageParam = ChatCompletionUserMessageParam(role="user", content=[
			ChatCompletionContentPartImageParam(type="image_url", image_url=ImageURL(url=image_uri, detail="auto")),
			ChatCompletionContentPartTextParam(type="text", text=prompt),
		])
		response = self._client.chat.completions.create(
			model=self._model,
			messages=[user_msg],
			response_format=ResponseFormatJSONObject(type="json_object")
		)
		return response.choices[0].message.content or ""


# ═══════════════════════════════════════════════════════════════
# Demo
# ═══════════════════════════════════════════════════════════════

if __name__ == "__main__":
	"""演示 VLMClient 的 chat_with_image 与 chat_with_image_json。

	用法：
		cd ch04-service-agent/02-vision/src
		python vlm/client.py

	前提：项目根目录下 config.yaml 中 vlm 配置已填写。
	"""

	from config import Config
	from PIL import ImageDraw

	# ── 1. 加载配置 ──────────────────────────────────────────
	cfg = Config.from_yaml()
	vlm_cfg = cfg.vlm

	client = VLMClient(
		api_key=vlm_cfg.api_key_env,
		base_url=vlm_cfg.base_url,
		model=vlm_cfg.model,
		provider=vlm_cfg.provider,
	)
	print(f"✅ VLMClient 就绪  provider={client.provider}  model={client.model}")

	# ── 2. 生成测试图片 ──────────────────────────────────────
	img = Image.new("RGB", (400, 200), color="white")
	draw = ImageDraw.Draw(img)
	draw.rectangle([10, 10, 390, 190], outline="blue", width=2)
	draw.text((50, 50), "Hello, VLM!", fill="red")
	draw.text((50, 85), "This is a demo image.", fill="black")
	draw.text((50, 130), "Fruits: 3 apples, 2 bananas.", fill="green")
	print("✅ 测试图片已生成 (400×200)")

	# ── 3. Demo 1: chat_with_image ───────────────────────────
	print("\n" + "=" * 60)
	print("🧪 Demo 1 — chat_with_image（自由文本）")
	print("=" * 60)
	result = client.chat_with_image(img, "用中文一句话描述这张图片的内容。")
	print(f"回复: {result}")

	# ── 4. Demo 2: chat_with_image_json ──────────────────────
	print("\n" + "=" * 60)
	print("🧪 Demo 2 — chat_with_image_json（JSON 输出）")
	print("=" * 60)
	json_prompt = (
		"识别图片中的水果名称及数量，"
		'以 JSON 格式输出: {"fruits": [{"name": "…", "count": 0}]}'
	)
	result = client.chat_with_image_json(img, json_prompt)
	print(f"回复: {result}")

	print("\n✅ Demo 完成")
