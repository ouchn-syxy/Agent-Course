"""事实核查工具 — 基于 TavilySearch 验证学生答案。

用法：
    from agents.review.tools.search_fact_check import SearchFactCheck

    tool = SearchFactCheck(tavily_api_key="tvly-xxx")
    results = tool.check("前序遍历是根左右", context="二叉树遍历")
"""

from __future__ import annotations

import json

from inherit.llm.tool_registry import ToolDef
from inherit.tools.tavily_search import TavilySearch


class SearchFactCheck:
	"""搜索互联网验证学生答案中的关键陈述是否正确。"""


	def __init__(self, tavily_api_key: str, max_results: int = 5) -> None:
		"""
		Args:
			tavily_api_key: Tavily API 密钥
			max_results: 单次搜索最大返回结果数
		"""
		self._tavily: TavilySearch = TavilySearch(
			api_key=tavily_api_key,
			max_results=max_results,
		)
		self._available: bool = True


	def check(self, statement: str, context: str | None = None) -> str:
		"""搜索互联网进行事实核查。

		Args:
			statement: 待核查的关键陈述或论断
			context: 补充上下文（如知识点名称），用于提高搜索精度

		Returns:
			JSON 格式的搜索结果列表
		"""
		query: str = f"{context} {statement}" if context else statement
		if not self._available:
			return "[]"
		try:
			results: list[dict[str, str]] = self._tavily.search(query, max_results=3)
		except Exception as exc:
			# 事实检索为增强项；不可用时由批改器依据题目与参考答案继续工作。
			self._available = False
			print(f"[提示] Tavily 不可用，后续批改将跳过联网核查：{exc}")
			return "[]"
		return json.dumps(results, ensure_ascii=False, indent=2)


	def to_tool_def(self) -> ToolDef:
		"""生成 ToolDef 注册描述。"""
		return ToolDef(
			name="search_fact_check",
			description="搜索互联网验证学生答案中的关键陈述是否正确。用于批改时的事实核查。",
			parameters={
				"statement": {
					"type": "string",
					"description": "待核查的关键陈述或论断",
				},
				"context": {
					"type": "string",
					"description": "补充上下文，如相关的知识点名称。用于提高搜索精度。",
				},
			},
			required=["statement"],
			func=self.check,
		)
