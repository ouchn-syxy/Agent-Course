"""写作工作室角色抽象基类。

所有写作角色（Planner / Writer / FactChecker / Polisher / Reviewer）
继承此基类，声明各自的 Input/Output Pydantic 模型，基类的 run() 模板方法
自动完成：Prompt 渲染 → LLM 调用 → JSON 解析 → 模型校验 → 返回强类型结果。
"""

from __future__ import annotations

import json
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Generic, TypeVar

from openai.types.chat import ChatCompletionMessageParam, ChatCompletionSystemMessageParam, \
	ChatCompletionUserMessageParam
from pydantic import BaseModel

from inherit.llm.client import LLMClient
from inherit.prompt.prompt_manager import PromptManager
from inherit.utils.model_render import render_model_code

# ── 泛型变量 ──────────────────────────────────────────────

TInput = TypeVar("TInput", bound=BaseModel)
TOutput = TypeVar("TOutput", bound=BaseModel)


# ── 自定义异常 ────────────────────────────────────────────

class RoleAgentError(Exception):
	"""角色代理基础异常。"""
	pass


class PromptRenderError(RoleAgentError):
	"""Prompt 渲染异常。"""
	pass


class LLMCallError(RoleAgentError):
	"""LLM 调用异常。"""
	pass


class OutputParseError(RoleAgentError):
	"""输出 JSON 解析异常。"""
	pass


class OutputValidationError(RoleAgentError):
	"""输出 Pydantic 校验异常。"""
	pass


# ── 角色元信息 ──────────────────────────────────────────

@dataclass(frozen=True)
class RoleMeta:
	"""角色静态元信息，每个子类通过 meta 属性返回一份实例。"""

	role_id: str
	"""角色唯一标识（如 planner），对应 prompts/agents/write_studio/{role_id}/ 目录。"""
	role_name: str
	"""角色中文名称（如 策划编辑）。"""
	role_description: str
	"""角色职责一句话描述。"""
	quality_focus: list[str]
	"""质量关注点列表。"""


# ── 抽象基类 ──────────────────────────────────────────────

class BaseRoleAgent(ABC, Generic[TInput, TOutput]):
	"""写作工作室角色抽象基类。

	泛型参数:
		TInput:  输入 Pydantic 模型（由子类的 input_model 属性指定）
		TOutput: 输出 Pydantic 模型（由子类的 output_model 属性指定）

	每个子类只需声明 role_id / role_name / role_description / input_model / output_model /
	quality_focus，基类的 run() 模板方法自动完成全流程。
	"""


	def __init__(self, llm: LLMClient, pm: PromptManager) -> None:
		self._llm: LLMClient = llm
		self._pm: PromptManager = pm


	# ── 子类必须实现 ──────────────────────────────────────────

	@classmethod
	@abstractmethod
	def meta(cls) -> RoleMeta:
		"""角色静态元信息。"""
		...


	@classmethod
	@abstractmethod
	def input_model(cls) -> type[TInput]:
		"""输入 Pydantic 模型类。"""
		...


	@classmethod
	@abstractmethod
	def output_model(cls) -> type[TOutput]:
		"""输出 Pydantic 模型类。"""
		...


	# ── 核心执行方法 ──────────────────────────────────────────

	def run(self, task: TInput) -> TOutput:
		"""执行角色任务（模板方法）。

		Args:
			task: TInput 类型的 Pydantic 输入模型实例

		Returns:
			TOutput 类型的 Pydantic 输出模型实例

		Raises:
			PromptRenderError:    Prompt 模板渲染失败
			LLMCallError:         LLM 调用失败
			OutputParseError:     LLM 返回的 JSON 无法解析
			OutputValidationError: 输出未通过 Pydantic 模型校验
		"""
		# 1. 渲染 system / user prompt
		try:
			system_prompt: str = self._pm.render(
				f"agents/write_studio/{self.meta().role_id}/system.j2",
				output_schema=render_model_code(self.output_model()),
			)
			user_prompt: str = self._pm.render(
				f"agents/write_studio/{self.meta().role_id}/task.j2",
				**task.model_dump(),
			)
		except Exception as e:
			raise PromptRenderError(f"Prompt 渲染失败：{e}") from e

		# 2. 调用 LLM
		messages: list[ChatCompletionMessageParam] = [
			ChatCompletionSystemMessageParam(role="system", content=system_prompt),
			ChatCompletionUserMessageParam(role="user", content=user_prompt),
		]

		try:
			output_text = self._llm.chat_with_json(messages)
		except Exception as e:
			raise LLMCallError(f"LLM 调用失败：{e}") from e

		# 3. JSON 解析
		try:
			# 使用 strict=False 允许控制字符（如未转义的换行符）
			raw_dict = json.loads(output_text, strict=False)
		except json.JSONDecodeError as e:
			raise OutputParseError(f"JSON 解析失败：{e}") from e

		# 4. Pydantic 校验
		try:
			return self.output_model().model_validate(raw_dict)
		except Exception as e:
			raise OutputValidationError(f"输出未通过模型校验：{e}") from e
