"""PolisherAgent — 润色编辑。

改善文章表达、节奏和可读性。
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field

from agents.write_studio.base import BaseRoleAgent, RoleMeta
from agents.write_studio.planner import AudienceAnalysis, CoreMessage, OutlineItem, WritingGuidelines
from inherit.llm.client import LLMClient
from inherit.prompt.prompt_manager import PromptManager


# ── 字符串枚举 ──────────────────────────────────────────

class ChangeType(StrEnum):
	"""修改类型"""

	LANGUAGE = "language"
	STRUCTURE = "structure"
	FORMATTING = "formatting"
	CONSISTENCY = "consistency"
	OTHER = "other"


# ── 嵌套模型 ──────────────────────────────────────────────

class PolisherChange(BaseModel):
	"""修改说明"""

	type: ChangeType = Field(description="修改类型")
	summary: str = Field(description="修改描述")
	examples: list[str] | None = Field(default=None, description="修改示例（可选）")


# ── 输出模型 ──────────────────────────────────────────────

class PolisherOutput(BaseModel):
	"""润色编辑输出"""

	content: str = Field(description="润色后的 Markdown 正文", min_length=100)
	changes: list[PolisherChange] = Field(description="主要修改说明")
	notes: str = Field(description="润色说明和建议")


# ── 输入模型 ──────────────────────────────────────────────

class PolisherInput(BaseModel):
	"""润色编辑输入"""

	topic: str = Field(description="文章主题")
	content: str = Field(description="待润色的文章内容")
	core_message: CoreMessage = Field(description="文章核心信息（保持核心论点不变）")
	audience_analysis: AudienceAnalysis = Field(description="目标读者分析（语言深度、术语粒度参考）")
	outline: list[OutlineItem] = Field(description="文章大纲（章节列表）")
	writing_guidelines: WritingGuidelines = Field(description="写作指导")


# ── 角色类 ────────────────────────────────────────────────

class PolisherAgent(BaseRoleAgent[PolisherInput, PolisherOutput]):
	"""润色编辑角色"""


	def __init__(self, llm: LLMClient, pm: PromptManager) -> None:
		super().__init__(llm, pm)


	@classmethod
	def meta(cls) -> RoleMeta:
		return RoleMeta(
			role_id="polisher",
			role_name="润色编辑",
			role_description="改善文章表达、节奏和可读性的专业编辑",
			quality_focus=[
				"语言表达是否流畅、准确",
				"段落节奏是否合理",
				"Markdown 排版是否清晰",
				"是否保留了原文的核心内容和观点",
				"可读性是否有实质性提升",
			],
		)


	@classmethod
	def input_model(cls) -> type[PolisherInput]:
		return PolisherInput


	@classmethod
	def output_model(cls) -> type[PolisherOutput]:
		return PolisherOutput


# ── Demo ─────────────────────────────────────────────────

if __name__ == "__main__":
	import json
	from pathlib import Path

	from agents.write_studio.planner import PlannerOutput
	from agents.write_studio.writer import WriterOutput
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
	agent: PolisherAgent = PolisherAgent(llm, pm)

	# 加载前序输出
	output_dir: Path = prj_root / "output"
	output_dir.mkdir(parents=True, exist_ok=True)
	planner_file: Path = output_dir / "planner_output.json"
	writer_file: Path = output_dir / "writer_output.json"
	if not planner_file.exists():
		raise FileNotFoundError(f"未找到策划输出 {planner_file}，请先运行 planner.py 生成大纲")

	if not writer_file.exists():
		raise FileNotFoundError(f"未找到写手输出 {writer_file}，请先运行 writer.py 生成文章")

	with open(planner_file, encoding="utf-8") as f:
		json_dict: dict = json.load(f)
		planner_output: PlannerOutput = PlannerOutput.model_validate(json_dict)
	print(f"从 {planner_file.name} 加载策划结果")

	with open(writer_file, encoding="utf-8") as f:
		json_dict: dict = json.load(f)
		writer_output: WriterOutput = WriterOutput.model_validate(json_dict)
	print(f"从 {writer_file.name} 加载文章内容")

	task: PolisherInput = PolisherInput(
		topic="AI 能否取代人类写作？",
		content=writer_output.content,
		core_message=planner_output.core_message,
		audience_analysis=planner_output.audience_analysis,
		outline=planner_output.outline,
		writing_guidelines=planner_output.writing_guidelines,
	)

	print(f"LLM: {llm.info()}")
	print(f"内容长度: {len(task.content)} 字符")
	print(f"正在执行润色编辑...\n")

	result: PolisherOutput = agent.run(task)

	print("=" * 60)
	print(result.model_dump_json(indent=2))
	print("=" * 60)

	# 保存到 output
	output_file: Path = output_dir / "polisher_output.json"
	output_file.write_text(result.model_dump_json(indent=2), encoding="utf-8")
	print(f"\n√ 输出已保存到 {output_file}")
