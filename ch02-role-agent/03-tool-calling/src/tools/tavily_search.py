"""
Tavily Web Search 工具。

通过 Tavily Search API 进行网页搜索，专为 AI Agent 优化。
免费层 1000 次/月，注册即用：https://tavily.com

设计要点：
  - 配置通过类字段管理，不直接读 config.yaml
  - 搜索失败返回错误信息字符串（不抛异常），便于 Agent 处理
"""

from __future__ import annotations

from typing import Any

import requests

from llm.tool_registry import ToolDef
from utils.retry import retry

TAVILY_API_URL: str = "https://api.tavily.com/search"


class TavilySearch:
	"""Tavily Search API 封装，配置由构造参数显式传入。

	用法：
		tool = TavilySearch(api_key="tvly-xxx", max_results=5)
		results = tool.search("鲁迅 生平")
	"""


	def __init__(
			self,
			api_key: str,
			max_results: int = 5,
			include_answer: bool = False,
			timeout: int = 15,
	) -> None:
		"""
		Args:
			api_key: Tavily API 密钥（注册地址: https://tavily.com）。
			max_results: 每次搜索最大返回结果数。
			include_answer: 是否包含 AI 生成的综合回答。
			timeout: 请求超时秒数。
		"""
		self._api_key: str = api_key
		self._max_results: int = max_results
		self._include_answer: bool = include_answer
		self._timeout: int = timeout


	def search(self, query: str, max_results: int | None = None) -> list[dict[str, str]]:
		"""执行网页搜索，返回结构化结果列表。

		Args:
			query: 搜索关键词。
			max_results: 本次调用的最大结果数，不传则用实例默认值。

		Returns:
			搜索结果列表，每项含 title / content / url。
			失败时返回含 error 键的单元素列表。
		"""
		if not self._api_key or "your-" in self._api_key.lower():
			return [{"error": "请在 TavilySearch 中设置有效的 api_key（注册地址: https://tavily.com）"}]

		if max_results is not None:
			limit: int = min(max_results, self._max_results)
		else:
			limit: int = self._max_results

		try:
			return self._search_api(query, limit)
		except Exception as e:
			return [{"error": f"搜索失败：{e}"}]


	@retry(max_retries=3, delay_s=2.0)
	def _search_api(self, query: str, limit: int) -> list[dict[str, str]]:
		"""纯网络调用：POST Tavily Search API，由 @retry 处理瞬时故障。"""
		payload: dict[str, Any] = {
			"api_key": self._api_key,
			"query": query,
			"max_results": limit,
			"include_answer": self._include_answer,
		}
		resp = requests.post(
			TAVILY_API_URL,
			json=payload,
			headers={"Content-Type": "application/json"},
			timeout=self._timeout,
		)
		resp.raise_for_status()
		data = resp.json()

		results: list[dict[str, str]] = []
		for item in data.get("results", []):
			results.append({
				"title": item.get("title", ""),
				"content": item.get("content", ""),
				"url": item.get("url", ""),
			})

		if not results:
			return [{"message": f"未找到与 '{query}' 相关的结果"}]

		return results


	def to_tool_def(self) -> ToolDef:
		"""生成此工具的 ToolDef 注册描述。"""
		return ToolDef(
			name="web_search",
			description="搜索互联网获取人物资料。返回标题、摘要、URL 的结构化列表。",
			parameters={
				"query": {
					"type": "string",
					"description": "搜索关键词（如 '鲁迅 生平事迹'）",
				},
				"max_results": {
					"type": "integer",
					"description": "最大返回结果数（默认 5）",
					"default": 5,
				},
			},
			required=["query"],
			func=self.search,
		)


if __name__ == "__main__":
	from config import Config

	print("=" * 60)
	print("  TavilySearch 演示")
	print("=" * 60)

	# ── 从 config.yaml 加载配置用于演示 ──
	cfg: Config = Config.from_yaml()
	tool = TavilySearch(
		api_key=cfg.tavily.api_key,
		max_results=cfg.tavily.max_results,
		include_answer=cfg.tavily.include_answer,
	)

	print(f"  api_key: {'***' + cfg.tavily.api_key[-4:] if cfg.tavily.api_key else '(未设置)'}")
	print(f"  max_results: {cfg.tavily.max_results}")
	print(f"  include_answer: {cfg.tavily.include_answer}")

	# ── 测试 1：正常搜索 ──
	query = "鲁迅 生平 简介"
	print(f"\n🔍 search(\"{query}\", max_results=3)")
	results = tool.search(query, max_results=3)
	if results and "error" not in results[0] and "message" not in results[0]:
		for i, r in enumerate(results, 1):
			print(f"\n  [{i}] {r.get('title', '无标题')}")
			print(f"      {r.get('content', '')[:120]}...")
			print(f"      {r.get('url', '')}")
	else:
		print(f"  {results}")

	# ── 测试 2：无意义关键词 ──
	query2 = "zxcvbnmasdfghjkl"
	print(f"\n🔍 search(\"{query2}\")（无意义关键词）")
	results2 = tool.search(query2)
	print(f"  {results2}")

	print("\n" + "=" * 60)
	print("  演示完成")
	print("=" * 60)
