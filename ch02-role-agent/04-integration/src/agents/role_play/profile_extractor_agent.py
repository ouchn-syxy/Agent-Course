"""综合实践使用的人物特征提取 Agent。"""

from __future__ import annotations

import json

from openai.types.chat import (
	ChatCompletionAssistantMessageParam,
	ChatCompletionMessageFunctionToolCallParam,
	ChatCompletionMessageParam,
	ChatCompletionSystemMessageParam,
	ChatCompletionToolMessageParam,
	ChatCompletionUserMessageParam,
)

from inherit.agents.role_play.profile_extractor_agent import ProfileExtractorAgent as InheritedProfileExtractorAgent
from inherit.agents.role_play.tools.extract_profile import ExtractProfile as InheritedExtractProfile
from inherit.llm.tool_registry import ToolDef


class ExtractProfile(InheritedExtractProfile):
	"""将通过校验的 Profile 作为 JSON 对象返回给工具循环。"""

	def to_tool_def(self) -> ToolDef:
		return ToolDef(
			name="extract_features",
			description="从搜索资料中提取完整、可保存的角色画像 JSON，只接受 text 参数。",
			parameters={
				"text": {"type": "string", "description": "待提取的文本内容"},
			},
			required=["text"],
			func=lambda text: self.extract(text).model_dump(),
		)


class ProfileExtractorAgent(InheritedProfileExtractorAgent):
	"""补齐提取参数，并在得到有效画像后可靠保存。"""

	def run(self, name: str) -> str:
		tools = [tool.to_openai_tool() for tool in self._registry.list()]
		messages: list[ChatCompletionMessageParam] = [
			ChatCompletionSystemMessageParam(
				role="system",
				content=self._pm.render("agents/role_play/profile_extractor/system.j2"),
			),
			ChatCompletionUserMessageParam(
				role="user",
				content=self._pm.render("agents/role_play/profile_extractor/task.j2", target_name=name),
			),
		]
		collected_sources: list[str] = []

		for iteration in range(1, self._max_iterations + 1):
			try:
				content, tool_calls = self._llm.chat_with_tools(messages, tools)
			except Exception as exc:
				# 部分兼容 API 会拒绝包含长检索正文的后续工具规划请求。
				# 已收集到资料时仍可由确定性的提取器完成画像，避免半途失败。
				if collected_sources:
					print(f"  [WARN] 工具规划不可用，改用已收集资料提取：{exc}")
					break
				raise
			if not tool_calls:
				# 有资料但模型没有继续发出工具调用时，仍进入确定性收尾。
				if collected_sources:
					print("  [WARN] 模型未继续调用工具，改用已收集资料提取。")
					break
				return content or "（Agent 未返回任何内容）"

			assistant_tool_calls: list[ChatCompletionMessageFunctionToolCallParam] = []
			tool_results: list[tuple[str, str]] = []
			for tool_call in tool_calls:
				try:
					arguments = json.loads(tool_call.function.arguments)
				except json.JSONDecodeError:
					arguments = {}
				name_of_tool = tool_call.function.name
				if name_of_tool == "extract_features" and not arguments.get("text"):
					arguments["text"] = "\n\n".join(collected_sources)[-4000:]

				print(f"  [TOOL {iteration}] {name_of_tool}({json.dumps(arguments, ensure_ascii=False)[:300]})")
				result = self._registry.execute(name_of_tool, **arguments)
				print(f"  [RESULT {iteration}] {result[:300]}")
				if name_of_tool in {"wikipedia_query", "web_search", "read_url"}:
					collected_sources.append(result)
				if name_of_tool == "extract_features":
					try:
						profile_data = json.loads(result)
					except json.JSONDecodeError:
						profile_data = None
					if isinstance(profile_data, dict):
						saved = self._registry.execute("save_yaml", name=name, data=profile_data)
						return f"{saved}\n角色画像提取完成。"

				assistant_tool_calls.append(ChatCompletionMessageFunctionToolCallParam(
					id=tool_call.id,
					type="function",
					function={"name": name_of_tool, "arguments": tool_call.function.arguments},
				))
				tool_results.append((tool_call.id, result))

			messages.append(ChatCompletionAssistantMessageParam(
				role="assistant", content=content, tool_calls=assistant_tool_calls,
			))
			for tool_call_id, result in tool_results:
				messages.append(ChatCompletionToolMessageParam(
					role="tool", tool_call_id=tool_call_id, content=result,
				))

		if collected_sources:
			result = self._registry.execute(
				"extract_features",
				# 兼容接口对过长的网页正文会拒绝请求；画像字段只需要摘要级资料。
				text=f"目标人物：{name}\n" + "\n\n".join(collected_sources)[-4000:],
			)
			try:
				profile_data = json.loads(result)
			except json.JSONDecodeError:
				profile_data = None
			if isinstance(profile_data, dict):
				saved = self._registry.execute("save_yaml", name=name, data=profile_data)
				return f"{saved}\n角色画像提取完成。"

		return "（Agent 达到最大迭代次数，任务未完成）"
