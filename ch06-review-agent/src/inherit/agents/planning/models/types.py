"""规划数据模型 — DecompositionResult, InspectionResult, SubTask 等核心类型。

Pydantic v2，用于 LLM 结构化输出和内部状态管理。
"""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


# ============================================================
# 枚举
# ============================================================

class TaskStatus(str, Enum):
	"""子任务执行状态。"""
	PENDING = "pending"
	IN_PROGRESS = "in_progress"
	COMPLETED = "completed"


# ============================================================
# 工具调用相关
# ============================================================

class ToolCallPlan(BaseModel):
	"""规划器/审查器生成的工具调用计划。"""
	tool_name: str = Field(description="工具名称")
	arguments: dict[str, Any] = Field(default_factory=dict, description="工具参数")
	reason: str = Field(default="", description="为什么需要这个调用")


	def to_display(self) -> str:
		"""供控制台输出的可读描述。"""
		args_str = ", ".join(f"{k}={v}" for k, v in self.arguments.items())
		return f"{self.tool_name}({args_str}) — {self.reason}"


class ToolResult(BaseModel):
	"""单次工具调用的执行结果。"""
	tool_name: str
	arguments: dict[str, Any]
	result: str
	is_error: bool = False


# ============================================================
# 子任务
# ============================================================

class SubTask(BaseModel):
	"""规划器分解出的子任务。

	既包含语义描述，也包含建议的工具调用列表。
	执行时由 PlanningAgent 驱动 Function Calling LLM 完成。
	"""
	id: str = Field(description="任务 ID，如 task-1")
	description: str = Field(description='语义描述，如「查询目标相关信息」')
	tool_calls: list[ToolCallPlan] = Field(
		default_factory=list,
		description="建议的工具调用，LLM 可根据上下文调整",
	)
	depends_on: list[str] = Field(
		default_factory=list,
		description="依赖的前置任务 ID 列表",
	)
	status: TaskStatus = Field(default=TaskStatus.PENDING)


# ============================================================
# 规划阶段
# ============================================================

class DecompositionResult(BaseModel):
	"""TaskDecomposer 的输出：分解结果 + 推理链。"""
	tasks: list[SubTask] = Field(description="分解出的子任务列表")
	reasoning: str = Field(description="规划推理过程")


# ============================================================
# 审查阶段
# ============================================================

class InspectionResult(BaseModel):
	"""InfoInspector 的输出：信息充分性判断 + 补充任务。"""
	is_sufficient: bool = Field(description="当前收集的信息是否足以生成最终方案")
	gaps: list[str] = Field(default_factory=list, description="仍缺失或不够明确的信息维度")
	additional_tool_calls: list[ToolCallPlan] = Field(
		default_factory=list, description="为填补缺口需要新增的工具调用"
	)
	reasoning: str = Field(default="", description="审查推理")


# ============================================================
# 收集到的信息（给 PlanReporter 用）
# ============================================================

class TaskExecutionRecord(BaseModel):
	"""一个子任务执行完毕后留下的记录。"""
	task: SubTask
	results: list[ToolResult] = Field(default_factory=list)


	def to_context_string(self) -> str:
		"""转为 PlanReporter 可用的文本。"""
		lines = [f"## {self.task.id}: {self.task.description}"]
		for r in self.results:
			status = "❌ 错误" if r.is_error else "✅"
			lines.append(f"- {status} {r.tool_name}({r.arguments}): {r.result[:500]}")
		return "\n".join(lines)
