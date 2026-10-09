"""
ProfileExtractorAgent — 基于 Function Calling 的 Agent 循环。

专用于人物特征提取任务，内置 ToolRegistry，通过 keyword-only 参数注入工具实例。
核心循环（感知 → 思考 → 行动 → 记忆）：
  1. LLM 分析当前状态，决定是否调用工具
  2. 如有 tool_calls → 执行工具 → 注入 messages → 继续循环
  3. 如无 tool_calls → 任务完成，返回最终文本回复

用法：
    from agents.role_play.profile_extractor_agent import ProfileExtractorAgent

    agent = ProfileExtractorAgent(
        llm,
        prompt_manager,
        max_iterations=10,
        tavily_search=TavilySearch(...),
        wikipedia_search=WikipediaSearch(),
        read_url=ReadUrl(),
        save_yaml=SaveYaml(...),
        extract_profile=ExtractProfile(llm, prompt_manager),
    )
    result = agent.run(target_name="鲁迅")
"""

from __future__ import annotations

import json

from openai.types.chat import (
	ChatCompletionAssistantMessageParam,
	ChatCompletionMessageParam,
	ChatCompletionMessageFunctionToolCallParam,
	ChatCompletionSystemMessageParam,
	ChatCompletionToolMessageParam,
	ChatCompletionUserMessageParam, ChatCompletionToolParam,
)

from inherit.agents.role_play.tools.extract_profile import ExtractProfile
from inherit.llm.tool_client import ToolLLMClient
from inherit.llm.tool_registry import ToolRegistry
from inherit.prompt.prompt_manager import PromptManager
from inherit.tools.read_url import ReadUrl
from inherit.tools.save_yaml import SaveYaml
from inherit.tools.tavily_search import TavilySearch
from inherit.tools.wikipedia_search import WikipediaSearch


class ProfileExtractorAgent:
	"""人物特征提取 Agent — 基于 Function Calling 的自主任务执行循环。

	专用于人物特征提取任务，通过搜索 + 提取 + 保存工具链自动构建角色画像。
	工具由调用方通过 keyword-only 参数注入，Agent 内部自行维护 ToolRegistry。
	不依赖 LangChain 等框架，裸写 Agent 循环：
	  while not finished:
		  1. chat_with_tools(messages, tools)
		  2. 有 tool_calls → 逐个执行 → 注入结果
		  3. 无 tool_calls → 返回最终文本
	"""


	def __init__(
			self,
			llm: ToolLLMClient,
			prompt_manager: PromptManager,
			max_iterations: int = 10,
			*,
			tavily_search: TavilySearch | None = None,
			wikipedia_search: WikipediaSearch | None = None,
			read_url: ReadUrl | None = None,
			save_yaml: SaveYaml | None = None,
			extract_profile: ExtractProfile | None = None,
	) -> None:
		"""
		:param llm:              支持 Function Calling 的 LLM 客户端
		:param prompt_manager:    提示词管理器（渲染 agents/role_play/profile_extractor/ 下的模板）
		:param max_iterations:   最大循环轮数，防止无限循环
		:param tavily_search:    Tavily 搜索工具实例，为 None 则不注册
		:param wikipedia_search: Wikipedia 搜索工具实例，为 None 则不注册
		:param read_url:         网页内容抓取工具实例，为 None 则不注册
		:param save_yaml:        YAML 保存工具实例，为 None 则不注册
		:param extract_profile:  特征提取工具实例，为 None 则不注册
		"""
		self._llm = llm
		self._pm = prompt_manager
		self._max_iterations = max_iterations

		# ── 工具注册中心（内部构建）──
		self._registry: ToolRegistry = ToolRegistry()
		for tool in (tavily_search, wikipedia_search, read_url, save_yaml, extract_profile):
			if tool is not None:
				self._registry.register(tool.to_tool_def())


	def run(self, name: str) -> str:
		"""执行任务，返回最终文本结果。

		Args:
			name: 目标人物姓名。

		Returns:
			Agent 的最终文本回复。
		"""
		tools: list[ChatCompletionToolParam] = [t.to_openai_tool() for t in self._registry.list()]

		# 构建初始消息：system_prompt + 渲染后的用户任务
		system_prompt = self._pm.render("agents/role_play/profile_extractor/system.j2")
		user_prompt = self._pm.render("agents/role_play/profile_extractor/task.j2", target_name=name)
		messages: list[ChatCompletionMessageParam] = [
			ChatCompletionSystemMessageParam(role="system", content=system_prompt),
			ChatCompletionUserMessageParam(role="user", content=user_prompt),
		]

		for iteration in range(1, self._max_iterations + 1):
			content, tool_calls = self._llm.chat_with_tools(messages, tools)

			# 无工具调用 → 直接返回文本回复
			if not tool_calls:
				return content or "（Agent 未返回任何内容）"

			# 有工具调用 → 逐个执行
			assistant_tool_calls: list[ChatCompletionMessageFunctionToolCallParam] = []
			tool_results: list[tuple[str, str]] = []

			for tc in tool_calls:
				fn_name = tc.function.name
				try:
					fn_args = json.loads(tc.function.arguments)
				except json.JSONDecodeError:
					fn_args = {}

				# 执行前打印日志
				args_display = json.dumps(fn_args, ensure_ascii=False)
				print(f"  🔧 [{iteration}] {fn_name}({args_display})")

				result = self._registry.execute(fn_name, **fn_args)

				# 截断过长输出用于显示
				if len(result) > 300:
					display = result[:300] + "..."
				else:
					display = result
				print(f"  📦 [{iteration}] 返回: {display}")

				assistant_tool_calls.append(ChatCompletionMessageFunctionToolCallParam(
					id=tc.id,
					type="function",
					function={"name": fn_name, "arguments": tc.function.arguments},
				))
				tool_results.append((tc.id, result))

			# 注入 assistant(tool_calls) + 各 tool 结果消息
			messages.append(ChatCompletionAssistantMessageParam(
				role="assistant",
				content=content,
				tool_calls=assistant_tool_calls,
			))
			for tool_call_id, result in tool_results:
				messages.append(ChatCompletionToolMessageParam(
					role="tool",
					tool_call_id=tool_call_id,
					content=result,
				))

		# 超出最大迭代次数 → 强制要求 LLM 总结
		print(f"  ⚠️ 达到最大迭代次数 {self._max_iterations}，要求 Agent 给出最终回复...")
		final_content, _ = self._llm.chat_with_tools(messages, tools)
		return final_content or "（Agent 达到最大迭代次数，任务未完成）"


if __name__ == "__main__":
	"""
	简单演示：让 Agent 使用 web_search + wikipedia_query 查询鲁迅的生平。
	需要先配置好 config.yaml 中的 API Key。
	"""

	from config import Config
	from inherit.utils.path import get_prj_root

	print("=" * 60)
	print("  ProfileExtractorAgent 演示")
	print("=" * 60)

	# ── 初始化 ──
	cfg = Config.from_yaml()
	llm = ToolLLMClient(
		api_key=cfg.llm.api_key_env,
		base_url=cfg.llm.base_url,
		model=cfg.llm.model,
		temperature=cfg.generation.temperature,
		top_p=cfg.generation.top_p,
		max_tokens=cfg.generation.max_tokens,
	)

	pm = PromptManager(get_prj_root() / "prompts")

	# ── 创建 Agent 并执行 ──
	agent: ProfileExtractorAgent = ProfileExtractorAgent(
		llm=llm,
		prompt_manager=pm,
		max_iterations=5,
		tavily_search=TavilySearch(
			api_key=cfg.tavily.api_key,
			max_results=cfg.tavily.max_results,
			include_answer=cfg.tavily.include_answer,
		),
		wikipedia_search=WikipediaSearch(),
	)

	name = "鲁迅"
	print(f"\n📋 目标人物: {name}\n")
	result = agent.run(name)
	print(f"\n✅ 最终结果:\n{result}")
