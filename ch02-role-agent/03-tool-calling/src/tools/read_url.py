"""
网页内容读取工具。

抓取指定 URL，优先定位正文区域（article / main / #mw-content-text），
提取可见文本并保留自然段落结构。

依赖：beautifulsoup4 + lxml
"""

from __future__ import annotations

import requests
from bs4 import BeautifulSoup, Tag

from llm.tool_registry import ToolDef
from utils.retry import retry

# 正文区域选择器优先级
CONTENT_SELECTORS: list[str] = [
	"article",
	"main",
	"#mw-content-text",
	'[role="main"]',
	".post-content",
	".article-content",
	".entry-content",
	".content",
]


class ReadUrl:
	"""网页内容读取工具 — 抓取 URL 并提取正文文本。

	用法：
		tool = ReadUrl()
		content = tool.read("https://zh.wikipedia.org/wiki/鲁迅")
	"""


	def __init__(self, timeout: int = 30) -> None:
		"""
		Args:
			timeout: 请求超时秒数。
		"""
		self._timeout: int = timeout


	def read(self, url: str) -> str:
		"""抓取网页并提取正文文本。

		Args:
			url: 目标网页 URL。

		Returns:
			提取的正文文本，保留段落结构。
		"""
		try:
			return self._fetch_page(url)
		except Exception as e:
			return f"读取失败：{e}"


	@retry(max_retries=2, delay_s=1.0)
	def _fetch_page(self, url: str) -> str:
		"""纯网络调用：GET 网页 + BeautifulSoup 解析，由 @retry 处理瞬时故障。"""
		headers = {
			"User-Agent": (
				"Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
				"AppleWebKit/537.36 (KHTML, like Gecko) "
				"Chrome/120.0.0.0 Safari/537.36"
			),
		}
		resp = requests.get(url, headers=headers, timeout=self._timeout)
		resp.raise_for_status()
		resp.encoding = resp.apparent_encoding

		soup = BeautifulSoup(resp.text, "lxml")

		# 剥离噪音标签
		for tag in soup(["script", "style", "nav", "footer", "header", "aside"]):
			tag.decompose()

		# 尝试定位正文区域
		content_root: Tag = soup
		for selector in CONTENT_SELECTORS:
			el = soup.select_one(selector)
			if el is not None:
				content_root = el
				break

		# 移除正文区域内的非文本元素
		for tag in content_root(["img", "svg", "figure", "table", "noscript"]):
			tag.decompose()

		text = content_root.get_text(separator="", strip=True)

		if not text.strip():
			return "（页面无可见文本内容）"

		return text


	def to_tool_def(self) -> ToolDef:
		"""生成此工具的 ToolDef 注册描述。"""
		return ToolDef(
			name="read_url",
			description="抓取指定网页 URL 的正文内容（最多 4000 字符）。用于深入阅读某篇具体文章，获取搜索摘要中未包含的细节信息。",
			parameters={
				"url": {
					"type": "string",
					"description": "目标网页的完整 URL",
				},
			},
			required=["url"],
			func=self.read,
		)


if __name__ == "__main__":
	print("=" * 60)
	print("  ReadUrl 演示")
	print("=" * 60)

	tool = ReadUrl()

	for url in [
		"https://zh.wikipedia.org/wiki/鲁迅",
		"https://invalid.example.com/nonexistent",
	]:
		print(f"\n📄 read(\"{url}\")")
		content = tool.read(url)
		print(f"   {content}...")
		print(f"   （总长度：{len(content)} 字符）")

	print("\n" + "=" * 60)
	print("  演示完成")
	print("=" * 60)
