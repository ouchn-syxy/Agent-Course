"""搜索参考题目工具 — 基于 TavilySearch 搜索真实考试题目。

用法：
    from agents.review.tools.search_reference_questions import SearchReferenceQuestions

    tool = SearchReferenceQuestions(tavily_api_key="tvly-xxx")
    results = tool.search("二叉树遍历", difficulty="中等")
"""

from __future__ import annotations

import json

from inherit.llm.tool_registry import ToolDef
from inherit.tools.tavily_search import TavilySearch


class SearchReferenceQuestions:
	"""搜索互联网获取真实考试题目作为出题参考。"""


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


	def search(self, topic: str, difficulty: str | None = None) -> str:
		"""搜索真实考试题目作为出题参考。

		Args:
			topic: 知识点主题（如 "二叉树遍历"）
			difficulty: 难度级别（可选，如 "简单"、"中等"、"困难"）

		Returns:
			JSON 格式的搜索结果列表
		"""
		query: str = f"{topic} 数据结构 考试题 练习题"
		if difficulty:
			query += f" {difficulty}"
		if not self._available:
			return "[]"
		try:
			results: list[dict[str, str]] = self._tavily.search(query, max_results=3)
		except Exception as exc:
			# 联网参考题是增强信息，不能让失效的可选 API 阻断本地出题。
			self._available = False
			print(f"[提示] Tavily 不可用，后续题目将仅使用本地知识点：{exc}")
			return "[]"
		return json.dumps(results, ensure_ascii=False, indent=2)


	def to_tool_def(self) -> ToolDef:
		"""生成 ToolDef 注册描述。"""
		return ToolDef(
			name="search_reference_questions",
			description="搜索互联网获取真实考试题目作为出题参考。用于查看类似知识点是如何出题的。",
			parameters={
				"topic": {
					"type": "string",
					"description": "知识点主题，如 '二叉树遍历'、'哈希表冲突解决'",
				},
				"difficulty": {
					"type": "string",
					"description": "难度级别：简单、中等、困难。不传则不限制难度。",
				},
			},
			required=["topic"],
			func=self.search,
		)
