"""WriterAgent — 内容作者。

根据大纲撰写 Markdown 格式的文章初稿。
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from inherit.agents.write_studio.base import BaseRoleAgent, RoleMeta
from inherit.agents.write_studio.planner import AudienceAnalysis, CoreMessage, OutlineItem, WritingGuidelines
from inherit.llm.client import LLMClient
from inherit.prompt.prompt_manager import PromptManager


# ── 输出模型 ──────────────────────────────────────────────

class WriterOutput(BaseModel):
	"""内容作者输出"""

	content: str = Field(description="Markdown 格式的完整文章正文", min_length=100)
	notes: str = Field(description="写作说明（数据来源、需要核查的地方、参考资料等）")


# ── 输入模型 ──────────────────────────────────────────────

class WriterInput(BaseModel):
	"""内容作者输入"""

	topic: str = Field(description="文章主题")
	word_count: str | None = Field(default=None, description="字数要求")
	tone: str | None = Field(default=None, description="语气风格")

	audience_analysis: AudienceAnalysis = Field(description="目标读者分析")
	core_message: CoreMessage = Field(description="文章核心信息")
	outline: list[OutlineItem] = Field(description="文章大纲（章节列表）")
	writing_guidelines: WritingGuidelines = Field(description="写作指导")


# ── 角色类 ────────────────────────────────────────────────

class WriterAgent(BaseRoleAgent[WriterInput, WriterOutput]):
	"""内容作者角色"""


	def __init__(self, llm: LLMClient, pm: PromptManager) -> None:
		super().__init__(llm, pm)


	@classmethod
	def meta(cls) -> RoleMeta:
		return RoleMeta(
			role_id="writer",
			role_name="内容作者",
			role_description="根据大纲撰写文章初稿的专业写作者",
			quality_focus=[
				"是否严格按照大纲撰写",
				"内容是否准确、逻辑清晰",
				"是否提供了具体示例和数据支撑",
				"语言风格是否符合要求",
				"段落结构是否合理，可读性如何",
			],
		)


	@classmethod
	def input_model(cls) -> type[WriterInput]:
		return WriterInput


	@classmethod
	def output_model(cls) -> type[WriterOutput]:
		return WriterOutput


# ── Demo ─────────────────────────────────────────────────

if __name__ == "__main__":
	import json
	from pathlib import Path

	from agents.write_studio.planner import PlannerOutput
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
	agent: WriterAgent = WriterAgent(llm, pm)

	# 尝试加载 planner 输出
	output_dir: Path = prj_root / "output"
	output_dir.mkdir(parents=True, exist_ok=True)
	planner_file: Path = output_dir / "planner_output.json"

	if not planner_file.exists():
		raise FileNotFoundError(f"未找到策划输出 {planner_file}，请先运行 planner.py 生成大纲")

	with open(planner_file, encoding="utf-8") as f:
		json_dict: dict = json.load(f)
		planner_output: PlannerOutput = PlannerOutput.model_validate(json_dict)
	print(f"从 {planner_file.name} 加载策划结果")

	task: WriterInput = WriterInput(
		topic="AI 能否取代人类写作？",
		word_count="2000-3000",
		tone="理性、客观、不贩卖焦虑",
		audience_analysis=planner_output.audience_analysis,
		core_message=planner_output.core_message,
		outline=planner_output.outline,
		writing_guidelines=planner_output.writing_guidelines,
	)

	print(f"LLM: {llm.info()}")
	print(f"主题: {task.topic}")
	print(f"章节数: {len(task.outline)}")
	print(f"正在执行内容撰写...\n")

	result: WriterOutput = agent.run(task)

	print("=" * 60)
	print(result.model_dump_json(indent=2))
	print("=" * 60)

	# 保存到 output（附加 topic 便于下游使用）
	output_file: Path = output_dir / "writer_output.json"
	output_file.write_text(result.model_dump_json(indent=2), encoding="utf-8")
	print(f"\n√ 输出已保存到 {output_file}")
