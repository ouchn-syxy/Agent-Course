"""复习助手智能体 — ReAct 循环 + JSON 状态机。

负责：
- --init：初始化学习会话（诊断 + 计划生成）
- daily：执行当日任务（ReAct：出题 → 作答 → 批改 → 反思 → 重规划）
- --status：查看当前状态
- --session：列出会话
- --reset：重置状态

编排流程（每天）：
  1. 遍历当日任务：出题 → 展示 → 收集答案 → 批改 → 更新掌握度
  2. 应用遗忘因子
  3. 日终反思
  4. 条件触发重规划
  5. 持久化状态
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from agents.review.daily_reviewer import DailyReviewer
from agents.review.data.syllabus_loader import build_initial_study_state, load_exam_syllabus
from agents.review.exam_grader import ExamGrader
from agents.review.knowledge_assessor import KnowledgeAssessor
from agents.review.mastery_calculator import apply_forgetting_factor, update_mastery
from agents.review.models.study_state import (
	DailyPlan,
	DailyTask,
	DayStatus,
	DimensionScores,
	ExamSyllabus,
	GradingResult,
	KnowledgePoint,
	ReflectionResult,
	ReplanChanges,
	StudyState,
	TaskResult,
	TaskStatus,
)
from agents.review.plan_generator import PlanGenerator
from agents.review.question_generator import GeneratedQuestion, QuestionGenerator
from agents.review.replanner import Replanner
from agents.review.tools.lookup_knowledge_point import LookupKnowledgePoint
from agents.review.tools.search_fact_check import SearchFactCheck
from agents.review.tools.search_reference_questions import SearchReferenceQuestions
from inherit.llm.client import LLMClient
from inherit.llm.tool_client import ToolLLMClient
from inherit.prompt.prompt_manager import PromptManager
from inherit.utils.path import get_prj_root


@dataclass
class SessionSummary:
	"""会话摘要信息，用于列表展示。"""

	session_id: str
	exam_name: str
	current_day: int
	total_days: int
	updated_at: str
	file: str


class ReviewAgent:
	"""复习助手智能体。

	用法：
		config = Config.from_yaml()
		agent = ReviewAgent(llm, tool_llm, pm,
			search_reference_questions=SearchReferenceQuestions(...),
			lookup_knowledge_point=LookupKnowledgePoint(),
			search_fact_check=SearchFactCheck(...),
		)
		state = agent.init_session()          # --init
		state = agent.run_daily(state)         # daily
	"""


	def __init__(
		self,
		llm_client: LLMClient,
		tool_llm_client: ToolLLMClient,
		prompt_manager: PromptManager,
		*,
		search_reference_questions: SearchReferenceQuestions | None = None,
		lookup_knowledge_point: LookupKnowledgePoint | None = None,
		search_fact_check: SearchFactCheck | None = None,
	) -> None:
		"""初始化复习助手智能体及其全部子 Agent。

		Args:
			llm_client: LLM 客户端，用于无需工具调用的子 Agent（评估、规划、反思、重规划）。
			tool_llm_client: 支持 Function Calling 的 LLM 客户端，用于出题器和批改器。
			prompt_manager: Prompt 管理器，用于加载和渲染 Jinja2 模板。
			search_reference_questions: 搜索参考题目工具实例，为 None 则不注册。
			lookup_knowledge_point: Wikipedia 知识点查询工具实例，为 None 则不注册。
			search_fact_check: 事实核查工具实例，为 None 则不注册。
		"""
		self._llm: LLMClient = llm_client
		self._pm: PromptManager = prompt_manager

		self._knowledge_assessor: KnowledgeAssessor = KnowledgeAssessor(llm_client, prompt_manager)
		self._plan_generator: PlanGenerator = PlanGenerator(llm_client, prompt_manager)
		self._question_generator: QuestionGenerator = QuestionGenerator(
			tool_llm_client, prompt_manager,
			search_reference_questions=search_reference_questions,
			lookup_knowledge_point=lookup_knowledge_point,
		)
		self._exam_grader: ExamGrader = ExamGrader(
			tool_llm_client, prompt_manager,
			search_fact_check=search_fact_check,
		)
		self._reflection_agent: DailyReviewer = DailyReviewer(llm_client, prompt_manager)
		self._replan_agent: Replanner = Replanner(llm_client, prompt_manager)


	# ================================================================
	# 会话初始化
	# ================================================================

	def init_session(self, syllabus_path: Path) -> StudyState:
		"""初始化学习会话：加载大纲 → 生成计划 → 持久化。

		流程：
		1. 从 syllabus_path 加载考试大纲 JSON，构建初始 StudyState。
		2. 调用 PlanGenerator 根据知识点列表生成完整的 daily_plans。
		3. 将状态持久化到 data/sessions/ 目录。

		Args:
			syllabus_path: 大纲 JSON 文件路径，格式见 Syllabus 模型定义。

		Returns:
			完成初始化的 StudyState（current_day=0，daily_plans 已生成完毕）。
		"""
		# 1. 加载大纲
		syllabus: ExamSyllabus = load_exam_syllabus(syllabus_path)
		state: StudyState = build_initial_study_state(syllabus)

		print("=" * 60)
		print(f"📚 {state.exam_name} — 复习助手")
		print(f"   总复习天数：{state.total_days}")
		print(f"   知识点数量：{len(state.knowledge_points)}")
		print("=" * 60)

		# 2. 诊断
		print("\n🧠 开始知识点诊断...")
		print("   我会通过几个问题了解你对各知识点的掌握情况。\n")

		self._knowledge_assessor.run(state.knowledge_points, exam_name=state.exam_name)

		# 3. 生成计划

		state.daily_plans = self._plan_generator.generate(
			knowledge_points=state.knowledge_points,
			exam_name=state.exam_name,
			total_days=state.total_days,
			daily_minutes=syllabus.daily_minutes,
		)

		# 4. 持久化
		state.updated_at = datetime.now().isoformat(sep=" ", timespec="seconds")
		self._save_state(state)

		print(f"\n✅ 初始化完成！会话 ID：{state.session_id}")
		print(f"   状态已保存到：{self._state_path(state.session_id)}")
		print(f"   明天开始第 1 天学习，运行 `python main.py` 开始。")

		return state


	# ================================================================
	# 每日学习执行
	# ================================================================

	def run_daily(self, state: StudyState) -> StudyState:
		"""执行当天的完整学习流程。

		每日流程（ReAct 循环）：
		1. 推进 current_day（从 0 → 1，或 +1）。
		2. 逐任务执行：出题 → 收集答案 → 批改 → 记录 TaskResult。
		3. 批量更新知识点掌握度（batch_update_mastery）。
		4. 应用遗忘因子（apply_forgetting_factor）。
		5. 日终反思（DailyReviewer.reflect）。
		6. 条件触发重规划（若 reflection.needs_replan）。
		7. 持久化状态到文件。

		Args:
			state: 当前学习状态，原地修改。

		Returns:
			原地修改后的 StudyState（同时已持久化）。
		"""
		# 确定当天
		if state.current_day <= 0:
			state.current_day = 1
		else:
			state.current_day += 1

		if state.current_day > state.total_days:
			print("🎉 所有学习计划已完成！恭喜！")
			return state

		current_plan: DailyPlan = self._get_daily_plan_or_raise(state, state.current_day)

		print(f"\n{'=' * 60}")
		print(f"📅 第 {state.current_day} 天 / 共 {state.total_days} 天")
		print(f"   可用时间：{current_plan.available_minutes} 分钟")
		print(f"   任务数量：{len(current_plan.tasks)}")
		print(f"{'=' * 60}")

		if not current_plan.tasks:
			print("   ⚠️  今日无任务，进入下一天。")
			state.daily_plans[state.current_day - 1].status = DayStatus.COMPLETED
			self._save_state(state)
			return state

		# 标记当天开始
		current_plan.status = DayStatus.IN_PROGRESS

		# --- 逐任务执行（ReAct 循环） ---
		# 同一知识点一天可能有多个任务；逐项保留证据，不能以后一个覆盖前一个。
		task_results: list[tuple[str, TaskResult, str, int]] = []

		for i, task in enumerate(current_plan.tasks, 1):
			print(f"\n--- 任务 {i}/{len(current_plan.tasks)} ---")
			print(f"📝 {task.description}")
			print(
				f"   类型：{task.task_type}  |  知识点：{task.knowledge_point_id}  |  预估：{task.estimated_minutes} 分钟")

			result: TaskResult = self._execute_task(task, state)
			task.result = result
			task.status = TaskStatus.COMPLETED
			task.actual_minutes = result.actual_minutes if hasattr(result, 'actual_minutes') else task.estimated_minutes

			task_results.append((
				task.knowledge_point_id, result, task.task_type.value, task.estimated_minutes,
			))

		# --- 批量更新掌握度 ---
		kp_map: dict[str, KnowledgePoint] = {kp.id: kp for kp in state.knowledge_points}
		for kp_id, result, task_type, estimated_minutes in task_results:
			kp = kp_map.get(kp_id)
			if kp is not None:
				update_mastery(kp, result, state.current_day, task_type, estimated_minutes)

		# --- 应用遗忘因子 ---
		apply_forgetting_factor(state.knowledge_points, state.current_day)

		# --- 日终反思 ---
		self._print_separator("反思")
		reflection: ReflectionResult = self._reflection_agent.reflect(state)
		current_plan.reflection = reflection

		print(f"   整体有效性：{reflection.overall_effectiveness:.0%}")
		print(f"   任务完成率：{reflection.task_completion_rate:.0%}")
		print(f"   💡 {reflection.insights}")
		if reflection.issues:
			print(f"   ⚠️  问题：")
			for issue in reflection.issues:
				print(f"       - {issue}")
		if reflection.suggestions:
			print(f"   💬 建议：")
			for s in reflection.suggestions:
				print(f"       - {s}")

		# --- 条件重规划 ---
		if reflection.needs_replan:
			self._print_separator("计划调整")
			changes: ReplanChanges = self._replan_agent.replan(state, reflection)
			print(f"   🔄 {changes.changes_description}")
			print(f"   推理：{changes.reasoning}")
			print(f"   修改了 {len(changes.modified_day_plans)} 天的计划")
		else:
			print("\n   ✅ 计划无需调整，按原计划继续。")

		# 标记当天完成
		current_plan.status = DayStatus.COMPLETED
		state.updated_at = datetime.now().isoformat(sep=" ", timespec="seconds")

		# 持久化
		self._save_state(state)

		print(f"\n✅ 第 {state.current_day} 天学习完成！状态已保存。")
		if state.current_day < state.total_days:
			print(f"   明天继续，运行 `python main.py` 开始第 {state.current_day + 1} 天。")

		return state


	# ================================================================
	# 单任务执行
	# ================================================================

	def _execute_task(self, task: DailyTask, state: StudyState) -> TaskResult:
		"""执行单个学习任务：出题 → 展示 → 收集用户答案 → 批改。

		根据 task.task_type 分两种处理路径：
		- REVIEW 类型：展示复习提示，收集用户自评分数。
		- PRACTICE/QUIZ 类型：调用 QuestionGenerator 出题，从 stdin 收集
		  多行答案（以 ``__END__`` 结束），调用 ExamGrader 批改，展示结果。

		Args:
			task: 当前要执行的任务对象（原地修改其 question/result/status）。
			state: 完整学习状态，用于查找关联知识点。

		Returns:
			TaskResult，包含自评分数、测验分数、用户答案、批改结果等。
		"""

		kp: KnowledgePoint | None = self._get_knowledge_point_or_none(state, task.knowledge_point_id)

		# 对于 review 类型：简单自评
		if task.task_type.value == "review":
			print("\n   📖 复习任务 — 请回顾以下内容：")
			print(f"   {task.description}")
			self_assessment: float = self._ask_rating("   请自评掌握程度（0.0 完全不会 ~ 1.0 完全掌握）")
			return TaskResult(
				self_assessment=self_assessment,
				completion_level=1.0,
			)

		# 对于 practice / quiz 类型：出题 → 作答 → 批改
		# 1) 出题
		if kp is None:
			print(f"   ⚠️  找不到知识点 {task.knowledge_point_id}，使用默认处理")
			return TaskResult(self_assessment=0.5, completion_level=1.0)

		print("   ⏳ 正在出题...")
		question_info: GeneratedQuestion = self._question_generator.generate(
			kp, task_type=task.task_type
		)

		# 保存题目
		task.question = question_info.question
		task.reference_answer = question_info.reference_answer
		task.grading_criteria = question_info.grading_criteria.model_dump_json(indent=2)

		# 2) 展示题目 & 收集答案
		print(f"\n   📝 题目：")
		print(f"   {task.question}")
		print()

		# 收集多行答案（以 __END__ 结束）
		print("   ✏️  请输入你的答案（输入 __END__ 结束）：")
		lines: list[str] = []
		while True:
			line: str = input()
			if line.strip() == "__END__":
				break
			lines.append(line)
		user_answer: str = "\n".join(lines)

		if not user_answer.strip():
			print("   ⚠️  未输入答案，视为跳过。")
			return TaskResult(
				self_assessment=0.0,
				completion_level=0.0,
				user_answer="",
			)

		# 3) 批改
		print("\n   ⏳ 正在批改...")
		grading: GradingResult = self._exam_grader.grade(question_info, user_answer)

		# 展示批改结果
		quiz_score_normalized: float = grading.score / 10.0
		print(f"\n   📊 批改结果：")
		print(f"   得分：{grading.score:.1f}/10")
		ds: DimensionScores = grading.dimension_scores
		print(f"     - correctness: {ds.correctness:.1f}")
		print(f"     - completeness: {ds.completeness:.1f}")
		print(f"     - clarity: {ds.clarity:.1f}")
		if grading.strengths:
			print(f"   ✅ 优点：{'；'.join(grading.strengths)}")
		if grading.weaknesses:
			print(f"   ⚠️  不足：{'；'.join(grading.weaknesses)}")
		print(f"   💬 {grading.feedback}")
		if grading.model_answer:
			print(f"\n   📖 参考答案：\n   {grading.model_answer}")

		self_assessment: float = self._ask_rating("   请自评掌握程度（0.0 ~ 1.0）")

		return TaskResult(
			self_assessment=self_assessment,
			quiz_score=quiz_score_normalized,
			completion_level=1.0,
			user_answer=user_answer,
			grading=grading,
		)


	# ================================================================
	# 状态展示
	# ================================================================

	def show_status(self, state: StudyState) -> None:
		"""在终端中展示当前学习状态的摘要信息。

		输出内容包括：考试名称、会话 ID、当前进度、各知识点掌握度柱状图、
		计划完成天数和今日任务进度。

		Args:
			state: 当前学习状态。
		"""
		print(f"\n{'=' * 60}")
		print(f"📚 {state.exam_name}  —  会话 {state.session_id}")
		print(f"   进度：第 {state.current_day}/{state.total_days} 天")
		print(f"{'=' * 60}")

		print(f"\n📊 知识点掌握情况：")
		for kp in sorted(state.knowledge_points, key=lambda k: k.mastery):
			bar: str = "█" * int(kp.mastery * 20) + "░" * (20 - int(kp.mastery * 20))
			print(f"   {kp.name:8s} [{bar}] {kp.mastery:.0%}  (置信度 {kp.confidence:.0%})")

		completed: int = sum(1 for p in state.daily_plans if p.status == DayStatus.COMPLETED)
		print(f"\n📅 计划进度：已完成 {completed}/{state.total_days} 天")
		if state.current_day > 0:
			current_plan: DailyPlan | None = self._get_daily_plan_or_none(state, state.current_day)
			if current_plan:
				done: int = sum(1 for t in current_plan.tasks if t.status == TaskStatus.COMPLETED)
				print(f"   今日任务：{done}/{len(current_plan.tasks)} 已完成")


	# ================================================================
	# 状态持久化
	# ================================================================

	def save_state(self, state: StudyState) -> Path:
		"""将当前学习状态持久化到 JSON 文件。

		Args:
			state: 待保存的学习状态。

		Returns:
			写入的文件路径。
		"""
		return self._save_state(state)


	def load_state(self, session_id: str) -> StudyState:
		"""从 JSON 文件加载指定会话的学习状态。

		Args:
			session_id: 会话唯一标识。

		Returns:
			反序列化后的 StudyState。

		Raises:
			FileNotFoundError: 会话状态文件不存在。
		"""
		path: Path = self._state_path(session_id)
		if not path.exists():
			raise FileNotFoundError(f"会话状态文件不存在：{path}")
		return StudyState.model_validate_json(path.read_text(encoding="utf-8"))


	def list_sessions(self) -> list[SessionSummary]:
		"""列出所有已持久化的会话摘要信息。

		按文件修改时间倒序排列。

		Returns:
			SessionSummary 列表，可能为空。
		"""
		output_dir: Path = get_prj_root() / "data" / "sessions"
		if not output_dir.exists():
			return []
		sessions: list[SessionSummary] = []
		for f in sorted(output_dir.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True):
			try:
				with open(f, encoding="utf-8") as fp:
					data: Any = json.load(fp)
				sessions.append(SessionSummary(
					session_id=data.get("session_id", f.stem),
					exam_name=data.get("exam_name", ""),
					current_day=data.get("current_day", 0),
					total_days=data.get("total_days", 0),
					updated_at=data.get("updated_at", ""),
					file=str(f),
				))
			except (json.JSONDecodeError, KeyError):
				continue
		return sessions


	def reset_session(self, session_id: str) -> None:
		"""删除指定会话的持久化文件。

		Args:
			session_id: 待删除的会话唯一标识。
		"""
		path: Path = self._state_path(session_id)
		if path.exists():
			path.unlink()
			print(f"已删除会话 {session_id}")
		else:
			print(f"会话 {session_id} 不存在")


	# ================================================================
	# 内部辅助
	# ================================================================

	def _save_state(self, state: StudyState) -> Path:
		"""将 StudyState 序列化为 JSON 并写入 data/sessions/ 目录。

		写入前自动更新 updated_at 时间戳。

		Args:
			state: 待持久化的学习状态。

		Returns:
			写入的文件路径。
		"""
		state.updated_at = datetime.now().isoformat(sep=" ", timespec="seconds")
		path: Path = self._state_path(state.session_id)
		path.parent.mkdir(parents=True, exist_ok=True)
		with open(path, "w", encoding="utf-8") as f:
			f.write(state.model_dump_json(indent=4, ensure_ascii=False))
		return path


	def _state_path(self, session_id: str) -> Path:
		"""根据 session_id 构造状态文件的存储路径。

		Args:
			session_id: 会话唯一标识。

		Returns:
			data/sessions/{session_id}.json 的绝对路径。
		"""
		return get_prj_root() / "data" / "sessions" / f"{session_id}.json"


	@staticmethod
	def _get_daily_plan_or_raise(state: StudyState, day: int) -> DailyPlan:
		"""获取指定天的计划，不存在则抛出 ValueError。

		Args:
			state: 当前学习状态。
			day: 目标天数（1-based）。

		Returns:
			对应的 DailyPlan。

		Raises:
			ValueError: 指定天数的计划不存在。
		"""
		for plan in state.daily_plans:
			if plan.day == day:
				return plan
		raise ValueError(f"找不到第 {day} 天的计划")


	@staticmethod
	def _get_daily_plan_or_none(state: StudyState, day: int) -> DailyPlan | None:
		"""获取指定天的计划，不存在则返回 None。

		Args:
			state: 当前学习状态。
			day: 目标天数（1-based）。

		Returns:
			对应的 DailyPlan，或 None。
		"""
		for plan in state.daily_plans:
			if plan.day == day:
				return plan
		return None


	@staticmethod
	def _get_knowledge_point_or_none(state: StudyState, kp_id: str) -> KnowledgePoint | None:
		"""在 StudyState 中按 ID 查找知识点。

		Args:
			state: 当前学习状态。
			kp_id: 知识点唯一标识。

		Returns:
			匹配的 KnowledgePoint，找不到则返回 None。
		"""
		for kp in state.knowledge_points:
			if kp.id == kp_id:
				return kp
		return None


	@staticmethod
	def _ask_rating(prompt: str) -> float:
		"""从 stdin 收集一个 0.0~1.0 范围内的浮点数评分。

		若用户直接回车则返回默认值 0.5；若输入无效则循环提示。

		Args:
			prompt: 显示给用户的提示文本。

		Returns:
			用户输入的有效浮点数（0.0~1.0）。
		"""
		while True:
			try:
				val: str = input(f"{prompt}: ").strip()
				if val == "":
					return 0.5
				v: float = float(val)
				if 0.0 <= v <= 1.0:
					return v
				print("   ⚠️  请输入 0.0 ~ 1.0 之间的数值")
			except ValueError:
				print("   ⚠️  请输入有效的数值")


	@staticmethod
	def _print_separator(title: str) -> None:
		"""在终端中打印带标题的分隔线，用于视觉区分各流程阶段。

		Args:
			title: 分隔线标题（如 "反思"、"计划调整"）。
		"""
		print(f"\n{'─' * 40}")
		print(f"🔍 {title}")
		print(f"{'─' * 40}")


if __name__ == "__main__":
	import os

	from config import Config

	config: Config = Config.from_yaml()

	api_key: str = os.getenv(config.llm.api_key_env, config.llm.api_key_env)
	llm: LLMClient = LLMClient(
		api_key=api_key,
		base_url=config.llm.base_url,
		model=config.llm.model,
		temperature=config.generation.temperature,
		top_p=config.generation.top_p,
		max_tokens=config.generation.max_tokens,
	)
	pm: PromptManager = PromptManager(get_prj_root() / "prompts")

	agent: ReviewAgent = ReviewAgent(llm, pm)

	# 列出已有会话
	sessions: list[SessionSummary] = agent.list_sessions()
	if sessions:
		print("已有会话：")
		for s in sessions:
			print(f"  {s.session_id}: {s.exam_name} (第{s.current_day}/{s.total_days}天)")
	else:
		print("暂无会话，运行 init_session() 初始化")
