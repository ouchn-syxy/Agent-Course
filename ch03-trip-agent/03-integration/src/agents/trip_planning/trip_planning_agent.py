"""TripPlanningAgent — 行程规划智能体统一入口。

整合需求收集 + 任务分解 + 工具编排 + 结果验证 + 对话记忆 + 偏好提取，
构建完整的 Collect → Plan → Execute → Verify 闭环。

核心流程：
  0. ReAct 需求收集 — 通过多轮对话逐步补全模糊出行需求
  1. 注入用户偏好 + 历史对话上下文
  2. PlanningAgent 编排 — Decompose → Execute → Reflect → Generate
  3. TripPlanVerifier 验证 — 不通过则反馈至 PlanningAgent 重生成（最多 N 轮）
  4. 记录本轮对话至 ConversationMemory
  5. 从对话中提取偏好标签并持久化至 PreferenceMemory
"""

from __future__ import annotations

from openai.types.chat import ChatCompletionMessageParam

from agents.preference_extractor.preference_extractor import PreferenceExtractor
from agents.trip_planning.trip_plan_verifier import TripPlanVerifier, VerifyResult
from inherit.agents.planning.planning_agent import PlanningAgent
from inherit.agents.trip_planning.domain_context import TRIP_DECOMPOSE_CONTEXT, TRIP_PLAN_CONTEXT, TRIP_REFLECT_CONTEXT
from inherit.agents.trip_planning.requirement_collector import TripRequirementCollector
from inherit.llm.client import LLMClient
from inherit.llm.tool_registry import ToolRegistry
from inherit.memory.conversation_memory import ConversationMemory
from inherit.prompt.prompt_manager import PromptManager
from memory.preference_memory import PreferenceMemory, PreferenceEntry

from inherit.agents.trip_planning.tools.attraction_search import AttractionSearch
from inherit.agents.trip_planning.tools.flight_search import FlightSearch
from inherit.agents.trip_planning.tools.hotel_search import HotelSearch
from inherit.agents.trip_planning.tools.weather_query import WeatherQuery
from inherit.tools.tavily_search import TavilySearch


class TripPlanningAgent:
	"""行程规划智能体 — Collect → Plan → Execute → Verify 闭环。

	内部自动加载 domain_context（拆分规则、反思检查点、输出格式规范），
	无需外部注入。

	用法：
		agent = TripPlanningAgent(
			llm=llm,
			pm=pm,
			conversation_memory=conv_mem,
			preference_memory=pref_mem,
			max_verify_rounds=3,
			flight_search=FlightSearch(),
			hotel_search=HotelSearch(),
			attraction_search=AttractionSearch(),
			weather_query=WeatherQuery(),
			tavily_search=TavilySearch(...),
		)
		plan = agent.run(requirements)
	"""


	def __init__(
			self,
			llm: LLMClient,
			pm: PromptManager,
			conversation_memory: ConversationMemory,
			preference_memory: PreferenceMemory,
			max_verify_rounds: int = 3,
			max_inspect_rounds: int = 5,
			verbose: bool = True,
			*,
			flight_search: FlightSearch | None = None,
			hotel_search: HotelSearch | None = None,
			attraction_search: AttractionSearch | None = None,
			weather_query: WeatherQuery | None = None,
			tavily_search: TavilySearch | None = None,
	) -> None:
		"""初始化 TripPlanningAgent。

		:param llm:                 LLM 客户端
		:param pm:                  提示词模板管理器
		:param conversation_memory: 多轮对话记忆
		:param preference_memory:   用户偏好持久化存储
		:param max_verify_rounds:   验证 → 重生成最大轮次（默认 3）
		:param max_inspect_rounds:  审查循环最大轮次（默认 5）
		:param verbose:             是否打印中间步骤
		:param flight_search:       航班搜索工具实例，为 None 则不注册
		:param hotel_search:        酒店搜索工具实例，为 None 则不注册
		:param attraction_search:   景点搜索工具实例，为 None 则不注册
		:param weather_query:       天气查询工具实例，为 None 则不注册
		:param tavily_search:       网络搜索工具实例，为 None 则不注册
		"""
		self._pm: PromptManager = pm

		# ── 工具注册中心（内部构建）──
		registry: ToolRegistry = ToolRegistry()
		for tool in (flight_search, hotel_search, attraction_search, weather_query, tavily_search):
			if tool is not None:
				registry.register(tool.to_tool_def())

		# -- 核心管线 --
		self._requirement_collector: TripRequirementCollector = TripRequirementCollector(llm=llm, prompt_manager=pm)
		self._planner: PlanningAgent = PlanningAgent(
			llm=llm, pm=pm, registry=registry, max_inspect_rounds=max_inspect_rounds, verbose=True
		)
		self._verifier: TripPlanVerifier = TripPlanVerifier(llm=llm, pm=pm)

		# -- 记忆系统 --
		self._conv_mem: ConversationMemory = conversation_memory
		self._pref_mgr: PreferenceMemory = preference_memory
		self._pref_extractor: PreferenceExtractor = PreferenceExtractor(llm=llm, pm=pm)

		# -- 流程控制 --
		self._max_verify_rounds: int = max_verify_rounds
		self._verbose: bool = verbose


	def _log(self, msg: str) -> None:
		"""verbose=True 时打印消息。"""
		if self._verbose:
			print(msg)


	def run(self, requirements: str) -> str:
		"""执行 Collect → Plan → Execute → Verify 全流程。

		Step 0  ReAct 需求收集 — 多轮对话补全模糊需求
		Step 1  注入上下文 — 加载用户偏好 + 历史对话
		Step 2  PlanningAgent 编排 — Decompose → Execute → Reflect → Generate
		Step 3  Verify 验证循环 — 不通过则反馈重生成（最多 max_verify_rounds 轮）
		Step 4  记录对话 — 写入 ConversationMemory
		Step 5  提取偏好 — 自动提炼偏好标签并持久化

		Args:
			requirements: 用户出行需求（模糊或结构化均可）

		Returns:
			Markdown 格式行程方案
		"""
		# ── Step 0: ReAct 需求收集 ──
		self._log("🧠 Step 0：需求智能收集")
		requirements = self._requirement_collector.run(requirements)
		self._log("\t📋 收集完成")
		self._log(f"\t{requirements}")

		# ── Step 1: 注入偏好 + 历史对话 ──
		preferences: list[PreferenceEntry] = self._pref_mgr.get_preferences()
		history_msgs: list[ChatCompletionMessageParam] = self._conv_mem.get_messages()
		if preferences or history_msgs:
			self._log("📋 Step 1：注入上下文")
		if preferences:
			self._log(f"\t📌 已加载用户偏好（{len(preferences)} 条）")
		if history_msgs:
			self._log(f"\t📌 已加载历史对话（{self._conv_mem.turn_count} 轮）")

		requirements = self._pm.render(
			"agents/trip_planning/requirements_context.j2",
			requirements=requirements,
			preferences=preferences,
			history_messages=history_msgs,
		)

		# ── Step 2: PlanningAgent 编排（Decompose→Execute→Reflect→Generate）──
		self._log("⚙️ Step 2：方案生成")
		plan_text: str = self._planner.run(
			requirements=requirements,
			domain_context=TRIP_DECOMPOSE_CONTEXT,
			inspection_domain_context=TRIP_REFLECT_CONTEXT,
			plan_domain_context=TRIP_PLAN_CONTEXT,
		)

		# ── Step 3: Verify & Regenerate Loop ──
		self._log("✅ Step 3：方案验证")
		for round_num in range(1, self._max_verify_rounds + 1):
			if round_num >= self._max_verify_rounds:
				self._log(f"\t⚠️  已达最大验证轮次（{self._max_verify_rounds}），直接返回当前方案。")
				break

			self._log(f"\t✅ 第 {round_num}/{self._max_verify_rounds} 轮")
			result: VerifyResult = self._verifier.verify(requirements, plan_text)

			if result.is_valid:
				self._log("\t\t✅ 通过")
				break

			self._log(f"\t\t❌ 不通过 | {result.reasoning}")
			for i in result.issues or []:
				severity: str = i.severity
				emoji: str = {"critical": "🔴", "major": "🟡", "minor": "🟢"}.get(severity, "⚪")
				self._log(f"\t\t\t{emoji} [{i.dimension}] {i.description}")

			if not result.has_critical_or_major():
				self._log("\t\tℹ️  仅存在 minor 级别问题，接受当前方案。")
				break

			self._log("\t\t🔄 反馈至 PlanningAgent，重新生成方案...")
			regenerate_context: str = self._pm.render(
				"agents/trip_planning/regenerate_context.j2",
				plan_domain_context=TRIP_PLAN_CONTEXT,
				result=result,
				plan_text=plan_text,
			)
			plan_text: str = self._planner.run(
				requirements=requirements,
				domain_context=TRIP_DECOMPOSE_CONTEXT,
				inspection_domain_context=TRIP_REFLECT_CONTEXT,
				plan_domain_context=regenerate_context,
			)

		# ── Step 4: 记录本轮对话 ──
		self._log("💾 Step 4：记录对话")
		self._conv_mem.record_turn(requirements, plan_text)

		# ── Step 5: 提取偏好 ──
		extracted_preferences: list[PreferenceEntry] = self._pref_extractor.extract(requirements)
		for entry in extracted_preferences:
			self._pref_mgr.record_preference(entry.tag, entry.value)
		if extracted_preferences:
			self._log("🏷️ Step 5：提取偏好")
			tags: str = ", ".join(f"{e.tag}={e.value}" for e in extracted_preferences)
			self._log(f"\t📌 已提取用户偏好：{tags}")

		return plan_text


# ============================================================
# Demo（直接 python trip_planning_agent.py 即可运行）
# ============================================================

if __name__ == "__main__":
	from pathlib import Path

	from config import Config
	from inherit.agents.trip_planning.tools.attraction_search import AttractionSearch
	from inherit.agents.trip_planning.tools.flight_search import FlightSearch
	from inherit.agents.trip_planning.tools.hotel_search import HotelSearch
	from inherit.agents.trip_planning.tools.weather_query import WeatherQuery
	from inherit.llm.client import LLMClient
	from inherit.tools.tavily_search import TavilySearch
	from inherit.utils.path import get_prj_root

	cfg: Config = Config.from_yaml()

	DEMO_REQUIREMENT: str = "我想去北京玩两天，预算2000元，喜欢历史文化景点"

	print("─" * 55)
	print("  🧳 TripPlanningAgent Demo")
	print("─" * 55)
	print(f"📝 输入：{DEMO_REQUIREMENT}")
	print("─" * 55)

	llm: LLMClient = LLMClient(
		api_key=cfg.llm.api_key_env,
		base_url=cfg.llm.base_url,
		model=cfg.llm.model,
		temperature=cfg.generation.temperature,
		top_p=cfg.generation.top_p,
		max_tokens=cfg.generation.max_tokens,
	)

	pm: PromptManager = PromptManager(get_prj_root() / "prompts")

	tavily_search: TavilySearch | None = None
	if cfg.tavily.api_key:
		tavily_search = TavilySearch(api_key=cfg.tavily.api_key, include_answer=False)

	mem_dir: Path = get_prj_root() / "data" / "memories"
	mem_dir.mkdir(parents=True, exist_ok=True)

	conversation_memory: ConversationMemory = ConversationMemory(
		storage_dir=mem_dir, session_id="trip_agent",
		llm_client=llm, prompt_manager=pm,
	)
	preference_memory: PreferenceMemory = PreferenceMemory(storage_dir=mem_dir, session_id="trip_agent")

	agent: TripPlanningAgent = TripPlanningAgent(
		llm=llm,
		pm=pm,
		conversation_memory=conversation_memory,
		preference_memory=preference_memory,
		max_verify_rounds=3,
		verbose=True,
		flight_search=FlightSearch(),
		hotel_search=HotelSearch(),
		attraction_search=AttractionSearch(),
		weather_query=WeatherQuery(),
		tavily_search=tavily_search,
	)

	plan: str = agent.run(DEMO_REQUIREMENT)

	print(f"\n{'─' * 55}")
	print("  📝 最终行程方案")
	print("─" * 55)
	print(plan)
