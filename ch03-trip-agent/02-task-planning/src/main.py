"""
实验 7：任务分解与工具编排 — 主入口

通过 Decompose→Execute→Inspect→Report 循环，将用户需求分解为子任务，
调用工具收集信息，不断审查补充，最终生成完整的 Markdown 方案报告。

用法：
    python main.py                        # 交互式规划
    python main.py --max-inspect 3        # 限制审查轮次
    python main.py -o output/my_plan.md   # 指定输出文件
"""

from __future__ import annotations

import argparse
from datetime import datetime
from pathlib import Path

from agents.trip_planning.tools.attraction_search import AttractionSearch
from agents.trip_planning.tools.flight_search import FlightSearch
from agents.trip_planning.tools.hotel_search import HotelSearch
from agents.trip_planning.tools.weather_query import WeatherQuery
from agents.trip_planning.trip_planning_agent import TripPlanningAgent
from config import Config
from inherit.llm.client import LLMClient
from inherit.prompt.prompt_manager import PromptManager
from inherit.tools.tavily_search import TavilySearch
from inherit.utils.path import get_prj_root


# ============================================================
# 命令行参数
# ============================================================

def parse_args() -> argparse.Namespace:
	"""解析命令行参数。"""
	parser: argparse.ArgumentParser = argparse.ArgumentParser(
		description="行程任务分解与工具编排智能体",
		formatter_class=argparse.RawDescriptionHelpFormatter,
		epilog="""
示例：
	python main.py                        # 交互式规划
	python main.py --max-inspect 3        # 限制最多 3 轮审查
	python main.py -o output/my_plan.md   # 输出到指定文件
		""",
	)
	parser.add_argument(
		"--max-inspect",
		type=int,
		default=5,
		dest="max_inspect",
		help="最大审查轮次（默认: 5）",
	)
	parser.add_argument(
		"-o", "--output",
		type=str,
		default="",
		dest="output_file",
		help="行程输出文件路径（默认: 自动生成时间戳文件名）",
	)
	return parser.parse_args()


# ============================================================
# 路径工具
# ============================================================

def _get_prompts_dir() -> Path:
	"""获取提示词模板目录。"""
	return get_prj_root() / "prompts"


def _get_output_dir() -> Path:
	"""获取/创建输出目录。"""
	p: Path = get_prj_root() / "output"
	p.mkdir(parents=True, exist_ok=True)
	return p


# ============================================================
# 输出
# ============================================================

def output_plan(plan_text: str, output_file: str = "") -> None:
	"""输出最终行程方案到终端和文件。

	:param plan_text:   行程方案 Markdown 文本
	:param output_file: 输出文件路径（为空则自动生成时间戳文件名）
	"""
	print("\n" + "=" * 55)
	print(plan_text)

	if output_file:
		path: Path = Path(output_file)
		if not path.is_absolute():
			path = _get_output_dir() / path
	else:
		timestamp: str = datetime.now().strftime("%Y%m%d_%H%M%S")
		path = _get_output_dir() / f"trip_plan_{timestamp}.md"

	path.parent.mkdir(parents=True, exist_ok=True)
	path.write_text(plan_text, encoding="utf-8")
	print(f"\n📁 行程已保存至：{path}")


# ============================================================
# 交互式规划
# ============================================================

def plan_loop(agent: TripPlanningAgent, output_file: str = "") -> None:
	"""交互式行程规划循环。

	每轮输入一个出行需求，agent 自动完成
	Decompose→Execute→Inspect→Report 全流程。
	"""

	while True:
		print()
		try:
			user_input: str = input("✈️  需求：").strip()
		except (EOFError, KeyboardInterrupt):
			print("\n👋 再见！")
			break

		if user_input.lower() in ("/quit", "/exit", "quit", "exit"):
			print("👋 再见！")
			break

		if not user_input:
			continue

		# 格式化需求
		requirements: str = user_input

		# 执行流水线
		plan_text: str = agent.run(requirements)

		# 输出
		output_plan(plan_text, output_file)
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

	# 初始化行程规划智能体
	agent: TripPlanningAgent = TripPlanningAgent(
		llm=llm, pm=pm, max_inspect_rounds=args.max_inspect, verbose=True,
		flight_search=FlightSearch(),
		hotel_search=HotelSearch(),
		attraction_search=AttractionSearch(),
		weather_query=WeatherQuery(),
		tavily_search=TavilySearch(
			api_key=cfg.tavily.api_key,
			max_results=cfg.tavily.max_results,
			include_answer=cfg.tavily.include_answer
		),
	)

	# 启动交互
	print("=" * 50)
	print("  🧳 行程规划智能体 — 任务分解与工具编排")
	print(f"  模型: {llm.model}")
	print("=" * 50)
	print("  输入你的出行需求（格式：目的地：成都 | 出发：北京 | ...）")
	print("  输入 /quit 退出")
	print("=" * 50)
	plan_loop(agent, args.output_file)


if __name__ == "__main__":
	main()
