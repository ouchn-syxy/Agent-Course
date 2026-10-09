"""工作流状态定义 — 状态机核心枚举。

定义写作工作室的 5 个核心阶段 + 完成/失败状态。
每个状态对应一个 Agent 或终态。
"""

from enum import Enum


class WorkflowState(str, Enum):
	"""工作流状态枚举 — 描述写作流水线的当前阶段。
	
	状态转移规则：
	  PLANNING → WRITING → FACT_CHECKING → POLISHING → REVIEWING
	                ↑           ↑              ↑            ↑
	                └───────────┴──────────────┴────────────┘
	                        (退回重做)
	
	终态：
	  COMPLETED - 审稿通过，文章完成
	  FAILED    - 超过最大重试次数或遇到不可恢复错误
	"""
	
	# ── 工作阶段 ──
	PLANNING = "planning"          # 策划编辑：制定大纲
	WRITING = "writing"            # 内容作者：撰写初稿
	FACT_CHECKING = "fact_checking"  # 事实核查：验证准确性
	POLISHING = "polishing"        # 润色编辑：优化表达
	REVIEWING = "reviewing"        # 审稿主编：质量终审
	
	# ── 终态 ──
	COMPLETED = "completed"        # 流程完成
	FAILED = "failed"              # 流程失败
	
	def is_terminal(self) -> bool:
		"""判断是否为终态（不可再转移）。"""
		return self in (WorkflowState.COMPLETED, WorkflowState.FAILED)
	
	def next_state(self) -> "WorkflowState":
		"""获取正常流程下的下一状态（不含退回逻辑）。
		
		Returns:
			WorkflowState: 下一状态
			
		Raises:
			ValueError: 当前状态无下一状态（终态或未定义）
		"""
		transitions = {
			WorkflowState.PLANNING: WorkflowState.WRITING,
			WorkflowState.WRITING: WorkflowState.FACT_CHECKING,
			WorkflowState.FACT_CHECKING: WorkflowState.POLISHING,
			WorkflowState.POLISHING: WorkflowState.REVIEWING,
			WorkflowState.REVIEWING: WorkflowState.COMPLETED,
		}
		
		if self not in transitions:
			raise ValueError(f"状态 {self.value} 无下一状态")
		
		return transitions[self]


class ReviewDecision(str, Enum):
	"""审稿决策 — Reviewer 对文章的最终判断。"""
	
	APPROVE = "approve"          # 通过：文章质量合格，可以发布
	REVISE_POLISH = "revise_polish"  # 退回润色：需要优化表达，但结构和内容 OK
	REVISE_WRITE = "revise_write"    # 退回重写：内容或结构有问题，需要大改
	REJECT = "reject"            # 拒绝：质量太差或不符合要求，终止流程


class FactCheckVerdict(str, Enum):
	"""事实核查判断 — FactChecker 对内容的审核结论。"""
	
	PASS = "pass"                # 通过：无严重问题
	PASS_WITH_WARNINGS = "pass_with_warnings"  # 通过但有轻微问题
	FAIL = "fail"                # 失败：存在严重错误，需退回重写
