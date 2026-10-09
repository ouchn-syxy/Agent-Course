"""
Wikipedia 查询工具。

通过 Wikipedia API 搜索人物资料，免费免 Key，返回结构化百科摘要。
优先搜索中文维基百科（zh.wikipedia.org）。

设计要点：
  - 单次 API 调用同时完成搜索 + 摘要获取（generator=search + prop=extracts）
  - 失败返回包含 error/message 键的字典列表（不抛异常），便于 Agent 统一处理
"""

from __future__ import annotations

from typing import Any

import requests

from inherit.llm.tool_registry import ToolDef
from inherit.utils.retry import retry

WIKI_API_URL: str = "https://zh.wikipedia.org/w/api.php"


class WikipediaSearch:
	"""Wikipedia 查询工具，搜索百科条目并返回摘要。

	用法：
		tool = WikipediaSearch(language="zh")
		results = tool.search("鲁迅")
	"""


	def __init__(self, language: str = "zh", timeout: int = 15) -> None:
		"""
		Args:
			language: Wikipedia 语言子域名（zh / en）。
			timeout: 请求超时秒数。
		"""
		self._language: str = language
		self._timeout: int = timeout


	def search(self, query: str, max_results: int = 5) -> list[dict[str, str]]:
		"""搜索 Wikipedia 条目并返回摘要列表。

		Args:
			query: 搜索关键词。
			max_results: 最大返回条目数（上限 10）。

		Returns:
			条目列表，每项含 title / content / url。
			失败或无结果时返回含 error 或 message 键的单元素列表。
		"""
		try:
			return self._query_api(query, min(max_results, 10))
		except Exception as e:
			return [{"error": f"Wikipedia 查询失败：{e}"}]


	@retry(max_retries=3, delay_s=2.0)
	def _query_api(self, query: str, limit: int) -> list[dict[str, str]]:
		"""纯网络调用：GET Wikipedia API，由 @retry 处理瞬时故障。"""
		params: dict[str, Any] = {
			"action": "query",
			"generator": "search",
			"gsrsearch": query,
			"gsrlimit": limit,
			"prop": "extracts|info",
			"exintro": 1,
			"explaintext": 1,
			"inprop": "url",
			"format": "json",
		}
		headers = {
			"User-Agent": (
				"Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
				"AppleWebKit/537.36 (KHTML, like Gecko) "
				"Chrome/120.0.0.0 Safari/537.36"
			),
		}
		resp = requests.get(
			WIKI_API_URL, params=params, headers=headers, timeout=self._timeout,
		)
		resp.raise_for_status()
		data = resp.json()

		pages = data.get("query", {}).get("pages", {})
		if not pages:
			return [{"message": f"Wikipedia 未找到与 '{query}' 相关的结果"}]

		results: list[dict[str, str]] = []
		for page_id in sorted(pages.keys(), key=int):
			page = pages[page_id]
			results.append({
				"title": page.get("title", ""),
				"content": page.get("extract", ""),
				"url": page.get(
					"fullurl",
					f"https://{self._language}.wikipedia.org/wiki/{page.get('title', '')}",
				),
			})

		return results


	def to_tool_def(self) -> ToolDef:
		"""生成此工具的 ToolDef 注册描述。"""
		return ToolDef(
			name="wikipedia_query",
			description="搜索 Wikipedia 百科条目，返回标题、摘要和 URL。信息比网页搜索更权威、噪音更少，适合获取人物的标准生平资料。",
			parameters={
				"query": {
					"type": "string",
					"description": "搜索关键词（如 '鲁迅'）",
				},
				"max_results": {
					"type": "integer",
					"description": "最大返回条目数（默认 5）",
					"default": 5,
				},
			},
			required=["query"],
			func=self.search,
		)


if __name__ == "__main__":
	print("=" * 60)
	print("  WikipediaSearch 演示")
	print("=" * 60)

	tool = WikipediaSearch()

	for query in ["鲁迅", "苏轼 生平", "zxcvbnm12345"]:
		print(f"\n🔍 search(\"{query}\", max_results=3)")
		results = tool.search(query, max_results=3)
		for i, r in enumerate(results, 1):
			if "error" in r:
				print(f"  ❌ {r['error']}")
			elif "message" in r:
				print(f"  ℹ️ {r['message']}")
			else:
				print(f"  [{i}] {r.get('title', '')}")
				print(f"      {r.get('content', '')[:120]}...")
				print(f"      {r.get('url', '')}")

	print("\n" + "=" * 60)
	print("  演示完成")
	print("=" * 60)
