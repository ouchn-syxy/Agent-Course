"""掌握度计算器 — 纯程序实现，禁止 LLM 参与。

根据学习证据（测验得分、自评、完成度）通过指数移动平均更新知识点的
掌握度和置信度。全部计算逻辑来自教育理论，高效且可调试。

核心公式：
  evidence_score = weighted_evidence(quiz_score, self_assessment, completion)
  alpha = learning_rate(task_type, estimated_minutes)
  new_mastery = clamp(old_mastery + alpha * (evidence_score - old_mastery), 0, 1)

  beta = 0.3  # 置信度变化速度
  new_confidence = clamp(old_confidence + beta * (evidence_quality - old_confidence), 0.1, 1)
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
	from agents.review.models.study_state import KnowledgePoint, TaskResult

# ============================================================
# 证据权重配置
# ============================================================

# 不同证据类型对掌握度的可信度权重
EVIDENCE_QUALITY_WEIGHTS: dict[str, float] = {
	"quiz": 0.8,
	"self_assessment": 0.3,
	"completion": 0.2,
}

# 不同任务类型对掌握度的学习率（alpha 系数）
TASK_TYPE_LEARNING_RATES: dict[str, float] = {
	"quiz": 0.25,
	"practice": 0.20,
	"review": 0.10,
}

# 遗忘因子：连续 days 天未练习后的 mastery 衰减
FORGETTING_FACTOR_DAILY: float = 0.98  # 每天衰减 2%

# 置信度变化速度
CONFIDENCE_BETA: float = 0.3


def clamp(value: float, lo: float, hi: float) -> float:
	return max(lo, min(hi, value))


# ============================================================
# 单个知识点更新
# ============================================================

def update_mastery(
		kp: KnowledgePoint,
		result: TaskResult,
		current_day: int,
		task_type: str = "practice",
		estimated_minutes: int = 30,
) -> KnowledgePoint:
	"""根据单个任务的完成结果更新知识点的掌握度和置信度。

	Args:
		kp: 待更新的知识点（原地修改后返回）
		result: 任务完成结果
		current_day: 当前天数
		task_type: 任务类型（quiz/practice/review）
		estimated_minutes: 预估学习时间

	Returns:
		更新后的知识点（同一对象）
	"""
	evidence_score = _compute_evidence_score(result)
	evidence_type = _determine_evidence_type(result)
	evidence_quality = EVIDENCE_QUALITY_WEIGHTS.get(evidence_type, 0.3)

	# 掌握度更新（指数移动平均）
	alpha = TASK_TYPE_LEARNING_RATES.get(task_type, 0.15)
	# 学习时间影响学习率：时间越多，微调学习率
	time_factor = clamp(estimated_minutes / 30.0, 0.5, 2.0)
	alpha *= time_factor

	old_mastery = kp.mastery
	new_mastery = clamp(old_mastery + alpha * (evidence_score - old_mastery), 0.0, 1.0)

	# 置信度更新
	old_confidence = kp.confidence
	new_confidence = clamp(
		old_confidence + CONFIDENCE_BETA * (evidence_quality - old_confidence),
		0.1, 1.0,
	)

	# 写入
	kp.mastery = round(new_mastery, 4)
	kp.confidence = round(new_confidence, 4)
	kp.last_practiced_day = current_day

	# 追加历史记录
	from agents.review.models.study_state import EvidenceType, MasteryRecord

	kp.history.append(
		MasteryRecord(
			day=current_day,
			old_mastery=old_mastery,
			new_mastery=kp.mastery,
			old_confidence=old_confidence,
			new_confidence=kp.confidence,
			evidence_type=EvidenceType(evidence_type),
		)
	)

	return kp


def _compute_evidence_score(result: TaskResult) -> float:
	"""融合多来源证据计算综合掌握度评分。

	优先级：quiz_score > 自评 × 完成度 > 仅完成度
	"""
	if result.quiz_score is not None:
		return result.quiz_score

	# 自评与完成度的加权平均
	return 0.6 * result.self_assessment + 0.4 * result.completion_level


def _determine_evidence_type(result: TaskResult) -> str:
	"""确定证据类型。"""
	if result.quiz_score is not None:
		return "quiz"
	if result.user_answer:
		return "self_assessment"
	return "completion"


# ============================================================
# 批量更新与遗忘
# ============================================================

def batch_update_mastery(
		kps: list[KnowledgePoint],
		results_by_kp: dict[str, TaskResult],
		current_day: int,
		task_info_by_kp: dict[str, tuple[str, int]] | None = None,
) -> list[KnowledgePoint]:
	"""批量更新多个知识点的掌握度。

	Args:
		kps: 知识点列表
		results_by_kp: {knowledge_point_id: TaskResult} 映射
		current_day: 当前天数
		task_info_by_kp: {knowledge_point_id: (task_type, estimated_minutes)}

	Returns:
		更新后的知识点列表
	"""
	if task_info_by_kp is None:
		task_info_by_kp = {}

	for kp in kps:
		if kp.id in results_by_kp:
			task_type, estimated_minutes = task_info_by_kp.get(
				kp.id, ("practice", 30)
			)
			update_mastery(
				kp,
				results_by_kp[kp.id],
				current_day,
				task_type=task_type,
				estimated_minutes=estimated_minutes,
			)
	return kps


def apply_forgetting_factor(
		kps: list[KnowledgePoint],
		current_day: int,
		skip_days_before_decay: int = 3,
) -> list[KnowledgePoint]:
	"""对长时间未练习的知识点应用遗忘衰减。

	仅当知识点 last_practiced_day >= 0（已练习过）且距离当前超过
	skip_days_before_decay 天时，才施加衰减。

	Args:
		kps: 知识点列表
		current_day: 当前天数
		skip_days_before_decay: 超过此天数才衰减

	Returns:
		更新后的知识点列表
	"""
	for kp in kps:
		if kp.last_practiced_day < 0:
			continue

		gap = current_day - kp.last_practiced_day
		if gap > skip_days_before_decay:
			extra = gap - skip_days_before_decay
			decay = FORGETTING_FACTOR_DAILY ** extra
			kp.mastery = round(clamp(kp.mastery * decay, 0.0, 1.0), 4)

	return kps
