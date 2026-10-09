"""阶段输出质量评估器 — 实时评估各 Agent 的输出质量。

StageEvaluator 作为独立的轻量级评估工具，在每个阶段执行完成后被调用，
对该阶段的输出进行智能评估，生成质量评分、发现的问题和优点。
"""

import json
from typing import Any

from pydantic import BaseModel, Field

from inherit.llm.client import LLMClient
from inherit.prompt.prompt_manager import PromptManager
from inherit.utils.model_render import render_model_code


class StageEvaluationOutput(BaseModel):
	"""阶段评估输出格式。"""
	
	quality_score: int = Field(
		description="输出质量评分，1-10分，7分为及格线",
		ge=1,
		le=10,
	)
	
	issues: list[str] = Field(
		default_factory=list,
		description="发现的问题列表，每项简洁描述一个问题",
	)
	
	strengths: list[str] = Field(
		default_factory=list,
		description="优点/亮点列表，每项简洁描述一个优点",
	)
	
	summary: str = Field(
		description="评估摘要，1-2句话概括整体质量",
	)


class StageEvaluator:
	"""阶段输出质量评估器 - 实时评估各 Agent 的输出质量。
	
	职责：
	  1. 评估指定阶段的输出质量（完整性、准确性、规范性、可用性）
	  2. 生成质量评分（1-10分）
	  3. 识别存在的问题和亮点
	  4. 输出评估摘要
	
	使用场景：
	  - Orchestrator 在每个 Agent 执行完成后调用
	  - 评估结果写入 WorkflowContext 的 StageRecord
	  - 最终导出到 workflow_summary.json 供评估器分析
	"""
	
	def __init__(
		self,
		llm_client: LLMClient,
		prompt_manager: PromptManager,
	):
		"""初始化评估器。
		
		Args:
			llm_client: LLM 客户端
			prompt_manager: Prompt 管理器
		"""
		self.llm_client = llm_client
		self.prompt_manager = prompt_manager
	
	def evaluate(
		self, 
		stage_name: str,
		input_data: dict[str, Any],
		output_data: dict[str, Any],
	) -> dict[str, Any]:
		"""评估指定阶段的输出质量。
		
		Args:
			stage_name: 阶段名称（如 "planning", "writing", "fact_checking"）
			input_data: 该阶段的输入数据
			output_data: 该阶段的输出数据
		
		Returns:
			dict: 包含以下字段：
				- quality_score: int (1-10)
				- issues: list[str]
				- strengths: list[str]
				- summary: str
		
		Example:
			>>> evaluator = StageEvaluator(llm_client, prompt_manager)
			>>> result = evaluator.evaluate(
			...     stage_name="writing",
			...     input_data={"outline": {...}},
			...     output_data={"content": "...", "word_count": 1500},
			... )
			>>> result["quality_score"]
			8
			>>> result["issues"]
			["段落过长，建议拆分"]
			>>> result["strengths"]
			["论证充分", "语言流畅"]
		"""
		# 渲染 system prompt
		system_prompt = self.prompt_manager.render(
			"agents/write_studio/stage_evaluator/system.j2",
			output_schema=render_model_code(StageEvaluationOutput),
		)
		
		# 渲染 task prompt
		task_prompt = self.prompt_manager.render(
			"agents/write_studio/stage_evaluator/task.j2",
			stage_name=stage_name,
			input_data=input_data,
			output_data=output_data,
		)
		
		# 调用 LLM（使用 JSON 模式）
		response_text = self.llm_client.chat_with_json(
			messages=[
				{"role": "system", "content": system_prompt},
				{"role": "user", "content": task_prompt},
			],
		)
		
		# 解析结果
		result = StageEvaluationOutput.model_validate_json(response_text)
		
		return result.model_dump()
