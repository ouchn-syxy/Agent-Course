"""
Token 计数工具模块。

支持两种 token 计数方式：
1. tiktoken 精确计数 — 当 model 参数匹配已知 OpenAI 模型时自动使用。
2. DeepSeek 字符估算 — 当 model 不受 tiktoken 支持时作为兜底方案。

算法来源（DeepSeek 官方文档）：
- 1 个英文字符 ≈ 0.3 个 token
- 1 个中文字符 ≈ 0.6 个 token
"""

from __future__ import annotations

import re

import tiktoken

# 已知的 OpenAI 模型 → tiktoken encoding 映射
MODEL_ENCODING: dict[str, str] = {
	"gpt-4": "cl100k_base",
	"gpt-4-turbo": "cl100k_base",
	"gpt-4o": "o200k_base",
	"gpt-3.5-turbo": "cl100k_base",
	"text-embedding-3-small": "cl100k_base",
}


def estimate_tokens_deepseek(text: str) -> int:
	"""使用 DeepSeek 官方推荐的算法估算 token 数。

	算法来源：DeepSeek 官方文档
	- 1 个英文字符 ≈ 0.3 个 token
	- 1 个中文字符 ≈ 0.6 个 token

	Args:
		text: 输入文本。

	Returns:
		估算的 token 数量（至少为 1）。
	"""
	if not text:
		return 0

	chinese_chars = len(re.findall(r'[\u4e00-\u9fff\u3400-\u4dbf]', text))
	english_chars = len(re.findall(r'[^\u4e00-\u9fff\u3400-\u4dbf\s]', text))

	tokens = chinese_chars * 0.6 + english_chars * 0.3
	return max(1, round(tokens))


def estimate_tokens(text: str, model: str | None = None) -> int:
	"""统一的 token 估算接口。

	当 model 参数匹配 MODEL_ENCODING 中的已知模型时，优先使用 tiktoken 精确计数；
	否则回退到 DeepSeek 官方推荐的字符估计算法。

	Args:
		text: 输入文本。
		model: 可选模型名。若在 MODEL_ENCODING 中则用 tiktoken 精确计数，否则用字符估算。

	Returns:
		token 数量（至少为 1）。
	"""
	if model and model in MODEL_ENCODING:
		try:
			encoding_name: str = MODEL_ENCODING[model]
			encoding = tiktoken.get_encoding(encoding_name)
			return len(encoding.encode(text))
		except ImportError:
			pass  # tiktoken 未安装时回退到字符估算

	return estimate_tokens_deepseek(text)


if __name__ == "__main__":
	print("=" * 50)
	print("  estimate_tokens_deepseek() 演示")
	print("=" * 50)

	samples: list[tuple[str, str]] = [
		("你好世界", "纯中文"),
		("Hello world", "纯英文"),
		("你好 world，今天 weather 不错", "中英混合"),
		("", "空字符串"),
		("人工智能正在改变世界的每一个角落，从医疗到教育。", "长中文"),
	]
	for text, desc in samples:
		tokens: int = estimate_tokens_deepseek(text)
		print(f"  [{desc}] \"{text[:30]}\" → {tokens} tokens")

	print()
	print("=" * 50)
	print("  estimate_tokens() 演示")
	print("=" * 50)

	for text, desc in samples:
		tokens = estimate_tokens(text)
		print(f"  [{desc}] \"{text[:30]}\" → {tokens} tokens（默认 DeepSeek 估算）")

	print()
	print("=" * 50)
	print("  MODEL_ENCODING 已知模型列表")
	print("=" * 50)
	for model_name in MODEL_ENCODING:
		print(f"  {model_name} → {MODEL_ENCODING[model_name]}")
	print("  注：传入 model 参数时会优先用 tiktoken 精确计数")
