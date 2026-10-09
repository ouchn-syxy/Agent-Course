"""
电商客服批量 GUI 自动回复 — CLI 入口。

组装批量编排器（BatchGUIReplyAgent），自动识别左侧栏用户选项卡，
循环遍历每个用户，调用 GUIReplyAgent 完成聊天回复。

用法:
    python main.py                          # 默认最多 20 个用户会话
    python main.py --max-users 30           # 自定义最多处理 30 个会话
    python main.py --max-steps 15           # 每用户最多 15 步 ReAct
    python main.py --wait 3.0               # 切换用户后等待 3 秒
    python main.py --quiet                  # 安静模式
"""

from __future__ import annotations

import argparse
from pathlib import Path

from agents.eshop_service.batch_gui_reply_agent import BatchGUIReplyAgent
from agents.eshop_service.reply_generator import ReplyGenerator
from config import Config
from inherit.agents.eshop_service.message_category_manager import MessageCategoryManager
from inherit.agents.eshop_service.message_classifier import MessageClassifier
from inherit.agents.eshop_service.strategy_engine import StrategyEngine
from inherit.llm.client import LLMClient
from inherit.llm.tool_client import ToolLLMClient
from inherit.prompt.prompt_manager import PromptManager
from inherit.utils.path import get_prj_root
from inherit.vlm.tool_vlm_client import ToolVLMClient


# ============================================================
# 命令行参数
# ============================================================

def parse_args() -> argparse.Namespace:
	"""解析命令行参数。"""
	parser: argparse.ArgumentParser = argparse.ArgumentParser(
		description="电商客服批量 GUI 自动回复 — 遍历用户选项卡自动处理消息",
		formatter_class=argparse.RawDescriptionHelpFormatter,
		epilog="""
示例:
    python main.py                        默认运行（最多 20 个用户会话）
    python main.py --max-users 30         最多 30 个会话
    python main.py --max-steps 15         每用户最多 15 步
    python main.py --wait 3.0             切换用户后等待 3 秒
    python main.py --quiet                安静模式
		""",
	)
	parser.add_argument(
		"--max-users", type=int, default=None, metavar="N",
		help="最多处理的用户会话数（默认批量 20；指定 --target-user 时默认 1）",
	)
	parser.add_argument(
		"--max-steps", type=int, default=20, metavar="N",
		help="每个用户的 GUIReplyAgent 最大 ReAct 步数（默认 20）",
	)
	parser.add_argument(
		"--wait", type=float, default=2.0, metavar="S",
		help="切换用户后等待页面加载的秒数（默认 2.0）",
	)
	parser.add_argument(
		"--target-user", type=str, default=None, metavar="NAME",
		help="只处理指定用户名，适合课堂演示，例如：--target-user 钱七",
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

	print(f"🔌 LLM:   {cfg.llm.provider}/{cfg.llm.model} @ {cfg.llm.base_url}")
	print(f"🔌 VLM:   {cfg.vlm.provider}/{cfg.vlm.model} @ {cfg.vlm.base_url}")
	max_users: int = args.max_users if args.max_users is not None else (1 if args.target_user else 20)
	print(
		f"🔧 每用户最大步数: {args.max_steps}  |  切换等待: {args.wait}s"
		f"  |  最多处理: {max_users} 个会话"
	)
	if args.target_user:
		print(f"🎯 指定用户: {args.target_user}")

	# ── Prompt 管理器 ─────────────────────────────────────
	pm: PromptManager = PromptManager(prj_root / "prompts")

	# ── 回复流水线组件 ────────────────────────────────────
	category_mgr: MessageCategoryManager = MessageCategoryManager(
		prj_root / "data" / "eshop_service" / "message_category"
	)
	classifier: MessageClassifier = MessageClassifier(llm=llm, pm=pm, category_mgr=category_mgr)
	strategy_engine: StrategyEngine = StrategyEngine(category_mgr=category_mgr, llm=llm, pm=pm)
	reply_generator: ReplyGenerator = ReplyGenerator(llm=tool_llm, pm=pm)

	# ── 构造批量编排器 ────────────────────────────────────
	batch: BatchGUIReplyAgent = BatchGUIReplyAgent(
		vlm=vlm,
		pm=pm,
		classifier=classifier,
		strategy_engine=strategy_engine,
		reply_generator=reply_generator,
		reply_max_steps=args.max_steps,
		wait_seconds=args.wait,
		verbose=not args.quiet,
	)

	# ── 启动批量循环 ──────────────────────────────────────
	print()
	batch.run(max_users=max_users, target_user=args.target_user)

	print("\n✅ 批量处理完成")


if __name__ == "__main__":
	main()
