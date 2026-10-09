"""工作流综合评估器 — 评估输出质量、角色表现和协作效果。

WorkflowEvaluator 负责：
  1. 评估各阶段/角色表现（质量、效率、重试情况）
  2. 评估协作效果（流程衔接、退回原因）
  3. 识别问题并生成优化建议
  4. 生成综合评估报告
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from inherit.llm.client import LLMClient
from inherit.prompt.prompt_manager import PromptManager
from agents.write_studio.evaluation.stage_evaluator import StageEvaluator


class StagePerformance(BaseModel):
	"""单个阶段/角色的表现评估（合并质量和表现）。"""
	stage: str = Field(description="阶段标识（如 planning）")
	agent_name: str = Field(description="角色名称（如策划编辑）")
	
	# 输出质量
	quality_score: int = Field(description="输出质量评分（1-10）", ge=1, le=10)
	summary: str = Field(description="质量评估摘要")
	issues: list[str] = Field(default_factory=list, description="发现的问题列表")
	strengths: list[str] = Field(default_factory=list, description="优点/亮点列表")
	
	# 执行表现
	execution_time: float = Field(default=0.0, description="执行耗时（秒）")
	retry_count: int = Field(default=0, description="重试次数")
	success: bool = Field(default=True, description="是否执行成功")


class CollaborationIssue(BaseModel):
	"""协作/流程衔接问题。"""
	from_stage: str = Field(description="退回源阶段")
	to_stage: str = Field(description="退回目标阶段")
	reason: str = Field(description="退回原因")
	retry_count: int = Field(description="该路径的重试次数")
	severity: str = Field(description="严重程度", pattern="^(low|medium|high)$")


class CollaborationAnalysis(BaseModel):
	"""协作效果分析。"""
	retry_count: int = Field(description="总退回次数")
	retry_rate: float = Field(description="退回率（退回次数/阶段数）")
	avg_stage_time: float = Field(description="平均阶段耗时（秒）")
	collaboration_quality: str = Field(description="协作质量评价（优秀/良好/一般/较差）")
	collaboration_desc: str = Field(description="协作效果描述")


class PerformanceSummary(BaseModel):
	"""整体表现摘要。"""
	total_execution_time: float = Field(description="总执行时间（秒）")
	total_retries: int = Field(description="总重试次数")
	average_quality_score: float = Field(description="平均质量评分")
	
	best_performer: dict[str, Any] = Field(description="最佳表现者")
	worst_performer: dict[str, Any] = Field(description="待改进者")
	slowest_stage: dict[str, Any] = Field(description="最慢阶段")


class EvaluationReport(BaseModel):
	"""综合评估报告。"""
	workflow_id: str = Field(description="工作流ID")
	topic: str = Field(description="文章主题")
	evaluated_at: str = Field(description="评估时间")
	
	# 各阶段/角色表现评估（合并质量和表现）
	stage_performances: list[StagePerformance] = Field(
		default_factory=list,
		description="各阶段/角色表现评估"
	)
	
	# 整体表现摘要
	performance_summary: PerformanceSummary | None = Field(
		default=None,
		description="整体表现摘要"
	)
	
	# 协作效果分析
	collaboration_analysis: CollaborationAnalysis | None = Field(
		default=None,
		description="协作效果分析"
	)
	
	# 流程衔接问题
	workflow_issues: list[CollaborationIssue] = Field(
		default_factory=list,
		description="流程衔接问题列表"
	)
	
	# 优化建议
	recommendations: list[str] = Field(
		default_factory=list,
		description="优化建议列表"
	)
	
	# 综合评分
	overall_score: float = Field(default=0.0, description="综合评分（1-10）", ge=0, le=10)


class WorkflowEvaluator:
	"""工作流综合评估器。
	
	职责：
	  1. 评估各阶段/角色表现（质量+效率+重试）
	  2. 分析协作效果（流程衔接）
	  3. 识别问题并生成优化建议
	  4. 生成综合评估报告
	"""
	
	def __init__(self, llm: LLMClient, pm: PromptManager):
		"""初始化评估器。
		
		Args:
			llm: LLM 客户端
			pm: Prompt 管理器
		"""
		self.llm = llm
		self.pm = pm
		self.stage_evaluator = StageEvaluator(llm, pm)
	
	def evaluate_workflow(
		self,
		workflow_dir: Path,
		workflow_summary: dict[str, Any],
	) -> EvaluationReport:
		"""评估完整工作流。
		
		Args:
			workflow_dir: 工作流输出目录
			workflow_summary: 工作流摘要数据
			
		Returns:
			EvaluationReport: 综合评估报告
		"""
		# 1. 评估各阶段/角色表现
		stage_performances = self._evaluate_stage_performances(
			workflow_dir,
			workflow_summary,
		)
		
		# 2. 分析协作效果
		collaboration_analysis = self._analyze_collaboration(workflow_summary)
		
		# 3. 识别流程衔接问题
		workflow_issues = self._identify_workflow_issues(workflow_summary)
		
		# 4. 生成整体表现摘要
		performance_summary = self._generate_performance_summary(stage_performances)
		
		# 5. 生成优化建议
		recommendations = self._generate_recommendations(
			stage_performances,
			performance_summary,
			collaboration_analysis,
			workflow_issues,
		)
		
		# 6. 计算综合评分
		overall_score = self._calculate_overall_score(
			stage_performances,
			collaboration_analysis,
		)
		
		# 构建报告
		report = EvaluationReport(
			workflow_id=workflow_summary.get("workflow_id", "unknown"),
			topic=workflow_summary.get("topic", ""),
			evaluated_at=datetime.now().isoformat(),
			stage_performances=stage_performances,
			performance_summary=performance_summary,
			collaboration_analysis=collaboration_analysis,
			workflow_issues=workflow_issues,
			recommendations=recommendations,
			overall_score=overall_score,
		)
		
		return report
	
	def _evaluate_stage_performances(
		self,
		workflow_dir: Path,
		workflow_summary: dict[str, Any],
	) -> list[StagePerformance]:
		"""评估各阶段/角色表现（合并质量和表现）。"""
		performances = []
		
		# 阶段名称映射
		stage_name_map = {
			"planning": "策划编辑",
			"researching": "资料研究员",
			"writing": "内容作者",
			"fact_checking": "事实核查员",
			"polishing": "润色编辑",
			"reviewing": "审稿主编",
		}
		
		stages = ["planning", "researching", "writing", "fact_checking", "polishing", "reviewing"]
		
		for stage in stages:
			output_file = workflow_dir / f"{stage}_output.json"
			
			if not output_file.exists():
				continue
			
			try:
				# 加载输出数据
				with open(output_file, encoding="utf-8") as f:
					output_data = json.load(f)
				
				# 构造输入数据（简化）
				input_data = {
					"topic": workflow_summary.get("topic", ""),
					"audience": workflow_summary.get("audience", ""),
				}
				
				# 调用阶段评估器（评估输出质量）
				evaluation = self.stage_evaluator.evaluate(
					stage_name=stage,
					input_data=input_data,
					output_data=output_data,
				)
				
				# 获取执行信息（执行表现）
				agents = workflow_summary.get("agents", [])
				agent_info = next((a for a in agents if a.get("stage") == stage), {})
				
				# 合并为单一的 StagePerformance
				performance = StagePerformance(
					stage=stage,
					agent_name=stage_name_map.get(stage, stage),
					quality_score=evaluation["quality_score"],
					summary=evaluation["summary"],
					issues=evaluation.get("issues", []),
					strengths=evaluation.get("strengths", []),
					execution_time=agent_info.get("time", 0.0),
					retry_count=agent_info.get("retries", 0),
					success=agent_info.get("success", True),
				)
				
				performances.append(performance)
				
			except Exception as e:
				print(f"[警告] 评估阶段 {stage} 失败: {e}")
				continue
		
		return performances
	
	def _generate_performance_summary(
		self,
		stage_performances: list[StagePerformance],
	) -> PerformanceSummary | None:
		"""生成整体表现摘要。"""
		if not stage_performances:
			return None
		
		# 计算统计指标
		total_time = sum(sp.execution_time for sp in stage_performances)
		total_retries = sum(sp.retry_count for sp in stage_performances)
		avg_quality = sum(sp.quality_score for sp in stage_performances) / len(stage_performances)
		
		# 找出表现最好、最差、最慢的阶段
		best = max(stage_performances, key=lambda x: x.quality_score)
		worst = min(stage_performances, key=lambda x: x.quality_score)
		slowest = max(stage_performances, key=lambda x: x.execution_time)
		
		return PerformanceSummary(
			total_execution_time=round(total_time, 2),
			total_retries=total_retries,
			average_quality_score=round(avg_quality, 1),
			best_performer={
				"agent": best.agent_name,
				"stage": best.stage,
				"score": best.quality_score,
				"reason": best.summary,
			},
			worst_performer={
				"agent": worst.agent_name,
				"stage": worst.stage,
				"score": worst.quality_score,
				"reason": worst.summary,
			},
			slowest_stage={
				"agent": slowest.agent_name,
				"stage": slowest.stage,
				"time": round(slowest.execution_time, 2),
			},
		)
	
	def _analyze_collaboration(
		self,
		workflow_summary: dict[str, Any],
	) -> CollaborationAnalysis:
		"""评估协作效果。"""
		retry_count = workflow_summary.get("retry_count", 0)
		stages_executed = workflow_summary.get("stages_executed", 0)
		duration = workflow_summary.get("duration_seconds", 0)
		
		# 计算协作效率
		if stages_executed > 0:
			retry_rate = retry_count / stages_executed
			avg_stage_time = duration / stages_executed
		else:
			retry_rate = 0.0
			avg_stage_time = 0.0
		
		# 评估协作质量
		if retry_rate == 0:
			collaboration_quality = "优秀"
			collaboration_desc = "所有阶段一次通过，协作非常顺畅"
		elif retry_rate < 0.2:
			collaboration_quality = "良好"
			collaboration_desc = "少量退回重做，协作基本顺畅"
		elif retry_rate < 0.5:
			collaboration_quality = "一般"
			collaboration_desc = "多次退回重做，协作存在摩擦"
		else:
			collaboration_quality = "较差"
			collaboration_desc = "频繁退回重做，协作效率低下"
		
		return CollaborationAnalysis(
			retry_count=retry_count,
			retry_rate=round(retry_rate, 2),
			avg_stage_time=round(avg_stage_time, 2),
			collaboration_quality=collaboration_quality,
			collaboration_desc=collaboration_desc,
		)
	
	def _identify_workflow_issues(
		self,
		workflow_summary: dict[str, Any],
	) -> list[CollaborationIssue]:
		"""识别流程衔接问题。"""
		issues = []
		
		retry_summary = workflow_summary.get("retry_summary", "")
		
		# 解析 retry_summary
		# 格式："共 X 次退回重做：\n  1. from_stage → to_stage (第 N 次): reason"
		if "次退回重做" in retry_summary:
			lines = retry_summary.split("\n")[1:]  # 跳过第一行
			
			for line in lines:
				if "→" in line:
					try:
						# 提取信息
						parts = line.split("→")
						from_stage = parts[0].split(".")[-1].strip()
						
						to_parts = parts[1].split("(")
						to_stage = to_parts[0].strip()
						
						reason_parts = parts[1].split(":")
						reason = reason_parts[-1].strip() if len(reason_parts) > 1 else "未知原因"
						
						retry_count_str = parts[1].split("第")[1].split("次")[0].strip()
						retry_count = int(retry_count_str)
						
						# 判断严重程度
						if retry_count == 1:
							severity = "low"
						elif retry_count == 2:
							severity = "medium"
						else:
							severity = "high"
						
						issues.append(CollaborationIssue(
							from_stage=from_stage,
							to_stage=to_stage,
							reason=reason,
							retry_count=retry_count,
							severity=severity,
						))
						
					except Exception as e:
						print(f"[警告] 解析退回记录失败: {e}")
						continue
		
		return issues
	
	def _generate_recommendations(
		self,
		stage_performances: list[StagePerformance],
		performance_summary: PerformanceSummary | None,
		collaboration_analysis: CollaborationAnalysis,
		workflow_issues: list[CollaborationIssue],
	) -> list[str]:
		"""生成优化建议。"""
		recommendations = []
		
		# 1. 基于质量评分的建议
		low_quality_stages = [sp for sp in stage_performances if sp.quality_score < 7]
		if low_quality_stages:
			for stage in low_quality_stages:
				recommendations.append(
					f"优化 {stage.agent_name} 的 Prompt：{stage.summary}，"
					f"主要问题：{', '.join(stage.issues[:2]) if stage.issues else '无'}"
				)
		
		# 2. 基于重试次数的建议
		high_retry_stages = [sp for sp in stage_performances if sp.retry_count >= 2]
		if high_retry_stages:
			for stage in high_retry_stages:
				recommendations.append(
					f"检查 {stage.agent_name} 的输出格式和质量门禁逻辑，"
					f"该阶段重试 {stage.retry_count} 次"
				)
		
		# 3. 基于执行时间的建议
		if performance_summary and performance_summary.slowest_stage["time"] > 30:
			slowest = performance_summary.slowest_stage
			recommendations.append(
				f"优化 {slowest['agent']} 的执行效率，"
				f"当前耗时 {slowest['time']}s，可考虑减少生成 token 数或优化 Prompt"
			)
		
		# 4. 基于协作效果的建议
		if collaboration_analysis.retry_rate > 0.3:
			recommendations.append(
				"协作效率较低，建议检查质量门禁是否过于严格，"
				"或各 Agent 的输出是否符合下游需求"
			)
		
		# 5. 基于流程衔接问题的建议
		if workflow_issues:
			# 找出最常见的退回路径
			issue_paths: dict[str, int] = {}
			for issue in workflow_issues:
				key = f"{issue.from_stage} → {issue.to_stage}"
				issue_paths[key] = issue_paths.get(key, 0) + 1
			
			most_common_path = max(issue_paths.items(), key=lambda x: x[1])[0]
			recommendations.append(
				f"重点优化 {most_common_path} 的衔接，"
				f"这是最常见的退回路径"
			)
		
		# 6. 基于问题类型的建议
		all_issues = []
		for sp in stage_performances:
			all_issues.extend(sp.issues)
		
		if all_issues:
			# 简单统计常见问题关键词
			issue_keywords: dict[str, int] = {}
			for issue in all_issues:
				for word in ["格式", "完整性", "准确性", "规范", "结构"]:
					if word in issue:
						issue_keywords[word] = issue_keywords.get(word, 0) + 1
			
			if issue_keywords:
				top_issue = max(issue_keywords.items(), key=lambda x: x[1])[0]
				recommendations.append(
					f"多个阶段存在 {top_issue} 问题，"
					f"建议在 System Prompt 中强化相关要求"
				)
		
		# 如果没有明显问题，给出正面建议
		if not recommendations:
			avg_quality = performance_summary.average_quality_score if performance_summary else 0
			if avg_quality >= 8:
				recommendations.append("整体表现优秀，可尝试更复杂的写作任务")
			else:
				recommendations.append("整体表现良好，继续保持当前配置")
		
		return recommendations
	
	def _calculate_overall_score(
		self,
		stage_performances: list[StagePerformance],
		collaboration_analysis: CollaborationAnalysis,
	) -> float:
		"""计算综合评分（1-10）。"""
		if not stage_performances:
			return 0.0
		
		# 质量评分（权重 70%）
		avg_quality = sum(sp.quality_score for sp in stage_performances) / len(stage_performances)
		quality_component = avg_quality * 0.7
		
		# 协作效率（权重 30%）
		# 将 retry_rate 转换为 0-10 的评分（retry_rate 越低越好）
		collaboration_score = max(0, 10 - collaboration_analysis.retry_rate * 20)
		collaboration_component = collaboration_score * 0.3
		
		overall = quality_component + collaboration_component
		return round(overall, 1)
	
	def save_report(self, report: EvaluationReport, output_path: Path) -> None:
		"""保存评估报告到文件。
		
		Args:
			report: 评估报告
			output_path: 输出文件路径
		"""
		with open(output_path, "w", encoding="utf-8") as f:
			json.dump(report.model_dump(), f, indent=2, ensure_ascii=False)
	
	def print_report_summary(self, report: EvaluationReport) -> None:
		"""打印评估报告摘要。
		
		Args:
			report: 评估报告
		"""
		print("\n" + "=" * 70)
		print("综合评估报告")
		print("=" * 70)
		print(f"主题：{report.topic}")
		print(f"工作流 ID：{report.workflow_id}")
		print(f"评估时间：{report.evaluated_at}")
		print(f"综合评分：{report.overall_score}/10")
		
		# 阶段/角色表现
		print(f"\n【阶段/角色表现】共评估 {len(report.stage_performances)} 个阶段")
		for sp in report.stage_performances:
			status = "✓" if sp.success else "✗"
			print(f"  {status} {sp.agent_name}: 质量{sp.quality_score}/10, "
			      f"耗时{sp.execution_time:.1f}s, 重试{sp.retry_count}次")
			if sp.issues:
				print(f"     问题: {', '.join(sp.issues[:2])}")
		
		# 整体表现摘要
		if report.performance_summary:
			ps = report.performance_summary
			print(f"\n【整体表现摘要】")
			print(f"  平均质量：{ps.average_quality_score}/10")
			print(f"  总耗时：{ps.total_execution_time}s")
			print(f"  总重试：{ps.total_retries}次")
			print(f"  最佳表现：{ps.best_performer['agent']} ({ps.best_performer['score']}/10)")
			print(f"  待改进：{ps.worst_performer['agent']} ({ps.worst_performer['score']}/10)")
		
		# 协作效果
		if report.collaboration_analysis:
			ca = report.collaboration_analysis
			print(f"\n【协作效果】")
			print(f"  评价：{ca.collaboration_quality}")
			print(f"  描述：{ca.collaboration_desc}")
			print(f"  退回率：{ca.retry_rate:.1%}")
		
		# 流程衔接问题
		if report.workflow_issues:
			print(f"\n【流程衔接问题】发现 {len(report.workflow_issues)} 个问题")
			severity_label = {"low": "轻微", "medium": "中等", "high": "严重"}
			for issue in report.workflow_issues[:3]:  # 只显示前3个
				print(f"  [{severity_label.get(issue.severity, '未知')}] "
				      f"{issue.from_stage} → {issue.to_stage}: {issue.reason}")
		
		# 优化建议
		if report.recommendations:
			print(f"\n【优化建议】")
			for i, rec in enumerate(report.recommendations[:5], 1):  # 只显示前5条
				print(f"  {i}. {rec}")
		
		print("\n" + "=" * 70)
