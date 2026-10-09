"""
TripPlanningAgent 启动器 — Collect→Plan→Execute→Verify 闭环。

通过多轮对话收集需求，注入用户偏好与历史上下文，
驱动 Decompose→Execute→Reflect→Verify 循环，
最终生成完整行程方案。

用法：
    python main.py                          # 交互式规划
    python main.py --max-verify 5           # 限制验证-重生成轮次
    python main.py --max-inspect 3          # 限制审查轮次
    python main.py -o output/my_plan.md     # 指定输出文件
"""

from __future__ import annotations

import argparse
from datetime import datetime
from pathlib import Path

from agents.trip_planning.trip_planning_agent import TripPlanningAgent
from config import Config
from inherit.agents.trip_planning.tools.attraction_search import AttractionSearch
from inherit.agents.trip_planning.tools.flight_search import FlightSearch
from inherit.agents.trip_planning.tools.hotel_search import HotelSearch
from inherit.agents.trip_planning.tools.weather_query import WeatherQuery
from inherit.llm.client import LLMClient
from inherit.memory.conversation_memory import ConversationMemory
from inherit.prompt.prompt_manager import PromptManager
from inherit.tools.tavily_search import TavilySearch
from inherit.utils.path import get_prj_root
from memory.preference_memory import PreferenceMemory


# ============================================================
# 命令行参数
# ============================================================

def parse_args() -> argparse.Namespace:
	"""解析命令行参数。"""
	parser: argparse.ArgumentParser = argparse.ArgumentParser(
		description="行程规划智能体 — Collect→Plan→Execute→Verify 闭环",
		formatter_class=argparse.RawDescriptionHelpFormatter,
		epilog="""
示例：
	python main.py                        # 交互式规划
	python main.py --max-verify 5         # 限制验证最多 5 轮
	python main.py --max-inspect 3        # 限制审查最多 3 轮
	python main.py -o output/my_plan.md   # 输出到指定文件
		""",
	)
	parser.add_argument(
		"--max-verify",
		type=int,
		default=3,
		dest="max_verify",
		help="最大验证-重生成轮次（默认: 3）",
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


def _get_memories_dir() -> Path:
	"""获取/创建记忆存储目录。"""
	p: Path = get_prj_root() / "data" / "memories"
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

	每轮输入出行需求，agent 自动完成
	Collect→Plan→Execute→Verify 全流程。
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

		# 执行完整流水线
		plan_text: str = agent.run(user_input)

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
	pm: PromptManager = PromptManager(_get_prompts_dir())

	llm: LLMClient = LLMClient(
		api_key=cfg.llm.api_key_env,
		base_url=cfg.llm.base_url,
		model=cfg.llm.model,
		temperature=cfg.generation.temperature,
		top_p=cfg.generation.top_p,
		max_tokens=cfg.generation.max_tokens,
	)

	tavily_search: TavilySearch | None = None
	if cfg.tavily.api_key:
		tavily_search = TavilySearch(api_key=cfg.tavily.api_key, include_answer=False)

	conversation_memory: ConversationMemory = ConversationMemory(
		storage_dir=_get_memories_dir(),
		session_id="trip_agent",
		llm_client=llm,
		prompt_manager=pm,
	)
	preference_memory: PreferenceMemory = PreferenceMemory(
		storage_dir=_get_memories_dir(),
		session_id="trip_agent",
	)

	agent: TripPlanningAgent = TripPlanningAgent(
		llm=llm,
		pm=pm,
		conversation_memory=conversation_memory,
		preference_memory=preference_memory,
		max_verify_rounds=args.max_verify,
		max_inspect_rounds=args.max_inspect,
		verbose=True,
		flight_search=FlightSearch(),
		hotel_search=HotelSearch(),
		attraction_search=AttractionSearch(),
		weather_query=WeatherQuery(),
		tavily_search=tavily_search,
	)

	tools: list[str] = ["flight_search", "hotel_search", "attraction_search", "weather_query"]
	if cfg.tavily.api_key:
		tools.append("web_search")

	print("=" * 50)
	print("  🧳 行程规划智能体 — Collect→Plan→Execute→Verify 闭环")
	print(f"  模型: {cfg.llm.model}")
	print(f"  工具: {', '.join(tools)}")
	print("=" * 50)
	print("  输入你的出行需求")
	print("  输入 /quit 退出")
	print("=" * 50)

	plan_loop(agent, args.output_file)


if __name__ == "__main__":
	main()
