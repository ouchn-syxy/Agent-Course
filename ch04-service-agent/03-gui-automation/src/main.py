"""
电商客服 GUI 自动回复 — CLI 入口。

组装视觉决策（VLM-FC）、键鼠执行（Window/Input）和
回复流水线（分类→策略→生成），启动 ReAct 循环自动处理客户消息。

用法:
    python main.py                          # 默认 max_steps=50
    python main.py --max-steps 20           # 自定义步数上限
    python main.py --quiet                  # 安静模式
"""

from __future__ import annotations

import argparse
from pathlib import Path

from agents.eshop_service.gui_reply_agent import GUIReplyAgent
from config import Config
from inherit.agents.eshop_service.message_category_manager import MessageCategoryManager
from inherit.agents.eshop_service.message_classifier import MessageClassifier
from inherit.agents.eshop_service.reply_generator import ReplyGenerator
from inherit.agents.eshop_service.strategy_engine import StrategyEngine
from inherit.llm.client import LLMClient
from inherit.llm.tool_client import ToolLLMClient
from inherit.prompt.prompt_manager import PromptManager
from inherit.utils.path import get_prj_root
from vlm.tool_vlm_client import ToolVLMClient


# ============================================================
# 命令行参数
# ============================================================

def parse_args() -> argparse.Namespace:
	"""解析命令行参数。"""
	parser: argparse.ArgumentParser = argparse.ArgumentParser(
		description="电商客服 GUI 自动回复 — VLM Function Calling 驱动键鼠操作",
		formatter_class=argparse.RawDescriptionHelpFormatter,
		epilog="""
示例:
    python main.py                    默认运行（最多 50 步）
    python main.py --max-steps 20     限制 20 步
    python main.py --quiet            安静模式
		""",
	)
	parser.add_argument(
		"--max-steps", type=int, default=50, metavar="N",
		help="最大 ReAct 循环步数（默认 50）",
	)
	parser.add_argument(
		"--quiet", action="store_true",
		help="安静模式，减少日志输出",
	)
	return parser.parse_args()


# ============================================================
# 主入口
# ============================================================

def main() -> None:
	"""程序入口。"""
	args: argparse.Namespace = parse_args()

	# ── 加载配置 ──────────────────────────────────────────
	cfg: Config = Config.from_yaml()

	# ── 构造 LLM 客户端 ───────────────────────────────────
	prj_root: Path = get_prj_root()

	llm: LLMClient = LLMClient(
		api_key=cfg.llm.api_key_env,
		base_url=cfg.llm.base_url,
		model=cfg.llm.model,
		temperature=cfg.generation.temperature,
		top_p=cfg.generation.top_p,
		max_tokens=cfg.generation.max_tokens,
	)

	tool_llm: ToolLLMClient = ToolLLMClient(
		api_key=cfg.llm.api_key_env,
		base_url=cfg.llm.base_url,
		model=cfg.llm.model,
		temperature=cfg.generation.temperature,
		top_p=cfg.generation.top_p,
		max_tokens=cfg.generation.max_tokens,
	)

	vlm: ToolVLMClient = ToolVLMClient(
		api_key=cfg.vlm.api_key_env,
		base_url=cfg.vlm.base_url,
		model=cfg.vlm.model,
		provider=cfg.vlm.provider,
	)

	print(f"🔌 LLM: {cfg.llm.provider}/{cfg.llm.model} @ {cfg.llm.base_url}")
	print(f"🔌 VLM: {cfg.vlm.provider}/{cfg.vlm.model} @ {cfg.vlm.base_url}")

	# ── Prompt 管理器 ─────────────────────────────────────
	pm: PromptManager = PromptManager(prj_root / "prompts")

	# ── 回复流水线组件 ────────────────────────────────────
	category_mgr: MessageCategoryManager = MessageCategoryManager(
		prj_root / "data" / "eshop_service" / "message_category"
	)
	classifier: MessageClassifier = MessageClassifier(llm=llm, pm=pm, category_mgr=category_mgr)
	strategy_engine: StrategyEngine = StrategyEngine(category_mgr=category_mgr, llm=llm, pm=pm)
	reply_generator: ReplyGenerator = ReplyGenerator(llm=tool_llm, pm=pm)

	# ── 构造编排器 ────────────────────────────────────────
	agent: GUIReplyAgent = GUIReplyAgent(
		vlm=vlm,
		pm=pm,
		classifier=classifier,
		strategy_engine=strategy_engine,
		reply_generator=reply_generator,
		max_steps=args.max_steps,
		verbose=not args.quiet,
	)

	# ── 启动循环 ──────────────────────────────────────────
	print()
	agent.run()
	print(f"\n{'=' * 60}")
	print("执行完成")
	print(f"{'=' * 60}")

	print("\n✅ 完成")


if __name__ == "__main__":
	main()
