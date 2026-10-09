"""考试大纲加载器 — 从 JSON 文件读取考试知识点和配置，构建 StudyState 初始骨架。"""

import json
from pathlib import Path

from agents.review.models.study_state import (
	ExamSyllabus,
	KnowledgePoint,
	SyllabusKnowledgePoint,
	StudyState,
)


def load_exam_syllabus(file_path: Path) -> ExamSyllabus:
	"""加载考试大纲 JSON 文件，返回结构化 ExamSyllabus 对象。

	Args:
		file_path: 大纲 JSON 文件路径

	Returns:
		解析后的 ExamSyllabus 结构化对象
	"""
	with open(file_path, encoding="utf-8") as f:
		data: dict = json.load(f)
	return ExamSyllabus.model_validate(data)


def build_knowledge_points(raw_kps: list[SyllabusKnowledgePoint]) -> list[KnowledgePoint]:
	"""从大纲原始数据构建初始 KnowledgePoint 列表。

	所有知识点初始 mastering=0.5, confidence=0.3。
	诊断阶段会通过会话更新这些值。

	Args:
		raw_kps: 大纲中的知识点列表

	Returns:
		KnowledgePoint 列表
	"""
	kps: list[KnowledgePoint] = []
	for raw in raw_kps:
		kp: KnowledgePoint = KnowledgePoint(
			id=raw.id,
			name=raw.name,
			category=raw.category,
			description=raw.description,
			key_concepts=raw.key_concepts,
			importance=raw.importance,
		)
		kps.append(kp)
	return kps


def build_initial_study_state(syllabus: ExamSyllabus, session_id: str | None = None) -> StudyState:
	"""从大纲构建 StudyState 初始骨架（不含 daily_plans，由 PlanGenerator 生成）。

	Args:
		syllabus: load_exam_syllabus() 返回的 ExamSyllabus
		session_id: 可选的会话 ID，若为 None 则自动生成

	Returns:
		初始 StudyState（knowledge_points 已填充，daily_plans 为空，current_day=0）
	"""
	knowledge_points: list[KnowledgePoint] = build_knowledge_points(syllabus.knowledge_points)

	state: StudyState = StudyState(
		exam_name=syllabus.exam_name,
		total_days=syllabus.total_days,
		knowledge_points=knowledge_points,
		daily_plans=[],
		current_day=0,
	)

	if session_id:
		state.session_id = session_id

	return state


if __name__ == "__main__":
	project_root: Path = Path(__file__).resolve().parents[4]
	syllabus_path: Path = project_root / "data" / "data_structure_exam.json"

	# Demo load_exam_syllabus
	print("=" * 60)
	print("Demo: load_exam_syllabus")
	print("=" * 60)
	syllabus: ExamSyllabus = load_exam_syllabus(syllabus_path)
	print(f"考试名称: {syllabus.exam_name}")
	print(f"总复习天数: {syllabus.total_days}")
	print(f"知识点数量: {len(syllabus.knowledge_points)}")
	for kp in syllabus.knowledge_points:
		print(f"  - [{kp.id}] {kp.name} (重要性: {kp.importance})")

	# Demo build_knowledge_points
	print()
	print("=" * 60)
	print("Demo: build_knowledge_points")
	print("=" * 60)
	raw_kps: list[SyllabusKnowledgePoint] = syllabus.knowledge_points
	kps: list[KnowledgePoint] = build_knowledge_points(raw_kps)
	for kp in kps:
		print(f"  - [{kp.id}] {kp.name}")
		print(f"    掌握度: {kp.mastery}, 置信度: {kp.confidence}")
		print(f"    核心概念: {kp.key_concepts}")

	# Demo build_initial_study_state
	print()
	print("=" * 60)
	print("Demo: build_initial_study_state")
	print("=" * 60)
	state: StudyState = build_initial_study_state(syllabus, session_id="demo_session")
	print(f"会话 ID: {state.session_id}")
	print(f"考试名称: {state.exam_name}")
	print(f"当前天数: {state.current_day}")
	print(f"知识点数量: {len(state.knowledge_points)}")
	print(f"每日计划数量: {len(state.daily_plans)}")
	print(f"创建时间: {state.created_at}")
