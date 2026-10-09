"""TripPlanVerifier — 行程方案验证模块。

调用 LLM 检查生成的行程方案是否存在逻辑问题：
时间冲突、地理一致性、预算合理性、逻辑完整性。

验证不通过时返回具体问题列表和改进建议，供 TripAgent 重新规划。
"""

from __future__ import annotations

from enum import StrEnum

from openai.types.chat import (
	ChatCompletionMessageParam,
	ChatCompletionSystemMessageParam,
	ChatCompletionUserMessageParam,
)
from pydantic import BaseModel, Field

from inherit.llm.client import LLMClient
from inherit.prompt.prompt_manager import PromptManager
from inherit.utils.model_render import render_model_code


# ============================================================
# 数据模型
# ============================================================

class Severity(StrEnum):
	"""问题严重程度。"""
	CRITICAL = "critical"
	MAJOR = "major"
	MINOR = "minor"


class VerifyIssue(BaseModel):
	"""单个验证问题。"""
	dimension: str = Field(description="问题所属维度")
	severity: Severity = Field(description="严重程度")
	description: str = Field(description="具体问题描述")


class VerifyResult(BaseModel):
	"""验证结果。"""
	is_valid: bool = Field(description="行程方案是否通过验证")
	issues: list[VerifyIssue] = Field(default_factory=list, description="发现的问题列表")
	suggestions: list[str] = Field(default_factory=list, description="改进建议")
	reasoning: str = Field(default="", description="审核推理过程")


	def has_critical_or_major(self) -> bool:
		"""是否包含 critical 或 major 级别的问题（需要修复）。"""
		return any(i.severity in (Severity.CRITICAL, Severity.MAJOR) for i in self.issues)


# ============================================================
# TripPlanVerifier
# ============================================================

class TripPlanVerifier:
	"""行程方案验证器 — 调用 LLM 检查行程方案的合理性。

	用法：
		verifier = TripPlanVerifier(llm, pm)
		result = verifier.verify(requirements, plan_text)
	"""


	def __init__(self, llm: LLMClient, pm: PromptManager) -> None:
		self._llm: LLMClient = llm
		self._pm: PromptManager = pm


	def verify(self, requirements: str, plan_text: str) -> VerifyResult:
		"""验证行程方案。

		:param requirements: 用户原始需求文本
		:param plan_text:    已生成的 Markdown 行程方案
		:return:             VerifyResult
		"""
		system_prompt: str = self._pm.render(
			"agents/trip_planning/plan_verifier/system.j2",
			verify_result_schema=render_model_code(VerifyResult),
		)
		user_prompt: str = self._pm.render(
			"agents/trip_planning/plan_verifier/verify.j2",
			requirements=requirements,
			plan_text=plan_text,
		)

		messages: list[ChatCompletionMessageParam] = [
			ChatCompletionSystemMessageParam(role="system", content=system_prompt),
			ChatCompletionUserMessageParam(role="user", content=user_prompt),
		]

		json_text: str = self._llm.chat_with_json(messages, temperature=0.2)
		return VerifyResult.model_validate_json(json_text)


# ============================================================
# 演示
# ============================================================

if __name__ == "__main__":
	from config import Config
	from inherit.utils.path import get_prj_root

	cfg: Config = Config.from_yaml()

	llm: LLMClient = LLMClient(
		api_key=cfg.llm.api_key_env,
		base_url=cfg.llm.base_url,
		model=cfg.llm.model,
		temperature=cfg.generation.temperature,
		top_p=cfg.generation.top_p,
		max_tokens=cfg.generation.max_tokens,
	)
	pm: PromptManager = PromptManager(get_prj_root() / "prompts")

	verifier: TripPlanVerifier = TripPlanVerifier(llm=llm, pm=pm)

	# ── 测试用例 1：正常行程方案（预期通过） ──
	requirements_1: str = "2 天北京亲子游，预算 3000 元"
	plan_1: str = """
### 第一天
- 上午：故宫博物院（09:00-12:00），门票 60 元/人
- 午餐：故宫附近老北京炸酱面，约 40 元/人
- 下午：天安门广场 + 国家博物馆（13:00-16:00），免费
- 晚上：前门大街逛吃，约 80 元/人
- 住宿：经济型酒店，250 元/晚
	
### 第二天
- 上午：颐和园（09:00-12:00），门票 30 元/人
- 午餐：颐和园附近餐厅，约 50 元/人
- 下午：圆明园（13:30-16:00），门票 25 元/人
- 返程
"""

	print("=== 测试 1：合理行程 ===")
	result_1: VerifyResult = verifier.verify(requirements_1, plan_1)
	print(f"is_valid: {result_1.is_valid}")
	print(f"reasoning: {result_1.reasoning}")
	for issue in result_1.issues:
		print(f"  [{issue.severity}] {issue.dimension}: {issue.description}")
	for s in result_1.suggestions:
		print(f"  建议: {s}")
	print()

	# ── 测试用例 2：有问题行程（时间冲突 + 预算超支） ──
	requirements_2: str = "1 天上海精华游，预算 500 元"
	plan_2: str = """
### 第一天
- 上午：外滩（09:00-10:00），免费
- 上午：东方明珠（09:30-11:30），门票 200 元/人
- 下午：迪士尼乐园（12:00-22:00），门票 500 元/人
- 午餐：园区内随意解决
"""

	print("=== 测试 2：问题行程 ===")
	result_2: VerifyResult = verifier.verify(requirements_2, plan_2)
	print(f"is_valid: {result_2.is_valid}")
	print(f"reasoning: {result_2.reasoning}")
	for issue in result_2.issues:
		print(f"  [{issue.severity}] {issue.dimension}: {issue.description}")
	for s in result_2.suggestions:
		print(f"  建议: {s}")
	print()

	# ── 测试用例 3：空方案（预期发现问题） ──
	requirements_3: str = "3 天杭州自由行"
	plan_3: str = """
### 第一天
- 上午：西湖
- 下午：灵隐寺
"""

	print("=== 测试 3：不完整方案 ===")
	result_3: VerifyResult = verifier.verify(requirements_3, plan_3)
	print(f"is_valid: {result_3.is_valid}")
	print(f"reasoning: {result_3.reasoning}")
	for issue in result_3.issues:
		print(f"  [{issue.severity}] {issue.dimension}: {issue.description}")
	for s in result_3.suggestions:
		print(f"  建议: {s}")
