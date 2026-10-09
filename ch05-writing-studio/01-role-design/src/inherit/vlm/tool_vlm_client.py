"""ToolVLMClient — 支持 Function Calling 的 VLM 客户端。

继承 VLMClient，新增 chat_with_image_and_tools() 方法，
一次调用同时传入截图 + 对话历史 + 工具定义，让 VLM 直接
看图决策并调用执行工具。

仅支持 OpenAI Chat Completions API 路径（deepseek / openai / qwen / zhipu），
火山方舟 Responses API 暂不支持 Function Calling。
"""

from __future__ import annotations

from collections.abc import Iterable

from PIL import Image
from openai.types.chat import (
	ChatCompletionContentPartImageParam,
	ChatCompletionContentPartTextParam,
	ChatCompletionMessageFunctionToolCall,
	ChatCompletionMessageParam,
	ChatCompletionToolParam,
	ChatCompletionUserMessageParam, ChatCompletionToolChoiceOptionParam, ChatCompletionSystemMessageParam,
)
from openai.types.chat.chat_completion_content_part_image_param import ImageURL

from inherit.utils.retry import retry
from inherit.vlm.client import VLMClient


class ToolVLMClient(VLMClient):
	"""支持 Function Calling 的 VLM 客户端。

	用法：
		vlm = ToolVLMClient(
			api_key="xxx",
			base_url="https://api.deepseek.com",
			model="deepseek-v4-flash",
			provider="deepseek",
		)
		content, tool_calls = vlm.chat_with_image_and_tools(
			image=screenshot,
			messages=conversation,
			tools=execution_tools,
		)
	"""


	def info(self) -> str:
		"""返回可读的模型信息，用于日志输出。"""
		return f"{self.model} (ToolVLM) @ {self.provider}"


	@retry(max_retries=3, delay_s=2.0)
	def chat_with_image_and_tools(
			self,
			image: Image.Image,
			messages: Iterable[ChatCompletionMessageParam],
			tools: Iterable[ChatCompletionToolParam],
			tool_choice: ChatCompletionToolChoiceOptionParam = "auto",
			temperature: float | None = None,
			top_p: float | None = None,
			max_tokens: int | None = None,
	) -> tuple[str | None, list[ChatCompletionMessageFunctionToolCall]]:
		"""发送截图 + 对话历史 + 工具到 VLM，支持 Function Calling。

		在现有 messages 末尾追加一条含截图的 user 消息后，
		调用 Chat Completions API（带 tools 参数）。

		Args:
			image: 当前截图 PIL Image。
			messages: 已有的对话历史（含 system / assistant / tool 消息）。
			tools: OpenAI Function Calling 工具定义列表。
			tool_choice: 工具选择策略（"auto" / "required" / "none"）。

		Returns:
			(content, tool_calls) 元组：
			  - content: VLM 文本回复（可能为 None）。
			  - tool_calls: 工具调用列表，每项含 id / function.name / function.arguments。
		"""
		image_uri: str = self._encode_image(image)

		user_msg: ChatCompletionUserMessageParam = ChatCompletionUserMessageParam(
			role="user",
			content=[
				ChatCompletionContentPartImageParam(
					type="image_url",
					image_url=ImageURL(url=image_uri, detail="auto"),
				),
				ChatCompletionContentPartTextParam(
					type="text",
					text=(
						"这是客服工作台的最新截图。请观察界面上的客户消息和状态变化，"
						"判断当前处于哪个阶段（等待新消息 / 理解客户意图 /"
						"已输入回复待发送 / 任务完毕），决定下一步操作并调用对应工具。"
					),
				),
			],
		)

		full_messages: list[ChatCompletionMessageParam] = list(messages) + [user_msg]

		completion = self._client.chat.completions.create(
			model=self._model,
			messages=full_messages,
			tools=list(tools),
			tool_choice=tool_choice,
			temperature=temperature,
			top_p=top_p,
			max_tokens=max_tokens,
		)

		choice = completion.choices[0]
		message = choice.message

		content: str | None = message.content
		tool_calls: list[ChatCompletionMessageFunctionToolCall] = []

		if message.tool_calls:
			for tc in message.tool_calls:
				if isinstance(tc, ChatCompletionMessageFunctionToolCall):
					tool_calls.append(tc)

		return content, tool_calls


if __name__ == "__main__":
	"""演示 ToolVLMClient 的 chat_with_image_and_tools。

	用法：
		cd ch04-service-agent/03-gui-automation/src
		python vlm/tool_vlm_client.py

	前提：
		1. 项目根目录 config.yaml 中 vlm 配置已填写。
		2. data/tests/screenshot.png 存在（任意截图即可）。
	"""

	import json

	from config import Config
	from inherit.utils.path import get_prj_root

	# ── 1. 加载配置 ──────────────────────────────────────────
	cfg = Config.from_yaml()
	vlm_cfg = cfg.vlm

	client = ToolVLMClient(
		api_key=vlm_cfg.api_key_env,
		base_url=vlm_cfg.base_url,
		model=vlm_cfg.model,
		provider=vlm_cfg.provider,
	)
	print(f"✅ ToolVLMClient 就绪  provider={client.provider}  model={client.model}")

	# ── 2. 加载测试截图 ──────────────────────────────────────
	screenshot_path = get_prj_root() / "data" / "tests" / "screenshot.png"
	if not screenshot_path.exists():
		print(f"❌ 截图文件不存在: {screenshot_path}")
		print("   请将测试截图放到 data/tests/screenshot.png 后重试。")
		exit(1)

	img = Image.open(screenshot_path)
	print(f"✅ 截图已加载: {screenshot_path.name} ({img.width}×{img.height})")

	# ── 3. 定义演示工具 ──────────────────────────────────────
	tools: list[ChatCompletionToolParam] = [
		{
			"type": "function",
			"function": {
				"name": "describe",
				"description": "用一句话描述截图中的界面内容，包括可见的按钮、文字、布局信息",
				"parameters": {
					"type": "object",
					"properties": {
						"summary": {"type": "string", "description": "界面内容一句话总结"},
						"elements": {"type": "array", "items": {"type": "string"}, "description": "可见交互元素列表"},
					},
					"required": ["summary", "elements"],
				},
			},
		},
	]

	# ── 4. 调用 VLM ──────────────────────────────────────────
	print()
	print("=" * 60)
	print("🧪 Demo — chat_with_image_and_tools")
	print("=" * 60)

	messages: list[ChatCompletionMessageParam] = [
		ChatCompletionSystemMessageParam(
			role="system",
			content="你是一个 GUI 分析助手，观察截图并调用 describe 工具描述其中的界面内容。"
		)
	]

	content, tool_calls = client.chat_with_image_and_tools(
		image=img,
		messages=messages,
		tools=tools,
	)

	if tool_calls:
		print(f"🔧 VLM 调用了 {len(tool_calls)} 个工具:")
		for tc in tool_calls:
			args = json.loads(tc.function.arguments)
			print(f"  · {tc.function.name}: {json.dumps(args, ensure_ascii=False)}")
	else:
		print(f"💬 VLM 直接回复: {content}")

	print()
	print("✅ Demo 完成")
