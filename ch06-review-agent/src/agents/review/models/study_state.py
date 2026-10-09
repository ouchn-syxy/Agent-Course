"""复习助手智能体 — 数据模型定义。

定义 StudyState、KnowledgePoint、DailyPlan 等全部核心 Pydantic 模型。
模型间引用关系：
    StudyState
    ├── list[KnowledgePoint]
    │   └── list[MasteryRecord]
    └── list[DailyPlan]
        ├── list[DailyTask]
        │   └── TaskResult
        │       └── GradingResult
        └── ReflectionResult
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from uuid import uuid4

from pydantic import BaseModel, Field, computed_field


# ============================================================
# 基础枚举
# ============================================================

class TaskType(str, Enum):
	"""每日任务类型。"""
	REVIEW = "review"  # 复习回顾
	PRACTICE = "practice"  # 练习题
	QUIZ = "quiz"  # 小测验


class TaskStatus(str, Enum):
	"""任务执行状态。"""
	PENDING = "pending"
	IN_PROGRESS = "in_progress"
	COMPLETED = "completed"
	SKIPPED = "skipped"


class DayStatus(str, Enum):
	"""单日学习状态。"""
	PENDING = "pending"
	IN_PROGRESS = "in_progress"
	COMPLETED = "completed"


class EvidenceType(str, Enum):
	"""掌握度证据类型，影响置信度计算权重。"""
	QUIZ = "quiz"
	SELF_ASSESSMENT = "self_assessment"
	COMPLETION = "completion"


# ============================================================
# 掌握度相关
# ============================================================

class MasteryRecord(BaseModel):
	"""掌握度变更记录 — 每次更新时追加一条。"""
	day: int = Field(description="第几天（0 为初始诊断）")
	old_mastery: float = Field(description="变更前掌握度 0.0~1.0")
	new_mastery: float = Field(description="变更后掌握度 0.0~1.0")
	old_confidence: float = Field(description="变更前置信度 0.0~1.0")
	new_confidence: float = Field(description="变更后置信度 0.0~1.0")
	evidence_type: EvidenceType = Field(description="证据类型")
	note: str = Field(default="", description="补充说明")
	timestamp: str = Field(default_factory=lambda: datetime.now().isoformat(sep=" ", timespec="seconds"))


class KnowledgePoint(BaseModel):
	"""单个知识点 — 含掌握度、置信度、重要性及历史记录。"""
	id: str = Field(description="唯一标识，如 linear_list")
	name: str = Field(description="中文名称，如 线性表")
	category: str = Field(description="分类，如 线性结构 / 非线性结构 / 算法")
	description: str = Field(description="知识点概述")
	key_concepts: list[str] = Field(default_factory=list, description="核心子概念")
	mastery: float = Field(default=0.5, ge=0.0, le=1.0, description="掌握度 0.0~1.0")
	confidence: float = Field(default=0.3, ge=0.1, le=1.0, description="置信度 0.1~1.0，越高越确定")
	importance: float = Field(default=0.5, ge=0.0, le=1.0, description="考试重要性 0.0~1.0")
	history: list[MasteryRecord] = Field(default_factory=list, description="掌握度变化历史")
	last_practiced_day: int = Field(default=-1, description="最近一次练习所在天数，-1 表示尚未练习")


	@computed_field
	@property
	def priority(self) -> float:
		"""学习优先级 = importance × (1 - mastery) / max(confidence, 0.1)。

		值越大越需要优先学习：重要且不熟练且不确定的知识点排前面。
		"""
		return self.importance * (1.0 - self.mastery) / max(self.confidence, 0.1)


# ============================================================
# 批改相关
# ============================================================

class DimensionScores(BaseModel):
	"""三维评分 — 正确性、完整性、清晰度各维度得分。"""
	correctness: float = Field(ge=0.0, description="正确性得分")
	completeness: float = Field(ge=0.0, description="完整性得分")
	clarity: float = Field(ge=0.0, description="清晰度得分")


class GradingResult(BaseModel):
	"""LLM 批改结果 — 对用户答案的结构化评分。"""
	score: float = Field(description="总分 0.0~10.0")
	dimension_scores: DimensionScores = Field(description="各维度得分")
	strengths: list[str] = Field(default_factory=list, description="优点")
	weaknesses: list[str] = Field(default_factory=list, description="不足")
	model_answer: str = Field(default="", description="参考答案")
	feedback: str = Field(default="", description="评语与改进建议")


class TaskResult(BaseModel):
	"""单个任务的完成结果 — 汇总用户自评、测验得分、批改结果等。"""
	self_assessment: float = Field(default=0.5, ge=0.0, le=1.0, description="用户自评 0.0~1.0")
	quiz_score: float | None = Field(default=None, ge=0.0, le=1.0, description="测验得分（归一化到 0.0~1.0）")
	completion_level: float = Field(default=0.0, ge=0.0, le=1.0, description="完成度 0.0~1.0")
	user_answer: str | None = Field(default=None, description="用户作答原文")
	grading: GradingResult | None = Field(default=None, description="LLM 批改结果")
	notes: str = Field(default="", description="用户备注")


# ============================================================
# 任务与计划
# ============================================================

class DailyTask(BaseModel):
	"""单个每日任务。"""
	id: str = Field(description="任务 ID")
	description: str = Field(description="任务描述")
	knowledge_point_id: str = Field(description="关联知识点 ID")
	task_type: TaskType = Field(description="任务类型")
	estimated_minutes: int = Field(default=30, ge=1, description="预估耗时（分钟）")
	status: TaskStatus = Field(default=TaskStatus.PENDING, description="执行状态")
	actual_minutes: int | None = Field(default=None, description="实际耗时（分钟）")
	result: TaskResult | None = Field(default=None, description="完成结果")
	question: str | None = Field(default=None, description="LLM 生成的题目")
	reference_answer: str | None = Field(default=None, description="参考答案")
	grading_criteria: str | None = Field(default=None, description="评分标准")


class ReflectionResult(BaseModel):
	"""每日反思 — 分析当日学习结果。"""
	overall_effectiveness: float = Field(description="整体有效性 0.0~1.0")
	task_completion_rate: float = Field(description="任务完成率 0.0~1.0")
	insights: str = Field(default="", description="主要洞见")
	issues: list[str] = Field(default_factory=list, description="发现的问题")
	suggestions: list[str] = Field(default_factory=list, description="改进建议")
	needs_replan: bool = Field(default=False, description="是否需要调整后续计划")


class ReplanChanges(BaseModel):
	"""计划调整 — 仅修改未执行天数。"""
	day: int = Field(description="触发调整的当前天数")
	changes_description: str = Field(description="调整说明")
	modified_day_plans: list[DailyPlan] = Field(default_factory=list, description="替换后的后续计划")
	reasoning: str = Field(default="", description="调整推理链")


class DailyPlan(BaseModel):
	"""单日学习计划。"""
	day: int = Field(description="第几天（1-based）")
	available_minutes: int = Field(description="可用时间（分钟）")
	tasks: list[DailyTask] = Field(default_factory=list, description="当日任务列表")
	status: DayStatus = Field(default=DayStatus.PENDING, description="当日状态")
	reflection: ReflectionResult | None = Field(default=None, description="当日反思结果")


# ============================================================
# 顶层状态
# ============================================================

class StudyState(BaseModel):
	"""复习智能体的完整状态 — 序列化到 JSON 文件。"""
	exam_name: str = Field(description="考试名称")
	total_days: int = Field(description="总复习天数")
	knowledge_points: list[KnowledgePoint] = Field(default_factory=list, description="知识点列表")
	daily_plans: list[DailyPlan] = Field(default_factory=list, description="每日计划列表")
	current_day: int = Field(default=0, description="当前天数（0 为初始化完成待开始）")
	created_at: str = Field(
		default_factory=lambda: datetime.now().isoformat(sep=" ", timespec="seconds"),
	    description="创建时间"
	)
	updated_at: str = Field(
		default_factory=lambda: datetime.now().isoformat(sep=" ", timespec="seconds"),
	    description="最后更新时间"
	)
	session_id: str = Field(default_factory=lambda: uuid4().hex[:12], description="会话 ID")


# ============================================================
# 大纲加载相关
# ============================================================

class SyllabusKnowledgePoint(BaseModel):
	"""大纲中的原始知识点条目 — 从 JSON 反序列化，尚未附加掌握度/置信度。"""
	id: str = Field(description="唯一标识，如 linear_list")
	name: str = Field(description="中文名称，如 线性表")
	category: str = Field(default="", description="分类，如 线性结构 / 非线性结构 / 算法")
	importance: float = Field(default=0.5, ge=0.0, le=1.0, description="考试重要性 0.0~1.0")
	description: str = Field(default="", description="知识点概述")
	key_concepts: list[str] = Field(default_factory=list, description="核心子概念")


class ExamSyllabus(BaseModel):
	"""考试大纲 — load_exam_syllabus() 返回的结构化数据。"""
	exam_name: str = Field(description="考试名称")
	total_days: int = Field(description="总复习天数")
	daily_minutes: int = Field(default=90, description="每天可用学习时间（分钟）")
	knowledge_points: list[SyllabusKnowledgePoint] = Field(default_factory=list, description="大纲知识点列表")
