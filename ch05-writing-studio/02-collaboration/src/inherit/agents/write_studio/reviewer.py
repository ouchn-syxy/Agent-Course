"""ReviewerAgent — 审稿主编。

对文章进行终审，决定是否通过发布。
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field

from agents.write_studio.workflow.state import ReviewDecision
from inherit.agents.write_studio.base import BaseRoleAgent, RoleMeta
from inherit.llm.client import LLMClient
from inherit.prompt.prompt_manager import PromptManager


# ── 嵌套模型 ──────────────────────────────────────────────

class DimensionScores(BaseModel):
	"""各维度评分"""

	logic: float = Field(description="逻辑性评分", ge=1, le=5)
	accuracy: float = Field(description="准确性评分", ge=1, le=5)
	readability: float = Field(description="可读性评分", ge=1, le=5)
	completeness: float = Field(description="完整性评分", ge=1, le=5)


# ── 输出模型 ──────────────────────────────────────────────

class ReviewerOutput(BaseModel):
	"""审稿主编输出"""

	decision: ReviewDecision = Field(description="审稿决策：approve(通过) / revise_polish(退回润色) / revise_write(退回重写) / reject(拒绝)")
	overall_score: float = Field(description="综合评分", ge=1, le=5)
	dimension_scores: DimensionScores = Field(description="各维度评分")
	strengths: list[str] = Field(description="文章优点")
	issues: list[str] = Field(description="存在的问题")
	suggestions: list[str] = Field(description="改进建议")
	summary: str = Field(description="审稿总结")


# ── 输入模型 ──────────────────────────────────────────────

class ReviewerInput(BaseModel):
	"""审稿主编输入 — 使用用户的原始需求，独立于 Planner 策划结果"""

	topic: str = Field(description="文章主题")
	audience: str = Field(description="目标读者")
	goal: str = Field(description="写作目标")
	word_count: str | None = Field(default=None, description="字数要求")
	tone: str | None = Field(default=None, description="语气风格")
	requirements: list[str] | None = Field(default=None, description="必须包含的内容")
	constraints: list[str] | None = Field(default=None, description="应该避免的内容")
	content: str = Field(description="待审阅的文章内容")


# ── 角色类 ────────────────────────────────────────────────

class ReviewerAgent(BaseRoleAgent[ReviewerInput, ReviewerOutput]):
	"""审稿主编角色"""


	def __init__(self, llm: LLMClient, pm: PromptManager) -> None:
		super().__init__(llm, pm)


	@classmethod
	def meta(cls) -> RoleMeta:
		return RoleMeta(
			role_id="reviewer",
			role_name="审稿主编",
			role_description="对文章进行终审，决定是否通过发布的资深编辑",
			quality_focus=[
				"文章是否完整回答了主题",
				"质量是否达到发布标准",
				"是否存在严重缺陷",
				"改进意见是否明确、可执行",
				"决策是否合理",
			],
		)


	@classmethod
	def input_model(cls) -> type[ReviewerInput]:
		return ReviewerInput


	@classmethod
	def output_model(cls) -> type[ReviewerOutput]:
		return ReviewerOutput


# ── Demo ─────────────────────────────────────────────────

if __name__ == "__main__":
	import json
	from pathlib import Path

	from agents.write_studio.polisher import PolisherOutput
	from config import Config
	from inherit.utils.path import get_prj_root

	prj_root: Path = get_prj_root()

	# 加载配置
	cfg: Config = Config.from_yaml()

	# 初始化 LLM & PromptManager
	llm: LLMClient = LLMClient(
		api_key=cfg.llm.api_key_env,
		base_url=cfg.llm.base_url,
		model=cfg.llm.model,
		temperature=cfg.generation.temperature,
		top_p=cfg.generation.top_p,
		max_tokens=cfg.generation.max_tokens,
	)
	pm: PromptManager = PromptManager(prj_root / "prompts")
	agent: ReviewerAgent = ReviewerAgent(llm, pm)

	# 加载前序输出
	output_dir: Path = prj_root / "output"
	output_dir.mkdir(parents=True, exist_ok=True)
	polisher_file: Path = output_dir / "polisher_output.json"

	if not polisher_file.exists():
		raise FileNotFoundError(f"未找到润色输出 {polisher_file}，请先运行 polisher.py 生成润色文章")

	with open(polisher_file, encoding="utf-8") as f:
		json_dict: dict = json.load(f)
		polisher_output: PolisherOutput = PolisherOutput.model_validate(json_dict)
	print(f"从 {polisher_file.name} 加载润色文章")

	task: ReviewerInput = ReviewerInput(
		topic="AI 能否取代人类写作？",
		audience="中文内容创作者（自媒体、文案、编辑）",
		goal="帮助读者理解 AI 写作的边界，消除焦虑，提供实用的人机协作思路",
		word_count="2000-3000",
		tone="理性、客观、不贩卖焦虑",
		requirements=["AI 写作工具现状", "AI 的局限性（创造力、情感、文化理解）", "人机协作的最佳实践"],
		content=polisher_output.content,
	)

	print(f"LLM: {llm.info()}")
	print(f"主题: {task.topic}")
	print(f"内容长度: {len(task.content)} 字符")
	print(f"正在执行终审...\n")

	result: ReviewerOutput = agent.run(task)

	print("=" * 60)
	print(result.model_dump_json(indent=2))
	print("=" * 60)

	# 保存到 output
	output_file: Path = output_dir / "reviewer_output.json"
	output_file.write_text(result.model_dump_json(indent=2), encoding="utf-8")
	print(f"\n√ 输出已保存到 {output_file}")
