"""
电商客服工作台视觉理解 — CLI 入口。

支持两种运行模式：
  - analyze：截图 → VLM 分析 → UI 结构 + 消息内容
  - locate：  截图 → VLM 定位 → 元素屏幕坐标

用法:
    python main.py --image screenshot.png --mode analyze
    python main.py --image screenshot.png --mode locate --target "发送按钮"
    python main.py --image screenshot.png --mode analyze --context "三栏布局：..."
"""

from __future__ import annotations

import argparse
from pathlib import Path

from PIL import Image

from agents.eshop_service.vision.element_locator import ElementLocator
from agents.eshop_service.vision.models.types import (
	ElementLocation,
	ScreenAnalysis,
)
from agents.eshop_service.vision.screen_analyzer import ScreenAnalyzer
from config import Config
from inherit.prompt.prompt_manager import PromptManager
from inherit.utils.path import get_prj_root
from vlm.client import VLMClient


# ============================================================
# 命令行参数
# ============================================================

def parse_args() -> argparse.Namespace:
	"""解析命令行参数。"""
	parser: argparse.ArgumentParser = argparse.ArgumentParser(
		description="电商客服工作台视觉理解 — 截图分析与元素定位",
		formatter_class=argparse.RawDescriptionHelpFormatter,
		epilog="""
示例:
    python main.py --image screenshot.png --mode analyze
    python main.py --image screenshot.png --mode analyze --context "三栏布局：左客户列表、中聊天区、右信息面板"
    python main.py --image screenshot.png --mode locate --target "发送按钮"
		""",
	)
	parser.add_argument(
		"--image", required=True, type=str, metavar="PATH",
		help="截图文件路径（必填）",
	)
	parser.add_argument(
		"--mode", required=True, choices=["analyze", "locate"],
		help="运行模式：analyze（截图分析）| locate（元素定位）",
	)
	parser.add_argument(
		"--context", type=str, default="",
		help="业务领域上下文描述，注入提示词模板（可选，默认为空）",
	)
	parser.add_argument(
		"--target", type=str, default="",
		help="定位目标元素描述（mode=locate 时必填），如 '发送按钮'",
	)
	return parser.parse_args()


# ============================================================
# 输出格式化
# ============================================================

def _print_analysis(result: ScreenAnalysis) -> None:
	"""打印 ScreenAnalysis 结果。"""
	print("\n" + "=" * 60)
	print("📊 截图分析结果")
	print("=" * 60)

	if result.active_customer:
		print(f"\n👤 活跃客户: {result.active_customer}")

	print(f"\n📐 识别到 {len(result.regions)} 个功能区域：")
	for region in result.regions:
		b = region.bbox
		print(f"  ▸ {region.name}")
		print(f"    边界: ({b.x}, {b.y}) → ({b.x + b.width}, {b.y + b.height}), {b.width}×{b.height}")
		if region.elements:
			print(f"    可交互元素 ({len(region.elements)}):")
			for elem in region.elements:
				print(f"      • {elem.name} @ ({elem.center_x}, {elem.center_y})")

	if result.messages:
		print(f"\n💬 聊天区消息 ({len(result.messages)} 条):")
		for msg in result.messages:
			unread = " 🔴" if msg.has_unread else ""
			print(f"  [{msg.customer_name}]{unread}: {msg.content}")

	if result.raw_text:
		print(f"\n📝 截图全文识别 ({len(result.raw_text)} 字符):\n  {result.raw_text}")


def _print_location(result: ElementLocation) -> None:
	"""打印 ElementLocation 结果。"""
	print("\n" + "=" * 60)
	print("🎯 元素定位结果")
	print("=" * 60)
	print(f"  元素名称: {result.element_name}")
	print(f"  置信度:   {result.confidence:.0%}")
	if result.confidence > 0:
		print(f"  中心坐标: ({result.center_x}, {result.center_y})")
		b = result.bbox
		print(f"  边界框:   ({b.x}, {b.y}) → ({b.x + b.width}, {b.y + b.height}), {b.width}×{b.height}")
	else:
		print("  ⚠️ 未找到目标元素")


# ============================================================
# 主入口
# ============================================================

def main() -> None:
	"""程序入口。"""
	args: argparse.Namespace = parse_args()

	# ── 参数校验 ──────────────────────────────────────────
	if args.mode == "locate" and not args.target:
		print("❌ mode=locate 时必须提供 --target 参数")
		raise SystemExit(1)

	image_path: Path = Path(args.image)
	if not image_path.exists():
		print(f"❌ 截图文件不存在: {image_path}")
		raise SystemExit(1)

	# ── 加载配置 ──────────────────────────────────────────
	cfg: Config = Config.from_yaml()

	# ── 构造 VLM 客户端 ────────────────────────────────────
	vlm: VLMClient = VLMClient(
		api_key=cfg.vlm.api_key_env,
		base_url=cfg.vlm.base_url,
		model=cfg.vlm.model,
		provider=cfg.vlm.provider,
	)
	print(f"🔌 VLM: {cfg.vlm.provider}/{cfg.vlm.model} @ {cfg.vlm.base_url}")

	# ── 加载截图 ──────────────────────────────────────────
	screenshot: Image.Image = Image.open(image_path)
	print(f"📷 截图: {image_path.name} ({screenshot.width}×{screenshot.height})")

	# ── 业务上下文 ────────────────────────────────────────
	context: str | None = args.context

	# ── Prompt 管理器 ─────────────────────────────────────
	pm: PromptManager = PromptManager(get_prj_root() / "prompts")

	# ── 运行 ──────────────────────────────────────────────
	if args.mode == "analyze":
		analyzer: ScreenAnalyzer = ScreenAnalyzer(vlm, pm)
		result: ScreenAnalysis = analyzer.analyze(context, screenshot)
		_print_analysis(result)

	elif args.mode == "locate":
		locator: ElementLocator = ElementLocator(vlm, pm)
		result: ElementLocation = locator.locate(context, screenshot, args.target)
		_print_location(result)

	print("\n✅ 完成")


if __name__ == "__main__":
	main()
