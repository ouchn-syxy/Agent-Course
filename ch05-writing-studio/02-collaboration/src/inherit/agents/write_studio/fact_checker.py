"""FactCheckerAgent — 事实核查员。

检查文章中的事实、数据、术语和引用是否准确。
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field

from agents.write_studio.workflow.state import FactCheckVerdict
from inherit.agents.write_studio.base import BaseRoleAgent, RoleMeta
from inherit.agents.write_studio.planner import AudienceAnalysis, CoreMessage, OutlineItem
from inherit.llm.client import LLMClient
from inherit.prompt.prompt_manager import PromptManager


# ── 字符串枚举 ──────────────────────────────────────────

class IssueType(StrEnum):
	"""问题类型"""

	FACTUAL_ERROR = "factual_error"
	DATA_ISSUE = "data_issue"
	TERMINOLOGY = "terminology"
	LOGIC_FLAW = "logic_flaw"
	MISSING_SOURCE = "missing_source"


class Severity(StrEnum):
	"""单个问题严重程度"""

	CRITICAL = "critical"
	MAJOR = "major"
	MINOR = "minor"


# ── 嵌套模型 ──────────────────────────────────────────────

class Issue(BaseModel):
	"""核查发现的问题"""

	type: IssueType = Field(description="问题类型")
	location: str = Field(description="问题位置（章节或段落标识）")
	summary: str = Field(description="问题描述")
	suggestion: str = Field(description="修改建议")
	severity: Severity = Field(description="问题的严重程度")


# ── 输出模型 ──────────────────────────────────────────────

class FactCheckerOutput(BaseModel):
	"""事实核查员输出"""

	issues: list[Issue] = Field(description="发现的问题列表")
	overall_severity: Severity | None = Field(default=None, description="整体严重程度，无问题时为 null")
	summary: str = Field(description="核查总结")
	verdict: FactCheckVerdict = Field(description="核查结论：pass(通过) / pass_with_warnings(有警告但通过) / fail(失败)")


# ── 输入模型 ──────────────────────────────────────────────

class FactCheckerInput(BaseModel):
	"""事实核查员输入"""

	topic: str = Field(description="文章主题")
	content: str = Field(description="待核查的文章内容")
	core_message: CoreMessage = Field(description="文章核心信息（论证主线参考）")
	audience_analysis: AudienceAnalysis = Field(description="目标读者分析（术语深度、信息密度参考）")
	outline: list[OutlineItem] = Field(description="文章大纲（章节列表）")
	writer_notes: str | None = Field(default=None, description="作者提供的核查线索（数据来源、需要核查的地方、参考资料等）")


# ── 角色类 ────────────────────────────────────────────────

class FactCheckerAgent(BaseRoleAgent[FactCheckerInput, FactCheckerOutput]):
	"""事实核查员角色"""


	def __init__(self, llm: LLMClient, pm: PromptManager) -> None:
		super().__init__(llm, pm)


	@classmethod
	def meta(cls) -> RoleMeta:
		return RoleMeta(
			role_id="fact_checker",
			role_name="事实核查员",
			role_description="检查文章中的事实、数据、术语和引用是否准确的专业审核员",
			quality_focus=[
				"是否发现了明显的事实错误",
				"数据和引用是否可信",
				"术语使用是否准确",
				"是否存在逻辑矛盾",
				"修改建议是否具体可行",
			],
		)


	@classmethod
	def input_model(cls) -> type[FactCheckerInput]:
		return FactCheckerInput


	@classmethod
	def output_model(cls) -> type[FactCheckerOutput]:
		return FactCheckerOutput


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
	agent: FactCheckerAgent = FactCheckerAgent(llm, pm)

	# 尝试加载前序输出
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
	print(f"从 {writer_file.name} 加载策划结果")

	task: FactCheckerInput = FactCheckerInput(
		topic="AI 能否取代人类写作？",
		content=writer_output.content,
		core_message=planner_output.core_message,
		audience_analysis=planner_output.audience_analysis,
		outline=planner_output.outline,
		writer_notes=writer_output.notes,
	)

	print(f"LLM: {llm.info()}")
	print(f"主题: {task.topic}")
	print(f"待核查长度: {len(task.content)} 字符")
	print(f"正在执行事实核查...\n")

	result: FactCheckerOutput = agent.run(task)

	print("=" * 60)
	print(result.model_dump_json(indent=2))
	print("=" * 60)

	# 保存到 output
	output_file: Path = output_dir / "fact_checker_output.json"
	output_file.write_text(result.model_dump_json(indent=2), encoding="utf-8")
	print(f"\n√ 输出已保存到 {output_file}")
