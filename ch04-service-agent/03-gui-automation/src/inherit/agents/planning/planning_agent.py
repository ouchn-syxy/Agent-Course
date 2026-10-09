"""PlanningAgent — 自主规划智能体：Decompose → Execute → Inspect → Report 循环。

核心流程：
  1. TaskDecomposer 初始分解 → SubTask 列表
  2. 执行所有初始子任务的工具调用
  3. InfoInspector 审查：信息是否充分？
     - 不充分 → 生成补充工具调用 → 执行 → 再次审查
     - 充分 → 退出循环
  4. PlanReporter 汇总所有信息 → 生成 Markdown 方案报告

这是本实验的核心价值所在 —— 不是静态拓扑执行，而是动态审查循环。
"""

from __future__ import annotations

import json

from inherit.agents.planning.models.types import (
	DecompositionResult,
	InspectionResult,
	SubTask,
	TaskExecutionRecord,
	TaskStatus,
	ToolCallPlan,
	ToolResult,
)
from inherit.agents.planning.info_inspector import InfoInspector
from inherit.agents.planning.plan_reporter import PlanReporter
from inherit.agents.planning.task_decomposer import TaskDecomposer
from inherit.llm.tool_registry import ToolRegistry


class PlanningAgent:
	"""自主规划智能体 — 驱动 Decompose→Execute→Inspect→Report 循环。"""


	def __init__(
			self,
			llm: LLMClient,
			pm: PromptManager,
			registry: ToolRegistry,
			max_inspect_rounds: int = 5,
			verbose: bool = True,
	) -> None:
		"""初始化智能体。

		:param registry:           工具注册中心（含全部已注册工具）
		:param max_inspect_rounds: 审查循环最大轮次
		:param verbose:            是否打印详细过程
		"""
		self._task_decomposer: TaskDecomposer = TaskDecomposer(llm, pm, registry)
		self._inspector: InfoInspector = InfoInspector(llm, pm, registry)
		self._plan_reporter: PlanReporter = PlanReporter(llm, pm)
		self._registry: ToolRegistry = registry
		self._max_inspect_rounds: int = max_inspect_rounds
		self._verbose: bool = verbose


	# ============================================================
	# 公共入口
	# ============================================================

	def run(
			self,
			requirements: str,
			domain_context: str = "",
			inspection_domain_context: str = "",
	        plan_domain_context: str = ""
	) -> str:
		"""执行完整的规划-执行-审查-生成流程。

		:param requirements:             格式化后的用户需求
		:param domain_context:            TaskDecomposer 使用的领域指导文本，由调用方注入
		:param inspection_domain_context: InfoInspector 使用的领域审核标准，由调用方注入
		:param plan_domain_context:       PlanReporter 使用的输出格式与指导文本，由调用方注入
		:return:                         Markdown 方案报告
		"""
		# ── Phase 1: Plan ──
		self._print_header("📋 Phase 1：任务分解")
		initial_plan: DecompositionResult = self._task_decomposer.plan(domain_context, requirements)
		self._print_plan(initial_plan)

		all_records: list[TaskExecutionRecord] = []

		# ── Phase 2: Execute initial tasks ──
		self._print_header("🔧 Phase 2：执行初始任务")
		for task in initial_plan.tasks:
			self._print_task_start(task)
			results: list[ToolResult] = self._execute_tool_calls(task.tool_calls)
			task.status = TaskStatus.COMPLETED
			all_records.append(TaskExecutionRecord(task=task, results=results))
			self._print_results(results)

		# ── Phase 3: Inspect-Execute loop ──
		self._print_header("🔄 Phase 3：审查与补充")
		for round_num in range(1, self._max_inspect_rounds + 1):
			inspection: InspectionResult = self._inspector.inspect(inspection_domain_context, requirements, all_records)
			if self._verbose:
				print(f"\n  🧠 审查 第 {round_num} 轮：")
				print(f"     充分性：{'✅ 信息充足' if inspection.is_sufficient else '❌ 有待补充'}")
				print(f"     推理：{inspection.reasoning}")

			if inspection.is_sufficient:
				self._print_info("信息收集完毕，进入方案生成阶段。")
				break

			if not inspection.additional_tool_calls:
				self._print_info("审查器未生成新任务，退出循环。")
				break

			# 输出发现的信息缺口
			if inspection.gaps and self._verbose:
				for gap in inspection.gaps:
					print(f"     🔍 缺口：{gap}")

			# 执行补充工具调用
			self._print_info(f"执行 {len(inspection.additional_tool_calls)} 个补充工具调用...")
			results: list[ToolResult] = self._execute_tool_calls(inspection.additional_tool_calls)

			# 创建虚拟任务记录
			virtual_task: SubTask = SubTask(
				id=f"inspect-round-{round_num}",
				description=f"第 {round_num} 轮审查补充",
				tool_calls=inspection.additional_tool_calls,
				status=TaskStatus.COMPLETED,
			)
			all_records.append(TaskExecutionRecord(task=virtual_task, results=results))
			self._print_results(results)
		else:
			self._print_info(
				f"⚠️ 已达最大审查轮次（{self._max_inspect_rounds}），"
				"强制进入方案生成阶段。"
			)

		# ── Phase 4: Report ──
		self._print_header("📝 Phase 4：生成方案报告")
		plan: str = self._plan_reporter.generate(plan_domain_context, requirements, all_records)

		return plan


	# ============================================================
	# 内部方法
	# ============================================================

	def _execute_tool_calls(self, calls: list[ToolCallPlan]) -> list[ToolResult]:
		"""直接执行一组工具调用（不通过 LLM）。

		:param calls: 待执行的 ToolCallPlan 列表
		:return:      执行结果列表
		"""
		results: list[ToolResult] = []
		for tc in calls:
			if self._verbose:
				args_display: str = json.dumps(tc.arguments, ensure_ascii=False)
				print(f"     🔧 {tc.tool_name}({args_display})")
			result_str: str = self._registry.execute(tc.tool_name, **tc.arguments)
			is_error: bool = result_str.startswith("错误") or result_str.startswith("参数错误")
			if self._verbose:
				display: str = result_str[:200] + ("..." if len(result_str) > 200 else "")
				print(f"     📦 {'❌' if is_error else '✅'} {display}")
			results.append(ToolResult(
				tool_name=tc.tool_name,
				arguments=tc.arguments,
				result=result_str,
				is_error=is_error,
			))
		return results


	# ============================================================
	# 打印辅助
	# ============================================================

	def _print_header(self, text: str) -> None:
		if self._verbose:
			print(f"\n{'=' * 55}")
			print(f"  {text}")
			print(f"{'=' * 55}")


	def _print_plan(self, plan: DecompositionResult) -> None:
		if not self._verbose:
			return
		print(f"  推理：{plan.reasoning}")
		print(f"  分解出 {len(plan.tasks)} 个子任务：")
		for t in plan.tasks:
			deps = f" (依赖: {', '.join(t.depends_on)})" if t.depends_on else ""
			print(f"    ◻ {t.id}: {t.description}{deps}")
			for tc in t.tool_calls:
				print(f"       → {tc.to_display()}")


	def _print_task_start(self, task: SubTask) -> None:
		if self._verbose:
			print(f"\n  ▶ 执行 {task.id}: {task.description}")


	def _print_results(self, results: list[ToolResult]) -> None:
		if not self._verbose:
			return
		ok = sum(1 for r in results if not r.is_error)
		err = len(results) - ok
		print(f"     📊 结果：{ok} 成功, {err} 失败")


	def _print_info(self, text: str) -> None:
		if self._verbose:
			print(f"\n  ℹ️  {text}")


if __name__ == "__main__":
	from config import Config

	from inherit.llm.client import LLMClient
	from inherit.prompt.prompt_manager import PromptManager
	from inherit.tools.tavily_search import TavilySearch
	from inherit.utils.path import get_prj_root

	# ── 内联领域上下文（演示用，不依赖 agents.trip_planning）──
	DECOMPOSE_CONTEXT: str = (
		"你是行程规划任务分解器。将用户需求拆解为可并行执行的搜索子任务，"
		"每个子任务包含具体的搜索关键词。"
	)
	INSPECT_CONTEXT: str = (
		"信息充分性审查标准：交通需有航班（含时间价格），"
		"住宿需 2-3 个酒店选项，景点需 3-5 个，天气需覆盖出行每天，美食需有当地推荐。"
		"如果某维度仅有 1 条或缺失，则为不充分。"
	)
	PLAN_CONTEXT: str = (
		"你是行程方案撰写助手。根据已收集的信息，生成一份结构清晰的 Markdown 行程方案。"
	)

	print("=" * 60)
	print("  PlanningAgent 演示 — 完整流水线")
	print("=" * 60)

	cfg: Config = Config.from_yaml()
	llm: LLMClient = LLMClient(
		api_key=cfg.llm.api_key_env,
		base_url=cfg.llm.base_url,
		model=cfg.llm.model,
		temperature=cfg.generation.temperature,
		top_p=cfg.generation.top_p,
		max_tokens=cfg.generation.max_tokens,
	)
	pm: PromptManager = PromptManager(templates_dir=get_prj_root() / "prompts")

	registry: ToolRegistry = ToolRegistry()
	registry.register(TavilySearch(api_key=cfg.tavily.api_key, include_answer=False).to_tool_def())

	agent: PlanningAgent = PlanningAgent(llm=llm, pm=pm, registry=registry, max_inspect_rounds=3)

	requirements: str = "目的地：成都 | 出发：北京 | 日期：2026-07-20~07-23 | 预算：3000-5000 | 偏好：自然风光、美食"
	print(f"\n📋 需求: {requirements}\n")

	plan: str = agent.run(
		requirements=requirements,
		domain_context=DECOMPOSE_CONTEXT,
		inspection_domain_context=INSPECT_CONTEXT,
		plan_domain_context=PLAN_CONTEXT,
	)

	print("\n" + "=" * 60)
	print("  📝 最终方案")
	print("=" * 60)
	print(plan)
	print("\n" + "=" * 60)
	print("  演示完成")
	print("=" * 60)
