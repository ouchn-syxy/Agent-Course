"""质量门禁机制 — 决定流程是否通过或需要退回重做。

QualityGate 根据 Agent 输出判断质量是否达标，
并生成对应的流转决策（继续前进 / 退回指定阶段 / 终止流程）。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from agents.write_studio.workflow.state import FactCheckVerdict, ReviewDecision, WorkflowState


@dataclass
class GateDecision:
	"""门禁决策 — 描述当前阶段完成后的流转方向。"""
	
	pass_gate: bool                # 是否通过门禁
	next_state: WorkflowState      # 下一状态（通过则前进，不通过则退回）
	reason: str                    # 决策理由
	severity: str = "info"         # 严重等级：info / warning / error
	
	@classmethod
	def approve(cls, next_state: WorkflowState, reason: str = "质量合格，继续流程") -> GateDecision:
		"""创建"通过"决策。"""
		return cls(pass_gate=True, next_state=next_state, reason=reason, severity="info")
	
	@classmethod
	def reject(cls, target_state: WorkflowState, reason: str, severity: str = "warning") -> GateDecision:
		"""创建"退回"决策。"""
		return cls(pass_gate=False, next_state=target_state, reason=reason, severity=severity)
	
	@classmethod
	def terminate(cls, reason: str) -> GateDecision:
		"""创建"终止"决策（流程失败）。"""
		return cls(pass_gate=False, next_state=WorkflowState.FAILED, reason=reason, severity="error")


class QualityGate:
	"""质量门禁 — 评估各阶段输出并生成流转决策。
	
	每个阶段完成后都会经过对应的门禁检查：
	  - PLANNING: 无门禁（直接通过）
	  - WRITING: 无门禁（由后续 FACT_CHECKING 检查）
	  - FACT_CHECKING: 根据 verdict 决定是否退回 WRITING
	  - POLISHING: 无门禁（由后续 REVIEWING 检查）
	  - REVIEWING: 根据 decision 决定通过 / 退回润色 / 退回重写 / 拒绝
	"""
	
	def __init__(self, max_retries: int = 3, enable_researcher: bool = False):
		"""初始化门禁。
		
		Args:
			max_retries: 每个阶段最多重试次数
			enable_researcher: 是否启用 Researcher 阶段
		"""
		self.max_retries = max_retries
		self.enable_researcher = enable_researcher
	
	def check_planning(self, output: dict[str, Any], enable_researcher: bool = False) -> GateDecision:
		"""策划阶段门禁 — 无质量检查，直接通过。
		
		Args:
			output: PlannerAgent 输出
			enable_researcher: 是否启用 Researcher 阶段
			
		Returns:
			GateDecision: 通过决策
		"""
		# 策划阶段不设门禁，根据配置进入 Researcher 或 Writer
		if enable_researcher:
			return GateDecision.approve(
				next_state=WorkflowState.RESEARCHING,
				reason="策划完成，进入资料调研阶段",
			)
		else:
			return GateDecision.approve(
				next_state=WorkflowState.WRITING,
				reason="策划完成，进入写作阶段",
			)
	
	def check_researching(self, output: dict[str, Any]) -> GateDecision:
		"""资料调研阶段门禁 — 无质量检查，直接通过。
		
		Args:
			output: ResearcherAgent 输出
			
		Returns:
			GateDecision: 通过决策
		"""
		# 调研阶段不设门禁，直接进入写作
		sources_count = len(output.get("sources", []))
		return GateDecision.approve(
			next_state=WorkflowState.WRITING,
			reason=f"资料调研完成（收集 {sources_count} 个来源），进入写作阶段",
		)
	
	def check_writing(self, output: dict[str, Any]) -> GateDecision:
		"""写作阶段门禁 — 无质量检查，直接通过。
		
		Args:
			output: WriterAgent 输出
			
		Returns:
			GateDecision: 通过决策
		"""
		# 写作阶段不设门禁，由后续事实核查环节检验
		return GateDecision.approve(
			next_state=WorkflowState.FACT_CHECKING,
			reason="初稿完成，进入事实核查阶段",
		)
	
	def check_fact_checking(self, output: dict[str, Any], retry_count: int) -> GateDecision:
		"""事实核查阶段门禁 — 根据 verdict 决定是否退回。
		
		决策规则：
		  - PASS: 通过，进入润色
		  - PASS_WITH_WARNINGS: 通过但记录警告
		  - FAIL: 退回写作（未超过重试次数）或终止（超过重试次数）
		
		Args:
			output: FactCheckerAgent 输出
			retry_count: 写作阶段当前重试次数
			
		Returns:
			GateDecision: 流转决策
		"""
		verdict_str = output.get("verdict")
		
		# 解析 verdict
		try:
			verdict = FactCheckVerdict(verdict_str)
		except ValueError:
			# 如果 verdict 不合法，默认通过但记录警告
			return GateDecision.approve(
				next_state=WorkflowState.POLISHING,
				reason=f"事实核查结果不明确（{verdict_str}），默认通过",
			)
		
		# 通过
		if verdict == FactCheckVerdict.PASS:
			return GateDecision.approve(
				next_state=WorkflowState.POLISHING,
				reason="事实核查通过，无问题发现",
			)
		
		# 通过但有警告
		if verdict == FactCheckVerdict.PASS_WITH_WARNINGS:
			issues = output.get("issues", [])
			warning_count = len([i for i in issues if i.get("severity") == "minor"])
			return GateDecision.approve(
				next_state=WorkflowState.POLISHING,
				reason=f"事实核查通过，但发现 {warning_count} 个轻微问题",
			)
		
		# 失败 — 判断是否还能重试
		if verdict == FactCheckVerdict.FAIL:
			if retry_count >= self.max_retries:
				# 超过重试次数，终止流程
				return GateDecision.terminate(
					reason=f"事实核查失败，且写作阶段已重试 {retry_count} 次（超过上限 {self.max_retries}）",
				)
			else:
				# 退回写作重做
				issues = output.get("issues", [])
				critical_count = len([i for i in issues if i.get("severity") == "critical"])
				return GateDecision.reject(
					target_state=WorkflowState.WRITING,
					reason=f"事实核查发现 {critical_count} 个严重问题，退回重写（第 {retry_count + 1} 次）",
					severity="warning",
				)
		
		# 默认通过（不应到达此处）
		return GateDecision.approve(
			next_state=WorkflowState.POLISHING,
			reason="事实核查完成",
		)
	
	def check_polishing(self, output: dict[str, Any]) -> GateDecision:
		"""润色阶段门禁 — 无质量检查，直接通过。
		
		Args:
			output: PolisherAgent 输出
			
		Returns:
			GateDecision: 通过决策
		"""
		# 润色阶段不设门禁，由后续审稿环节检验
		return GateDecision.approve(
			next_state=WorkflowState.REVIEWING,
			reason="润色完成，进入审稿阶段",
		)
	
	def check_reviewing(
		self,
		output: dict[str, Any],
		writing_retry_count: int,
		polishing_retry_count: int,
	) -> GateDecision:
		"""审稿阶段门禁 — 根据 decision 决定最终流转。
		
		决策规则：
		  - APPROVE: 通过，流程完成
		  - REVISE_POLISH: 退回润色（未超过重试次数）或降级通过
		  - REVISE_WRITE: 退回写作（未超过重试次数）或降级退回润色
		  - REJECT: 终止流程
		
		Args:
			output: ReviewerAgent 输出
			writing_retry_count: 写作阶段当前重试次数
			polishing_retry_count: 润色阶段当前重试次数
			
		Returns:
			GateDecision: 流转决策
		"""
		decision_str = output.get("decision")
		
		# 解析 decision
		try:
			decision = ReviewDecision(decision_str)
		except ValueError:
			# 如果 decision 不合法，默认通过
			return GateDecision.approve(
				next_state=WorkflowState.COMPLETED,
				reason=f"审稿决策不明确（{decision_str}），默认通过",
			)
		
		# 通过
		if decision == ReviewDecision.APPROVE:
			overall_score = output.get("overall_score", "N/A")
			return GateDecision.approve(
				next_state=WorkflowState.COMPLETED,
				reason=f"审稿通过（综合评分：{overall_score}），文章发布",
			)
		
		# 退回润色
		if decision == ReviewDecision.REVISE_POLISH:
			if polishing_retry_count >= self.max_retries:
				# 超过重试次数，降级通过
				return GateDecision.approve(
					next_state=WorkflowState.COMPLETED,
					reason=f"审稿建议润色，但已重试 {polishing_retry_count} 次，降级通过",
				)
			else:
				# 退回润色
				issues = output.get("issues", [])
				return GateDecision.reject(
					target_state=WorkflowState.POLISHING,
					reason=f"审稿建议优化表达（发现 {len(issues)} 个问题），退回润色（第 {polishing_retry_count + 1} 次）",
					severity="warning",
				)
		
		# 退回重写
		if decision == ReviewDecision.REVISE_WRITE:
			if writing_retry_count >= self.max_retries:
				# 超过重试次数，降级退回润色
				if polishing_retry_count >= self.max_retries:
					# 润色也超限，降级通过
					return GateDecision.approve(
						next_state=WorkflowState.COMPLETED,
						reason=f"审稿建议重写，但已重试 {writing_retry_count} 次，且润色也超限，降级通过",
					)
				else:
					# 降级退回润色
					return GateDecision.reject(
						target_state=WorkflowState.POLISHING,
						reason=f"审稿建议重写，但写作已重试 {writing_retry_count} 次，降级退回润色",
						severity="warning",
					)
			else:
				# 退回写作
				issues = output.get("issues", [])
				return GateDecision.reject(
					target_state=WorkflowState.WRITING,
					reason=f"审稿建议重写（发现 {len(issues)} 个严重问题），退回写作（第 {writing_retry_count + 1} 次）",
					severity="warning",
				)
		
		# 拒绝
		if decision == ReviewDecision.REJECT:
			summary = output.get("summary", "质量不合格")
			return GateDecision.terminate(
				reason=f"审稿拒绝：{summary}",
			)
		
		# 默认通过（不应到达此处）
		return GateDecision.approve(
			next_state=WorkflowState.COMPLETED,
			reason="审稿完成",
		)
