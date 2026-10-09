"""资料研究员 Agent — 收集主题相关的背景资料和最新信息。

Researcher 是可选增强模块，在 Planner 和 Writer 之间插入，
使用 Wikipedia 获取权威背景，Tavily 搜索最新资料，ReadUrl 深入阅读，
最后整理成结构化资料包交给 Writer。
"""

from __future__ import annotations

import json

from openai.types.chat import (
	ChatCompletionMessageParam,
	ChatCompletionSystemMessageParam,
	ChatCompletionUserMessageParam,
	ChatCompletionAssistantMessageParam,
	ChatCompletionToolMessageParam,
	ChatCompletionMessageFunctionToolCallParam,
)
from pydantic import BaseModel, Field

from agents.write_studio.base import BaseRoleAgent, RoleMeta
from inherit.llm.tool_client import ToolLLMClient
from inherit.llm.tool_registry import ToolRegistry
from inherit.tools.wikipedia_search import WikipediaSearch
from inherit.tools.tavily_search import TavilySearch
from inherit.tools.read_url import ReadUrl


class ResearcherInput(BaseModel):
	"""Researcher 输入模型。"""
	
	topic: str = Field(description="文章主题")
	audience: str = Field(description="目标读者")
	core_message: str = Field(description="核心信息（来自 Planner）")
	outline: list[str] = Field(description="大纲要点（来自 Planner）")
	search_keywords: list[str] = Field(default_factory=list, description="搜索关键词建议")


class ResearchSource(BaseModel):
	"""单个资料来源。"""
	
	source_type: str = Field(description="来源类型：wikipedia / web / article")
	title: str = Field(description="标题")
	url: str = Field(default="", description="URL 地址")
	summary: str = Field(description="摘要或关键信息")
	relevance: str = Field(description="与主题的相关性：high / medium / low")


class ResearcherOutput(BaseModel):
	"""Researcher 输出模型。"""
	
	topic: str = Field(description="主题")
	sources: list[ResearchSource] = Field(description="收集到的资料来源列表")
	key_findings: list[str] = Field(description="关键发现和要点")
	background_context: str = Field(description="背景知识综述")
	latest_developments: str = Field(default="", description="最新进展（如有）")
	recommendations: list[str] = Field(default_factory=list, description="写作建议（基于调研）")
	notes: str = Field(default="", description="补充说明")


class ResearcherAgent(BaseRoleAgent[ResearcherInput, ResearcherOutput]):
	"""资料研究员 — 为写作收集背景资料和最新信息。
	
	工作流程：
	  1. 根据主题和大纲确定调研方向
	  2. 初始化工具注册表（Wikipedia / Tavily / ReadUrl）
	  3. LLM 自主决定调用哪些工具、传什么参数
	  4. 执行工具调用并收集结果（最多3轮）
	  5. 让 LLM 整理成结构化资料包
	
	与其他 Agent 的区别：
	  - 继承 BaseRoleAgent 保持接口一致
	  - 覆盖 run() 方法实现工具调用逻辑
	  - 需要 ToolLLMClient（而非普通 LLMClient）
	  - 构造时需要传入 tavily_api_key
	"""
	
	def __init__(
		self,
		llm: ToolLLMClient,  # 注意：需要 ToolLLMClient
		pm,
		tavily_api_key: str = "",
		max_tool_rounds: int = 3,
	) -> None:
		"""
		Args:
			llm: 支持 Function Calling 的 ToolLLMClient。
			pm: Prompt 管理器。
			tavily_api_key: Tavily API 密钥（可选，未设置则工具会返回提示信息）。
			max_tool_rounds: 最大工具调用轮次（防止无限循环）。
		"""
		super().__init__(llm, pm)
		self._max_tool_rounds = max_tool_rounds
		
		# 初始化工具注册表
		self._registry = ToolRegistry()
		self._registry.register(WikipediaSearch().to_tool_def())
		self._registry.register(TavilySearch(api_key=tavily_api_key).to_tool_def())
		self._registry.register(ReadUrl().to_tool_def())
	
	@classmethod
	def meta(cls) -> RoleMeta:
		return RoleMeta(
			role_id="researcher",
			role_name="资料研究员",
			role_description="收集主题相关的背景资料、权威观点和最新进展",
			quality_focus=[
				"资料权威性和可信度",
				"信息时效性和准确性",
				"内容覆盖完整性",
				"来源多样性",
			],
		)
	
	@classmethod
	def input_model(cls) -> type[ResearcherInput]:
		return ResearcherInput
	
	@classmethod
	def output_model(cls) -> type[ResearcherOutput]:
		return ResearcherOutput
	
	def run(self, task: ResearcherInput) -> ResearcherOutput:
		"""执行资料研究任务（覆盖 BaseRoleAgent.run()）。
		
		与基类 run() 的区别：
		  - 使用 ToolLLMClient.chat_with_tools() 而非 chat_with_json()
		  - 支持多轮工具调用
		  - 最后一轮才要求返回结构化 JSON
		
		Args:
			task: ResearcherInput 输入模型实例。
		
		Returns:
			ResearcherOutput 输出模型实例。
		"""
		# 1. 渲染 prompts
		system_prompt = self._pm.render(
			f"agents/write_studio/{self.meta().role_id}/system.j2",
			available_tools=", ".join([t.name for t in self._registry.list()]),
		)
		
		user_prompt = self._pm.render(
			f"agents/write_studio/{self.meta().role_id}/task.j2",
			**task.model_dump(),
		)
		
		# 2. 初始化消息列表
		messages: list[ChatCompletionMessageParam] = [
			ChatCompletionSystemMessageParam(role="system", content=system_prompt),
			ChatCompletionUserMessageParam(role="user", content=user_prompt),
		]
		
		# 3. 工具调用循环
		tools_schema = [t.to_openai_tool() for t in self._registry.list()]
		
		for round_num in range(self._max_tool_rounds):
			# 调用 LLM（可能返回工具调用）
			content, tool_calls = self._llm.chat_with_tools(
				messages=messages,
				tools=tools_schema,
				tool_choice="auto",
			)
			
			if not tool_calls:
				# LLM 没有调用工具，进入最后整理阶段
				break
			
			# 先添加 assistant 消息（包含所有 tool_calls）
			assistant_tool_calls: list[ChatCompletionMessageFunctionToolCallParam] = []
			
			for tc in tool_calls:
				assistant_tool_calls.append(
					ChatCompletionMessageFunctionToolCallParam(
						id=tc.id,
						type="function",
						function={"name": tc.function.name, "arguments": tc.function.arguments},
					)
				)
			
			messages.append(ChatCompletionAssistantMessageParam(
				role="assistant",
				content=content,
				tool_calls=assistant_tool_calls,
			))
			
			# 再执行工具并添加 tool 消息
			for tc in tool_calls:
				fn_name = tc.function.name
				fn_args = json.loads(tc.function.arguments)
				
				# 执行工具
				result = self._registry.execute(fn_name, **fn_args)
				
				# 追加 tool 结果
				messages.append(ChatCompletionToolMessageParam(
					role="tool",
					tool_call_id=tc.id,
					content=result[:4000],  # 限制长度避免 token 超限
				))
		
		# 4. 让 LLM 整理资料并返回结构化输出
		from inherit.utils.model_render import render_model_code
		
		summary_prompt = f"""
现在你已经收集了足够的资料。请将所有资料整理成结构化的 JSON 格式。

输出 Schema：
```python
{render_model_code(self.output_model())}
```

要求：
1. sources 列表：列出所有查询到的资料来源，标注类型和相关性
2. key_findings：提炼3-5个关键发现
3. background_context：撰写2-3段背景知识综述
4. latest_developments：如果有最新进展，简要说明
5. recommendations：给 Writer 的3-5条写作建议

请直接返回 JSON，不要包含任何额外说明或 markdown 标记。
"""
		
		messages.append(ChatCompletionUserMessageParam(role="user", content=summary_prompt))
		
		# 使用 chat_with_json 强制返回 JSON
		output_text = self._llm.chat_with_json(messages)
		
		# 5. 解析并校验输出
		try:
			raw_dict = json.loads(output_text)
			return self.output_model().model_validate(raw_dict)
		except Exception as e:
			# 如果解析失败，返回一个兜底的输出
			return ResearcherOutput(
				topic=task.topic,
				sources=[],
				key_findings=["工具调用完成，但结果整理失败"],
				background_context=f"由于技术问题，无法完整整理资料：{e}",
				latest_developments="",
				recommendations=["建议基于主题进行独立研究"],
				notes=f"原始输出：{output_text[:500]}...",
			)
