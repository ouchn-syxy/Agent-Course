"""PlannerAgent — 策划编辑。

负责选题分析、读者定位和文章大纲设计。
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from agents.write_studio.base import BaseRoleAgent, RoleMeta
from inherit.llm.client import LLMClient
from inherit.prompt.prompt_manager import PromptManager


# ── 嵌套模型 ──────────────────────────────────────────────

class AudienceAnalysis(BaseModel):
	"""目标读者分析"""

	profile: str = Field(description="读者画像（背景、技能水平、关注点）")
	needs: list[str] = Field(description="读者的核心需求", min_length=1)
	pain_points: list[str] = Field(description="读者的痛点或困惑", min_length=1)


class CoreMessage(BaseModel):
	"""文章核心信息"""

	angle: str = Field(description="文章的独特角度或切入点")
	thesis: str = Field(description="核心论点")
	takeaways: list[str] = Field(description="读者应获得的关键收获", min_length=2, max_length=5)


class OutlineItem(BaseModel):
	"""大纲章节项"""

	title: str = Field(description="章节标题")
	objective: str = Field(description="本节的写作目标")
	key_points: list[str] = Field(description="本节应包含的要点")
	notes: str | None = Field(default=None, description="给作者的特别说明（可选）")


class WritingGuidelines(BaseModel):
	"""写作指导"""

	dos: list[str] = Field(description="应该做的事")
	donts: list[str] = Field(description="应该避免的事")
	examples: list[str] = Field(description="建议使用的示例方向")


# ── 输出模型 ──────────────────────────────────────────────

class PlannerOutput(BaseModel):
	"""策划编辑输出"""

	audience_analysis: AudienceAnalysis = Field(description="目标读者分析")
	core_message: CoreMessage = Field(description="文章核心信息")
	outline: list[OutlineItem] = Field(description="文章大纲", min_length=3)
	writing_guidelines: WritingGuidelines = Field(description="写作指导")


# ── 输入模型 ──────────────────────────────────────────────

class PlannerInput(BaseModel):
	"""策划编辑输入"""

	topic: str = Field(description="文章主题")
	audience: str = Field(description="目标读者")
	goal: str = Field(description="写作目标")
	word_count: str | None = Field(default=None, description="字数要求")
	tone: str | None = Field(default=None, description="语气风格")
	requirements: list[str] | None = Field(default=None, description="必须包含的内容")
	constraints: list[str] | None = Field(default=None, description="应该避免的内容")


# ── 角色类 ────────────────────────────────────────────────

class PlannerAgent(BaseRoleAgent[PlannerInput, PlannerOutput]):
	"""策划编辑角色"""


	def __init__(self, llm: LLMClient, pm: PromptManager) -> None:
		super().__init__(llm, pm)


	@classmethod
	def meta(cls) -> RoleMeta:
		return RoleMeta(
			role_id="planner",
			role_name="策划编辑",
			role_description="负责选题分析、读者定位和文章大纲设计的资深编辑",
			quality_focus=[
				"选题是否清晰且有价值",
				"读者画像是否明确",
				"大纲是否有逻辑层次",
				"每节是否有明确写作目标",
				"内容范围是否适度，不过于宽泛或狭窄",
			],
		)


	@classmethod
	def input_model(cls) -> type[PlannerInput]:
		return PlannerInput


	@classmethod
	def output_model(cls) -> type[PlannerOutput]:
		return PlannerOutput


# ── Demo ─────────────────────────────────────────────────

if __name__ == "__main__":
	from pathlib import Path

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
	agent: PlannerAgent = PlannerAgent(llm, pm)

	# 构造任务
	task: PlannerInput = PlannerInput(
		topic="AI 能否取代人类写作？",
		audience="中文内容创作者（自媒体、文案、编辑）",
		goal="帮助读者理解 AI 写作的边界，消除焦虑，提供实用的人机协作思路",
		word_count="2000-3000",
		tone="理性、客观、不贩卖焦虑",
		requirements=["AI 写作工具现状", "AI 的局限性（创造力、情感、文化理解）", "人机协作的最佳实践"],
	)

	print(f"LLM: {llm.info()}")
	print(f"主题: {task.topic}")
	print(f"正在执行策划编辑...\n")

	result: PlannerOutput = agent.run(task)

	print("=" * 60)
	print(result.model_dump_json(indent=2))
	print("=" * 60)

	# 保存到 output
	output_dir: Path = prj_root / "output"
	output_dir.mkdir(parents=True, exist_ok=True)
	output_file: Path = output_dir / "planner_output.json"
	output_file.write_text(result.model_dump_json(indent=2), encoding="utf-8")
	print(f"\n√ 输出已保存到 {output_file}")
