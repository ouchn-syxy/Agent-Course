"""TripPlanningAgent — 行程规划领域智能体。

封装 PlanningAgent 的完整构建逻辑（工具注册、三大模块、领域上下文），
通过注入 LLM 客户端和提示词管理器保持与调用方的解耦。

用法：
    from agents.trip_planning.trip_planning_agent import TripPlanningAgent
    agent = TripPlanningAgent(llm, pm, max_inspect_rounds=3)
    plan = agent.run("目的地：成都 | 出发：北京 | ...")
"""

from __future__ import annotations

from agents.planning.planning_agent import PlanningAgent
from agents.trip_planning.domain_context import (
	TRIP_DECOMPOSE_CONTEXT,
	TRIP_PLAN_CONTEXT,
	TRIP_REFLECT_CONTEXT,
)
from agents.trip_planning.tools.attraction_search import AttractionSearch
from agents.trip_planning.tools.flight_search import FlightSearch
from agents.trip_planning.tools.hotel_search import HotelSearch
from agents.trip_planning.tools.weather_query import WeatherQuery
from inherit.llm.client import LLMClient
from inherit.llm.tool_registry import ToolRegistry
from inherit.prompt.prompt_manager import PromptManager
from inherit.tools.tavily_search import TavilySearch


class TripPlanningAgent:
	"""行程规划领域智能体。

	内置行程领域的工具注册和领域上下文注入，包装通用 PlanningAgent，
	对外提供一行式 run() 入口。
	"""


	def __init__(
			self,
			llm: LLMClient,
			pm: PromptManager,
			max_inspect_rounds: int = 5,
			verbose: bool = True,
			flight_search: FlightSearch | None = None,
			hotel_search: HotelSearch | None = None,
			attraction_search: AttractionSearch | None = None,
			weather_query: WeatherQuery | None = None,
			tavily_search: TavilySearch | None = None,
	) -> None:
		"""初始化行程规划智能体。

		:param llm:                LLM 客户端（由调用方注入）
		:param pm:                 提示词管理器（由调用方注入）
		:param max_inspect_rounds: 审查循环最大轮次
		:param verbose:            是否打印详细过程
		:param flight_search:      航班搜索工具实例，为 None 则不注册
		:param hotel_search:       酒店搜索工具实例，为 None 则不注册
		:param attraction_search:  景点搜索工具实例，为 None 则不注册
		:param weather_query:      天气查询工具实例，为 None 则不注册
		:param tavily_search:      网络搜索工具实例，为 None 则不注册
		"""
		# ── 工具注册中心（内部构建）──
		self._registry: ToolRegistry = ToolRegistry()
		for tool in (flight_search, hotel_search, attraction_search, weather_query, tavily_search):
			if tool is not None:
				self._registry.register(tool.to_tool_def())

		# ── 核心智能体 ──
		self._agent: PlanningAgent = PlanningAgent(
			llm=llm, pm=pm, registry=self._registry,
			max_inspect_rounds=max_inspect_rounds, verbose=verbose
		)


	def run(self, requirements: str) -> str:
		"""执行行程规划全流程，返回 Markdown 方案。

		:param requirements: 格式化后的用户出行需求
		:return:             Markdown 行程方案
		"""
		return self._agent.run(
			requirements,
			domain_context=TRIP_DECOMPOSE_CONTEXT,
			inspection_domain_context=TRIP_REFLECT_CONTEXT,
			plan_domain_context=TRIP_PLAN_CONTEXT,
		)


if __name__ == "__main__":
	from config import Config
	from inherit.utils.path import get_prj_root

	cfg: Config = Config.from_yaml()
	llm: LLMClient = LLMClient(
		api_key=cfg.llm.api_key_env,
		base_url=cfg.llm.base_url,
		model=cfg.llm.model,
		temperature=cfg.generation.temperature,
		top_p=cfg.generation.top_p,
		max_tokens=cfg.generation.max_tokens,
	)
	pm: PromptManager = PromptManager(get_prj_root() / "prompts")

	print("=" * 60)
	print("  TripPlanningAgent 演示 — 一站式行程规划")
	print("=" * 60)

	agent: TripPlanningAgent = TripPlanningAgent(
		llm, pm, max_inspect_rounds=3,
		flight_search=FlightSearch(),
		hotel_search=HotelSearch(),
		attraction_search=AttractionSearch(),
		weather_query=WeatherQuery(),
		tavily_search=TavilySearch(
			api_key=cfg.tavily.api_key,
			max_results=cfg.tavily.max_results,
			include_answer=cfg.tavily.include_answer,
		),
	)

	requirements: str = (
		"目的地：成都 | 出发：北京 | 日期：2026-07-20~07-23 | "
		"预算：3000-5000 | 偏好：自然风光、美食"
	)
	print(f"\n📋 需求: {requirements}")
	print(f"🔧 工具: {', '.join(t.name for t in agent._registry.list())}")
	print(f"🤖 模型: {llm.info()}\n")

	plan: str = agent.run(requirements)

	print("\n" + "=" * 60)
	print("  📝 最终方案")
	print("=" * 60)
	print(plan)
	print("\n" + "=" * 60)
	print("  演示完成")
	print("=" * 60)
