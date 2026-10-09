"""知识点查询工具 — 基于 WikipediaSearch 查询权威定义。

用法：
    from agents.review.tools.lookup_knowledge_point import LookupKnowledgePoint

    tool = LookupKnowledgePoint(language="zh")
    results = tool.lookup("哈夫曼树")
"""

from __future__ import annotations

import json

from inherit.llm.tool_registry import ToolDef
from inherit.tools.wikipedia_search import WikipediaSearch


class LookupKnowledgePoint:
	"""从 Wikipedia 查询数据结构的权威定义和解释。"""


	def __init__(self, language: str = "zh") -> None:
		"""
		Args:
			language: Wikipedia 语言子域名（zh / en）
		"""
		self._wiki: WikipediaSearch = WikipediaSearch(language=language)


	def lookup(self, concept: str) -> str:
		"""从 Wikipedia 查询知识点的权威定义。

		Args:
			concept: 要查询的概念名称（如 "二叉搜索树"）

		Returns:
			JSON 格式的 Wikipedia 条目摘要列表
		"""
		results: list[dict[str, str]] = self._wiki.search(concept, max_results=2)
		return json.dumps(results, ensure_ascii=False, indent=2)


	def to_tool_def(self) -> ToolDef:
		"""生成 ToolDef 注册描述。"""
		return ToolDef(
			name="lookup_knowledge_point",
			description="从 Wikipedia 查询数据结构的权威定义和解释。用于获取准确的概念描述。",
			parameters={
				"concept": {
					"type": "string",
					"description": "要查询的概念名称，如 '哈夫曼树'、'图的广度优先遍历'",
				},
			},
			required=["concept"],
			func=self.lookup,
		)
