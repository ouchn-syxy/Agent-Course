"""
实验 6：ReAct 模式与需求理解智能体 — 主入口

通过纯 ReAct（Thought → Action → Observation）循环，
从用户一句模糊出行需求出发，逐步收集完整信息。

用法：
    python main.py                        # 交互式需求收集
    python main.py --max-iterations 10    # 自定义最大追问轮数
"""

from __future__ import annotations

import argparse
from pathlib import Path

from agents.trip_planning.requirement_collector import TripRequirementCollector
from config import Config
from inherit.llm.client import LLMClient
from inherit.prompt.prompt_manager import PromptManager
from inherit.utils.path import get_prj_root


# ============================================================
# 命令行参数
# ============================================================

def parse_args() -> argparse.Namespace:
	"""解析命令行参数。"""
	parser: argparse.ArgumentParser = argparse.ArgumentParser(
		description="ReAct 需求收集智能体",
		formatter_class=argparse.RawDescriptionHelpFormatter,
		epilog="""
示例：
	python main.py                     # 默认 15 轮上限
	python main.py --max-iterations 10 # 更短的收集流程
		""",
	)
	parser.add_argument(
		"--max-iterations",
		type=int,
		default=15,
		help="最大追问轮数（默认: 15）",
	)
	return parser.parse_args()


# ============================================================
# 路径工具
# ============================================================

def _get_prompts_dir() -> Path:
	"""获取提示词模板目录。"""
	return get_prj_root() / "prompts"


# ============================================================
# 交互式收集
# ============================================================

def collect_loop(collector: TripRequirementCollector) -> None:
	"""交互式需求收集循环。

	每轮输入一个模糊出行需求，TripRequirementCollector 自动完成
	Thought → Action → Observation 收集流程。
	"""

	while True:
		print()
		try:
			user_input: str = input("✈️  你的需求：").strip()
		except (EOFError, KeyboardInterrupt):
			print("\n👋 再见！")
			break

		if user_input.lower() in ("/quit", "/exit", "quit", "exit"):
			print("👋 再见！")
			break

		if not user_input:
			continue

		# 执行 ReAct 循环
		result: str = collector.run(user_input)
		print(f"\n{result}")
		print()

		# 询问是否继续
		again: str = input("🔁 再来一次？（y/n）：").strip().lower()
		if again not in ("y", "yes", "是", ""):
			print("👋 再见！")
			break


# ============================================================
# 主入口
# ============================================================


def main() -> None:
	"""程序入口。"""
	args: argparse.Namespace = parse_args()
	cfg: Config = Config.from_yaml()

	# 初始化 LLM
	llm: LLMClient = LLMClient(
		api_key=cfg.llm.api_key_env,
		base_url=cfg.llm.base_url,
		model=cfg.llm.model,
		temperature=cfg.generation.temperature,
		top_p=cfg.generation.top_p,
		max_tokens=cfg.generation.max_tokens,
	)

	# 初始化提示词管理器
	pm: PromptManager = PromptManager(_get_prompts_dir())

	# 初始化出行需求收集器
	collector: TripRequirementCollector = TripRequirementCollector(llm, pm, max_iterations=args.max_iterations)

	# 启动交互
	print("=" * 50)
	print("  🧳 行程规划智能体 — 需求收集")
	print(f"  模型: {llm.model}")
	print("=" * 50)
	print("  输入你的出行需求（越模糊越能体现 ReAct 模式！）")
	print("  示例：\"我想出去玩几天\"")
	print("  输入 /quit 退出")
	print("=" * 50)
	collect_loop(collector)


if __name__ == "__main__":
	main()
