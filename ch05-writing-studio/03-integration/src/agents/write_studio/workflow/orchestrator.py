"""工作流编排器 — 驱动多智能体协作的核心引擎。

WorkflowOrchestrator 负责：
  1. 按状态机驱动 5 个 Agent 依次执行
  2. 在每个阶段后通过质量门禁判断流转方向
  3. 处理退回重做逻辑（记录、计数、防止死循环）
  4. 管理全局上下文和执行历史
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from agents.write_studio.base import BaseRoleAgent
from agents.write_studio.fact_checker import FactCheckerAgent, FactCheckerInput
from agents.write_studio.planner import PlannerAgent, PlannerInput
from agents.write_studio.polisher import PolisherAgent, PolisherInput
from agents.write_studio.researcher import ResearcherAgent, ResearcherInput
from agents.write_studio.reviewer import ReviewerAgent, ReviewerInput
from agents.write_studio.writer import WriterAgent, WriterInput
from inherit.llm.client import LLMClient
from inherit.llm.tool_client import ToolLLMClient
from inherit.prompt.prompt_manager import PromptManager
from agents.write_studio.workflow.context import WorkflowContext
from agents.write_studio.workflow.gate import GateDecision, QualityGate
from agents.write_studio.workflow.state import WorkflowState


class WorkflowOrchestrator:
	"""工作流编排器 — 多智能体协作引擎。
	
	核心流程：
	  while not terminal_state:
	      1. 根据当前状态选择对应 Agent
	      2. 准备 Agent 输入（从 context 读取前序结果）
	      3. 执行 Agent，记录输出到 context
	      4. 通过质量门禁判断下一状态
	      5. 如果需要退回，记录退回信息并更新状态
	"""
	
	def __init__(
		self,
		llm: LLMClient,
		pm: PromptManager,
		max_retries: int = 3,
		output_dir: Path | None = None,
		enable_researcher: bool = False,
		tavily_api_key: str = "",
	):
		"""初始化编排器。
		
		Args:
			llm: LLM 客户端
			pm: Prompt 管理器
			max_retries: 每个阶段最多重试次数
			output_dir: 输出目录（保存中间结果）
			enable_researcher: 是否启用 Researcher 阶段
			tavily_api_key: Tavily API 密钥（Researcher 需要）
		"""
		self.llm = llm
		self.pm = pm
		self.max_retries = max_retries
		self.output_dir = output_dir or Path("output")
		self.enable_researcher = enable_researcher
		
		# 初始化质量门禁
		self.gate = QualityGate(max_retries=max_retries, enable_researcher=enable_researcher)
		
		# 初始化 6 个 Agent（Researcher 可选）
		self.planner = PlannerAgent(llm, pm)
		
		# Researcher 需要 ToolLLMClient（支持 Function Calling）
		if enable_researcher:
			# 创建 ToolLLMClient（基于现有 LLM 配置）
			tool_llm = ToolLLMClient(
				api_key=llm._api_key,
				base_url=llm._base_url,
				model=llm.model,
				temperature=llm._temperature,
				max_tokens=llm._max_tokens,
			)
			self.researcher = ResearcherAgent(tool_llm, pm, tavily_api_key=tavily_api_key)
		else:
			self.researcher = None
		
		self.writer = WriterAgent(llm, pm)
		self.fact_checker = FactCheckerAgent(llm, pm)
		self.polisher = PolisherAgent(llm, pm)
		self.reviewer = ReviewerAgent(llm, pm)
	
	def run(self, ctx: WorkflowContext) -> WorkflowContext:
		"""执行完整工作流。
		
		Args:
			ctx: 工作流上下文（包含用户输入）
			
		Returns:
			WorkflowContext: 更新后的上下文（包含所有阶段输出和执行历史）
		"""
		print("\n" + "=" * 70)
		print(f"写作工作室协作流程启动")
		print("=" * 70)
		print(f"工作流 ID: {ctx.workflow_id}")
		print(f"主题: {ctx.topic}")
		print(f"读者: {ctx.audience}")
		print(f"目标: {ctx.goal}")
		print(f"最大重试次数: {self.max_retries}")
		print(f"Researcher 模块: {'启用' if self.enable_researcher else '禁用'}")
		print("=" * 70 + "\n")
		
		# 状态机循环
		while not ctx.current_state.is_terminal():
			try:
				# 执行当前阶段
				self._execute_stage(ctx)
				
				# 质量门禁检查
				decision = self._check_gate(ctx)
				
				# 根据门禁决策流转状态
				self._handle_decision(ctx, decision)
				
			except Exception as e:
				# 捕获异常，标记失败
				print(f"\n[错误] 阶段 {ctx.current_state.value} 执行失败: {e}")
				ctx.fail_stage(ctx.current_state, str(e))
				ctx.current_state = WorkflowState.FAILED
				break
		
		# 标记完成
		ctx.completed_at = ctx.started_at.__class__.now()
		
		# 保存最终结果
		self._save_final_result(ctx)
		
		# 打印总结
		self._print_summary(ctx)
		
		return ctx
	
	def _execute_stage(self, ctx: WorkflowContext) -> None:
		"""执行当前阶段的 Agent。
		
		Args:
			ctx: 工作流上下文
		"""
		stage = ctx.current_state
		print(f"\n{'─' * 70}")
		print(f"阶段：{stage.value.upper()}")
		print('─' * 70)
		
		# 准备输入
		agent_input = self._prepare_input(ctx, stage)
		agent_input_dict = agent_input.model_dump() if hasattr(agent_input, 'model_dump') else {}
		
		# 记录开始
		ctx.start_stage(stage, agent_input_dict)
		
		# 选择并执行 Agent
		agent = self._get_agent(stage)
		if agent is None:
			raise ValueError(f"未找到阶段 {stage.value} 对应的 Agent")
		
		print(f"执行 Agent: {agent.meta().role_name}...")
		output = agent.run(agent_input)
		
		# 转换输出为字典
		output_dict = output.model_dump()
		
		# 记录完成（保存输入输出数据，供事后评估使用）
		ctx.complete_stage(stage, output_dict)
		
		# 保存中间结果（包含输入和输出）
		self._save_stage_output(ctx, stage, agent_input_dict, output_dict)
		
		print(f"✓ 阶段 {stage.value} 完成")
	
	def _prepare_input(self, ctx: WorkflowContext, stage: WorkflowState) -> Any:
		"""准备 Agent 输入（从 context 读取前序结果）。
		
		Args:
			ctx: 工作流上下文
			stage: 当前阶段
			
		Returns:
			对应 Agent 的输入模型实例
		"""
		if stage == WorkflowState.PLANNING:
			return PlannerInput(
				topic=ctx.topic,
				audience=ctx.audience,
				goal=ctx.goal,
				word_count=ctx.word_count,
				tone=ctx.tone,
				requirements=ctx.requirements,
				constraints=ctx.constraints,
			)
		
		elif stage == WorkflowState.RESEARCHING:
			if ctx.planner_output is None:
				raise ValueError("planner_output 为空，无法执行 researcher")
			
			# 提取 core_message 文本（可能是字典或字符串）
			core_msg = ctx.planner_output["core_message"]
			if isinstance(core_msg, dict):
				core_msg = core_msg.get("angle", "") + " " + core_msg.get("value", "")
			
			# 提取 outline 标题列表（可能是字典列表或字符串列表）
			outline_items = ctx.planner_output["outline"]
			if outline_items and isinstance(outline_items[0], dict):
				outline_items = [item.get("title", str(item)) for item in outline_items]
			
			return ResearcherInput(
				topic=ctx.topic,
				audience=ctx.audience,
				core_message=core_msg,
				outline=outline_items,
				search_keywords=ctx.planner_output.get("search_keywords", []),
			)
		
		elif stage == WorkflowState.WRITING:
			if ctx.planner_output is None:
				raise ValueError("planner_output 为空，无法执行 writer")
			
			# 如果有 Researcher 输出，将其传递给 Writer
			researcher_data = {}
			if ctx.researcher_output:
				researcher_data = {
					"research_sources": ctx.researcher_output.get("sources", []),
					"key_findings": ctx.researcher_output.get("key_findings", []),
					"background_context": ctx.researcher_output.get("background_context", ""),
				}
			
			return WriterInput(
				topic=ctx.topic,
				word_count=ctx.word_count,
				tone=ctx.tone,
				audience_analysis=ctx.planner_output["audience_analysis"],
				core_message=ctx.planner_output["core_message"],
				outline=ctx.planner_output["outline"],
				writing_guidelines=ctx.planner_output["writing_guidelines"],
				**researcher_data,
			)
		
		elif stage == WorkflowState.FACT_CHECKING:
			if ctx.planner_output is None or ctx.writer_output is None:
				raise ValueError("planner_output 或 writer_output 为空，无法执行 fact_checker")
			
			return FactCheckerInput(
				topic=ctx.topic,
				content=ctx.writer_output["content"],
				core_message=ctx.planner_output["core_message"],
				audience_analysis=ctx.planner_output["audience_analysis"],
				outline=ctx.planner_output["outline"],
				writer_notes=ctx.writer_output.get("notes"),
			)
		
		elif stage == WorkflowState.POLISHING:
			if ctx.planner_output is None or ctx.writer_output is None:
				raise ValueError("planner_output 或 writer_output 为空，无法执行 polisher")
			
			return PolisherInput(
				topic=ctx.topic,
				content=ctx.writer_output["content"],
				core_message=ctx.planner_output["core_message"],
				audience_analysis=ctx.planner_output["audience_analysis"],
				outline=ctx.planner_output["outline"],
				writing_guidelines=ctx.planner_output["writing_guidelines"],
			)
		
		elif stage == WorkflowState.REVIEWING:
			if ctx.polisher_output is None:
				raise ValueError("polisher_output 为空，无法执行 reviewer")
			
			return ReviewerInput(
				topic=ctx.topic,
				audience=ctx.audience,
				goal=ctx.goal,
				word_count=ctx.word_count,
				tone=ctx.tone,
				requirements=ctx.requirements,
				constraints=ctx.constraints,
				content=ctx.polisher_output["content"],
			)
		
		else:
			raise ValueError(f"未知阶段：{stage.value}")
	
	def _get_agent(self, stage: WorkflowState) -> BaseRoleAgent | None:
		"""根据阶段获取对应 Agent。
		
		Args:
			stage: 当前阶段
			
		Returns:
			Agent 实例，未找到则返回 None
		"""
		mapping = {
			WorkflowState.PLANNING: self.planner,
			WorkflowState.RESEARCHING: self.researcher,
			WorkflowState.WRITING: self.writer,
			WorkflowState.FACT_CHECKING: self.fact_checker,
			WorkflowState.POLISHING: self.polisher,
			WorkflowState.REVIEWING: self.reviewer,
		}
		return mapping.get(stage)
	
	def _check_gate(self, ctx: WorkflowContext) -> GateDecision:
		"""通过质量门禁检查当前阶段输出。
		
		Args:
			ctx: 工作流上下文
			
		Returns:
			GateDecision: 流转决策
		"""
		stage = ctx.current_state
		output = ctx.get_stage_output(stage)
		
		if output is None:
			return GateDecision.terminate(reason=f"阶段 {stage.value} 输出为空")
		
		# 根据阶段调用对应门禁检查
		if stage == WorkflowState.PLANNING:
			return self.gate.check_planning(output, self.enable_researcher)
		
		elif stage == WorkflowState.RESEARCHING:
			return self.gate.check_researching(output)
		
		elif stage == WorkflowState.WRITING:
			return self.gate.check_writing(output)
		
		elif stage == WorkflowState.FACT_CHECKING:
			retry_count = ctx.retry_counts.get(WorkflowState.WRITING, 0)
			return self.gate.check_fact_checking(output, retry_count)
		
		elif stage == WorkflowState.POLISHING:
			return self.gate.check_polishing(output)
		
		elif stage == WorkflowState.REVIEWING:
			writing_retry = ctx.retry_counts.get(WorkflowState.WRITING, 0)
			polishing_retry = ctx.retry_counts.get(WorkflowState.POLISHING, 0)
			return self.gate.check_reviewing(output, writing_retry, polishing_retry)
		
		else:
			return GateDecision.terminate(reason=f"未知阶段：{stage.value}")
	
	def _handle_decision(self, ctx: WorkflowContext, decision: GateDecision) -> None:
		"""根据门禁决策更新状态。
		
		Args:
			ctx: 工作流上下文
			decision: 门禁决策
		"""
		current_stage = ctx.current_state
		
		print(f"\n[门禁] {decision.reason}")
		
		if decision.pass_gate:
			# 通过 — 前进到下一状态
			print(f"[流转] {current_stage.value} → {decision.next_state.value}")
			ctx.current_state = decision.next_state
		
		else:
			# 未通过 — 退回或终止
			if decision.next_state == WorkflowState.FAILED:
				# 终止流程
				print(f"[终止] 流程失败")
				ctx.current_state = WorkflowState.FAILED
			
			else:
				# 退回重做
				target_state = decision.next_state
				
				# 检查是否还能重试
				if not ctx.can_retry(target_state):
					print(f"[警告] {target_state.value} 已达到最大重试次数，强制终止")
					ctx.current_state = WorkflowState.FAILED
					return
				
				# 记录退回
				ctx.record_retry(
					from_stage=current_stage,
					to_stage=target_state,
					reason=decision.reason,
				)
				
				print(f"[退回] {current_stage.value} → {target_state.value}（第 {ctx.retry_counts[target_state]} 次重试）")
				
				# 清除退回目标之后的所有输出（重新执行）
				self._clear_outputs_after(ctx, target_state)
				
				# 更新状态到退回目标
				ctx.current_state = target_state
	
	def _clear_outputs_after(self, ctx: WorkflowContext, target_state: WorkflowState) -> None:
		"""清除目标状态之后的所有输出（为重新执行做准备）。
		
		Args:
			ctx: 工作流上下文
			target_state: 退回目标状态
		"""
		# 状态顺序（根据是否启用 Researcher 动态调整）
		if self.enable_researcher:
			stages = [
				WorkflowState.PLANNING,
				WorkflowState.RESEARCHING,
				WorkflowState.WRITING,
				WorkflowState.FACT_CHECKING,
				WorkflowState.POLISHING,
				WorkflowState.REVIEWING,
			]
		else:
			stages = [
				WorkflowState.PLANNING,
				WorkflowState.WRITING,
				WorkflowState.FACT_CHECKING,
				WorkflowState.POLISHING,
				WorkflowState.REVIEWING,
			]
		
		# 找到目标状态的索引
		try:
			target_idx = stages.index(target_state)
		except ValueError:
			return
		
		# 清除目标状态及之后的输出
		for stage in stages[target_idx:]:
			if stage == WorkflowState.PLANNING:
				ctx.planner_output = None
			elif stage == WorkflowState.RESEARCHING:
				ctx.researcher_output = None
			elif stage == WorkflowState.WRITING:
				ctx.writer_output = None
			elif stage == WorkflowState.FACT_CHECKING:
				ctx.fact_checker_output = None
			elif stage == WorkflowState.POLISHING:
				ctx.polisher_output = None
			elif stage == WorkflowState.REVIEWING:
				ctx.reviewer_output = None
	
	def _save_stage_output(
		self, 
		ctx: WorkflowContext, 
		stage: WorkflowState, 
		input_data: dict[str, Any], 
		output_data: dict[str, Any]
	) -> None:
		"""保存阶段输入和输出到文件。
		
		Args:
			ctx: 工作流上下文
			stage: 阶段名称
			input_data: 输入数据
			output_data: 输出数据
		"""
		output_dir = self.output_dir / ctx.workflow_id
		output_dir.mkdir(parents=True, exist_ok=True)
		
		# 保存输入输出组合
		stage_data = {
			"input": input_data,
			"output": output_data,
		}
		
		output_file = output_dir / f"{stage.value}_output.json"
		with open(output_file, "w", encoding="utf-8") as f:
			json.dump(stage_data, f, indent=2, ensure_ascii=False)
	
	def _save_final_result(self, ctx: WorkflowContext) -> None:
		"""保存最终结果（文章 + 执行摘要）。
		
		Args:
			ctx: 工作流上下文
		"""
		output_dir = self.output_dir / ctx.workflow_id
		output_dir.mkdir(parents=True, exist_ok=True)
		
		# 保存工作流摘要
		summary_file = output_dir / "workflow_summary.json"
		with open(summary_file, "w", encoding="utf-8") as f:
			json.dump(ctx.to_summary(), f, indent=2, ensure_ascii=False)
		
		# 如果流程完成，生成最终文章
		if ctx.current_state == WorkflowState.COMPLETED:
			content = ctx.get_latest_content()
			if content:
				article_file = output_dir / "final_article.md"
				with open(article_file, "w", encoding="utf-8") as f:
					f.write(f"# {ctx.topic}\n\n")
					f.write(f"> 作者：AI 写作工作室\n")
					f.write(f"> 目标读者：{ctx.audience}\n")
					if ctx.reviewer_output:
						f.write(f"> 综合评分：{ctx.reviewer_output.get('overall_score', 'N/A')}\n")
					f.write(f"> 工作流 ID：{ctx.workflow_id}\n\n")
					f.write("---\n\n")
					f.write(content)
					f.write("\n\n---\n\n")
					f.write("## 执行信息\n\n")
					f.write(ctx.get_retry_summary() + "\n")
	
	def _print_summary(self, ctx: WorkflowContext) -> None:
		"""打印执行总结。
		
		Args:
			ctx: 工作流上下文
		"""
		print("\n" + "=" * 70)
		print("工作流执行完毕")
		print("=" * 70)
		print(f"最终状态: {ctx.current_state.value}")
		print(f"执行阶段数: {len(ctx.history)}")
		print(f"退回重做次数: {len(ctx.retry_records)}")
		
		if ctx.completed_at:
			duration = (ctx.completed_at - ctx.started_at).total_seconds()
			print(f"总耗时: {duration:.2f} 秒")
		
		print(f"\n{ctx.get_retry_summary()}")
		
		output_dir = self.output_dir / ctx.workflow_id
		print(f"\n输出目录: {output_dir}")
		print("=" * 70 + "\n")
