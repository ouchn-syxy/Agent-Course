"""协作上下文管理 — 在 Agent 间共享数据和历史记录。

WorkflowContext 聚合了写作流程中所有阶段的输入输出，
确保每个 Agent 都能访问所需的前序结果。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from agents.write_studio.workflow.state import FactCheckVerdict, ReviewDecision, WorkflowState


@dataclass
class StageRecord:
	"""单个阶段的执行记录 — 记录状态、输入、输出和时间戳。"""
	
	stage: WorkflowState
	started_at: datetime
	completed_at: datetime | None = None
	input_data: dict[str, Any] = field(default_factory=dict)
	output_data: dict[str, Any] = field(default_factory=dict)
	error: str | None = None
	
	@property
	def duration(self) -> float | None:
		"""计算执行耗时（秒）。"""
		if self.completed_at is None:
			return None
		return (self.completed_at - self.started_at).total_seconds()
	
	@property
	def is_success(self) -> bool:
		"""判断是否执行成功（无错误 + 有输出）。"""
		return self.error is None and bool(self.output_data)


@dataclass
class RetryRecord:
	"""退回重做记录 — 记录哪个阶段被退回、原因和退回次数。"""
	
	from_stage: WorkflowState      # 从哪个阶段退回
	to_stage: WorkflowState        # 退回到哪个阶段
	reason: str                    # 退回原因
	timestamp: datetime            # 退回时间
	retry_count: int               # 当前是第几次重试


@dataclass
class WorkflowContext:
	"""工作流全局上下文 — 聚合所有阶段的数据和执行历史。
	
	职责：
	  1. 存储各阶段的输入输出（planner_output, writer_output 等）
	  2. 记录执行历史（每个阶段的耗时、错误）
	  3. 管理退回重做次数（防止无限循环）
	  4. 提供数据访问接口（get_stage_output / get_latest_content 等）
	"""
	
	# ── 用户原始输入 ──
	topic: str
	audience: str
	goal: str
	word_count: str
	tone: str
	requirements: list[str] | None = None
	constraints: list[str] | None = None
	
	# ── 当前状态 ──
	current_state: WorkflowState = WorkflowState.PLANNING
	
	# ── 各阶段输出（动态填充）──
	planner_output: dict[str, Any] | None = None
	writer_output: dict[str, Any] | None = None
	fact_checker_output: dict[str, Any] | None = None
	polisher_output: dict[str, Any] | None = None
	reviewer_output: dict[str, Any] | None = None
	
	# ── 执行历史 ──
	history: list[StageRecord] = field(default_factory=list)
	retry_records: list[RetryRecord] = field(default_factory=list)
	
	# ── 重试控制 ──
	max_retries: int = 3           # 每个阶段最多重试次数
	retry_counts: dict[WorkflowState, int] = field(default_factory=dict)
	
	# ── 元信息 ──
	workflow_id: str = field(default_factory=lambda: datetime.now().strftime("%Y%m%d_%H%M%S"))
	started_at: datetime = field(default_factory=datetime.now)
	completed_at: datetime | None = None
	
	def start_stage(self, stage: WorkflowState, input_data: dict[str, Any]) -> None:
		"""记录阶段开始。
		
		Args:
			stage: 即将执行的阶段
			input_data: 阶段输入数据
		"""
		self.current_state = stage
		record = StageRecord(
			stage=stage,
			started_at=datetime.now(),
			input_data=input_data,
		)
		self.history.append(record)
	
	def complete_stage(self, stage: WorkflowState, output_data: dict[str, Any]) -> None:
		"""记录阶段完成。
		
		Args:
			stage: 完成的阶段
			output_data: 阶段输出数据
		"""
		# 更新最后一条记录
		if self.history and self.history[-1].stage == stage:
			self.history[-1].completed_at = datetime.now()
			self.history[-1].output_data = output_data
		
		# 存储到对应字段
		if stage == WorkflowState.PLANNING:
			self.planner_output = output_data
		elif stage == WorkflowState.WRITING:
			self.writer_output = output_data
		elif stage == WorkflowState.FACT_CHECKING:
			self.fact_checker_output = output_data
		elif stage == WorkflowState.POLISHING:
			self.polisher_output = output_data
		elif stage == WorkflowState.REVIEWING:
			self.reviewer_output = output_data
	
	def fail_stage(self, stage: WorkflowState, error: str) -> None:
		"""记录阶段失败。
		
		Args:
			stage: 失败的阶段
			error: 错误信息
		"""
		if self.history and self.history[-1].stage == stage:
			self.history[-1].completed_at = datetime.now()
			self.history[-1].error = error
	
	def record_retry(self, from_stage: WorkflowState, to_stage: WorkflowState, reason: str) -> None:
		"""记录退回重做。
		
		Args:
			from_stage: 从哪个阶段退回
			to_stage: 退回到哪个阶段
			reason: 退回原因
		"""
		# 增加目标阶段的重试计数
		self.retry_counts[to_stage] = self.retry_counts.get(to_stage, 0) + 1
		
		# 添加退回记录
		retry_record = RetryRecord(
			from_stage=from_stage,
			to_stage=to_stage,
			reason=reason,
			timestamp=datetime.now(),
			retry_count=self.retry_counts[to_stage],
		)
		self.retry_records.append(retry_record)
	
	def can_retry(self, stage: WorkflowState) -> bool:
		"""判断某阶段是否还能重试。
		
		Args:
			stage: 要检查的阶段
			
		Returns:
			bool: 如果未超过最大重试次数则返回 True
		"""
		return self.retry_counts.get(stage, 0) < self.max_retries
	
	def get_stage_output(self, stage: WorkflowState) -> dict[str, Any] | None:
		"""获取指定阶段的输出。
		
		Args:
			stage: 阶段名称
			
		Returns:
			dict | None: 阶段输出数据，未执行则返回 None
		"""
		mapping = {
			WorkflowState.PLANNING: self.planner_output,
			WorkflowState.WRITING: self.writer_output,
			WorkflowState.FACT_CHECKING: self.fact_checker_output,
			WorkflowState.POLISHING: self.polisher_output,
			WorkflowState.REVIEWING: self.reviewer_output,
		}
		return mapping.get(stage)
	
	def get_latest_content(self) -> str | None:
		"""获取当前最新的文章内容（优先取 polisher > writer）。
		
		Returns:
			str | None: 文章内容，未生成则返回 None
		"""
		if self.polisher_output and "content" in self.polisher_output:
			return self.polisher_output["content"]
		if self.writer_output and "content" in self.writer_output:
			return self.writer_output["content"]
		return None
	
	def get_retry_summary(self) -> str:
		"""生成重试摘要（用于日志和报告）。
		
		Returns:
			str: 重试信息摘要
		"""
		if not self.retry_records:
			return "无退回重做"
		
		lines = [f"共 {len(self.retry_records)} 次退回重做："]
		for i, record in enumerate(self.retry_records, 1):
			lines.append(
				f"  {i}. {record.from_stage.value} → {record.to_stage.value} "
				f"(第 {record.retry_count} 次): {record.reason}"
			)
		return "\n".join(lines)
	
	def to_summary(self) -> dict[str, Any]:
		"""生成工作流执行摘要（用于保存和展示）。
		
		Returns:
			dict: 包含关键信息的摘要
		"""
		duration = None
		if self.completed_at:
			duration = (self.completed_at - self.started_at).total_seconds()
		
		return {
			"workflow_id": self.workflow_id,
			"topic": self.topic,
			"current_state": self.current_state.value,
			"started_at": self.started_at.isoformat(),
			"completed_at": self.completed_at.isoformat() if self.completed_at else None,
			"duration_seconds": duration,
			"stages_executed": len(self.history),
			"retry_count": len(self.retry_records),
			"retry_summary": self.get_retry_summary(),
			"final_content_available": self.get_latest_content() is not None,
		}
