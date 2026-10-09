"""实验13：写作工作室角色分工设计 — CLI 入口。

支持 6 种运行模式：
  --list-roles          列出所有可用角色
  --show-role ROLE_ID   查看指定角色的详情
  --run-role  ROLE_ID   执行指定角色（按依赖链自动加载前序输出）
  --workflow            生成协作流程图（Mermaid）
  --pipeline            一键运行完整流水线（需 --topic）

角色依赖链（前序 → 后续）：
  planner → writer → fact_checker → polisher → reviewer
"""

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from pydantic import BaseModel

# ── 写作工作室角色 ──
from agents.write_studio.base import BaseRoleAgent, RoleMeta
from agents.write_studio.fact_checker import FactCheckerAgent, FactCheckerInput
from agents.write_studio.planner import PlannerAgent, PlannerInput, PlannerOutput
from agents.write_studio.polisher import PolisherAgent, PolisherInput, PolisherOutput
from agents.write_studio.reviewer import ReviewerAgent, ReviewerInput
from agents.write_studio.writer import WriterAgent, WriterInput, WriterOutput
# ── 基础设施 ──
from config import Config
from inherit.llm.client import LLMClient
from inherit.prompt.prompt_manager import PromptManager
from inherit.utils.path import get_prj_root


def cmd_list_roles() -> None:
	"""列出所有可用角色（从注册的 5 个 Agent 类中提取元信息打印）。"""
	print("\n=== 写作工作室角色列表 ===\n")
	agents: list[type[BaseRoleAgent]] = [PlannerAgent, WriterAgent, FactCheckerAgent, PolisherAgent, ReviewerAgent]
	for agent in agents:
		print(f"• {agent.meta().role_id:15s} | {agent.meta().role_name:10s} | {agent.meta().role_description}")
	print(f"\n共 {len(agents)} 个角色\n")


def cmd_show_role(agent: BaseRoleAgent) -> None:
	"""查看角色详情。

	Args:
		agent: 已初始化的角色实例，通过 meta() / input_model() / output_model() 获取信息
	"""

	print(f"\n=== 角色详情：{agent.meta().role_name} ===\n")
	print(f"ID: {agent.meta().role_id}")
	print(f"名称: {agent.meta().role_name}")
	print(f"职责: {agent.meta().role_description}")
	print(f"\n输入约束:")
	fields: Any = agent.input_model().model_fields
	required: list[str] = [n for n, f in fields.items() if f.is_required()]
	optional: list[str] = [n for n, f in fields.items() if not f.is_required()]
	print(f"  必需: {', '.join(required) or '无'}")
	print(f"  可选: {', '.join(optional) or '无'}")
	print(f"\n输出模型: {agent.output_model().__name__}")
	print(f"\n质量关注点:")
	for i, focus in enumerate(agent.meta().quality_focus, 1):
		print(f"  {i}. {focus}")

	print()


def cmd_workflow(output_dir: Path) -> None:
	"""生成协作流程图（Mermaid 格式）并写入 output_dir/workflow.md。

	流程概览：
	  开始 → 策划编辑（大纲设计）→ 内容作者（初稿）
	       → 事实核查员（验证）→ 润色编辑（优化）→ 审稿主编（终审）→ 发布

	回退路径：
	  - 事实核查发现严重问题 → 退回作者重写
	  - 审稿不通过 → 退回润色或重写

	Args:
		output_dir: 输出目录，workflow.md 将写入此目录
	"""

	mermaid_lines: list[str] = []
	# ── 图声明 ──
	mermaid_lines.append("```mermaid")
	mermaid_lines.append("graph TD")

	# ── 正向流程节点 ──
	mermaid_lines.append("    Start[开始：写作需求] --> Planner[策划编辑<br/>选题分析 + 大纲设计]")
	mermaid_lines.append("    Planner --> Writer[内容作者<br/>撰写初稿]")
	mermaid_lines.append("    Writer --> FactChecker[事实核查员<br/>验证准确性]")
	mermaid_lines.append("")

	# ── 核查分支：通过 / 回退 ──
	mermaid_lines.append("    FactChecker -->|发现严重问题| Writer")
	mermaid_lines.append("    FactChecker -->|通过核查| Polisher[润色编辑<br/>优化表达]")
	mermaid_lines.append("")

	# ── 终审分支：通过 / 退回润色 / 退回重写 ──
	mermaid_lines.append("    Polisher --> Reviewer[审稿主编<br/>终审质量]")
	mermaid_lines.append("")
	mermaid_lines.append("    Reviewer -->|需重写| Writer")
	mermaid_lines.append("    Reviewer -->|需润色| Polisher")
	mermaid_lines.append("    Reviewer -->|通过| End[发布文章]")
	mermaid_lines.append("")

	# ── 节点配色 ──
	mermaid_lines.append("    style Start fill:#e1f5e1")
	mermaid_lines.append("    style End fill:#e1f5e1")
	mermaid_lines.append("    style Planner fill:#fff4e1")
	mermaid_lines.append("    style Writer fill:#ffe1e1")
	mermaid_lines.append("    style FactChecker fill:#e1f0ff")
	mermaid_lines.append("    style Polisher fill:#f0e1ff")
	mermaid_lines.append("    style Reviewer fill:#ffe1f0")
	mermaid_lines.append("```")
	mermaid: str = "\n".join(mermaid_lines)

	print("\n=== 生成协作流程图 ===\n")

	# ── 角色概览（控制台打印 + 写入文件）──
	lines: list[str] = []
	lines.append("# 写作工作室协作流程")
	lines.append("")
	lines.append("## 角色概览")
	lines.append("")

	print("角色概览：")
	for agent in [PlannerAgent, WriterAgent, FactCheckerAgent, PolisherAgent, ReviewerAgent]:
		meta: RoleMeta = agent.meta()

		print(f"  • {meta.role_name}（{meta.role_id}）— {meta.role_description}")

		lines.append(f"### {meta.role_name}（`{meta.role_id}`）")
		lines.append("")
		lines.append(f"**职责**: {meta.role_description}")
		lines.append("")
		lines.append("**质量关注点**:")
		for focus in meta.quality_focus:
			lines.append(f"- {focus}")
		lines.append("")

		input_fields: Any = agent.input_model().model_fields
		required: list[str] = [n for n, f in input_fields.items() if f.is_required()]
		optional: list[str] = [n for n, f in input_fields.items() if not f.is_required()]
		input_desc: str = ", ".join(required)
		if optional:
			input_desc += f"（可选: {', '.join(optional)}）"
		lines.append(f"**输入**: {input_desc}")
		lines.append(f"**输出**: {agent.output_model().__name__}")
		lines.append("")

	print()

	# ── 协作流程图 ──
	print("协作流程图：")
	lines.append("## 协作流程图")
	lines.append("")
	lines.append(mermaid)
	lines.append("")
	print(mermaid)
	print()

	# ── 数据流（各阶段输入 → 输出）──
	print("数据流：")
	lines.append("## 数据流")
	lines.append("")
	flow_items = [
		"**策划阶段**: 主题 + 读者 + 目标 → 大纲 + 写作指南",
		"**创作阶段**: 大纲 + 指南 → Markdown 初稿",
		"**核查阶段**: 初稿 → 问题列表 + 修改建议",
		"**润色阶段**: 初稿 + 核查报告 → 润色后文稿",
		"**审核阶段**: 润色稿 → 审核决策（通过 / 修改 / 重写）",
	]
	for i, item in enumerate(flow_items, 1):
		print(f"  {i}. {item}")
		lines.append(f"{i}. {item}")
	print()

	# 写入文件
	output_dir.mkdir(parents=True, exist_ok=True)
	output_file: Path = output_dir / "workflow.md"
	output_file.write_text("\n".join(lines) + "\n", encoding="utf-8")
	print(f"✓ 工作流程图已保存到：{output_file}")


def cmd_pipeline(
		topic: str,
		audience: str,
		goal: str,
		words: str,
		tone: str,
		requirements: list[str] | None,
		constraints: list[str] | None,
		planner: PlannerAgent,
		writer: WriterAgent,
		fact_checker: FactCheckerAgent,
		polisher: PolisherAgent,
		reviewer: ReviewerAgent,
		output_dir: Path,
) -> None:
	"""一键运行完整写作流水线（planner → writer → fact_checker → polisher → reviewer）。

	Args:
		topic: 文章主题
		audience: 目标读者描述
		goal: 写作目标
		words: 字数要求
		tone: 语气风格
		requirements: 必须包含的内容列表
		constraints: 应该避免的内容列表
		planner: PlannerAgent 实例
		writer: WriterAgent 实例
		fact_checker: FactCheckerAgent 实例
		polisher: PolisherAgent 实例
		reviewer: ReviewerAgent 实例
		output_dir: 输出目录，所有中间结果和最终文章均写入此目录
	"""

	print("\n" + "=" * 60)
	print("写作工作室流水线启动")
	print("=" * 60)
	print(f"  主题: {topic}")
	print(f"  读者: {audience}")
	print(f"  目标: {goal}")
	print(f"  字数: {words}")
	print(f"  语气: {tone}")
	if requirements:
		print(f"  必须包含: {', '.join(requirements)}")
	if constraints:
		print(f"  避免: {', '.join(constraints)}")
	print(f"  输出: {output_dir}")

	# ── 第 1 步：策划编辑 ──
	print(f"\n{'─' * 40}")
	print("第 1/5 步：策划编辑 (planner)")
	print('─' * 40)
	run_planner(planner, topic, audience, goal, words, tone, requirements, constraints, output_dir)

	# ── 第 2 步：内容作者 ──
	print(f"\n{'─' * 40}")
	print("第 2/5 步：内容作者 (writer)")
	print('─' * 40)
	run_writer(writer, output_dir)

	# ── 第 3 步：事实核查员 ──
	print(f"\n{'─' * 40}")
	print("第 3/5 步：事实核查员 (fact_checker)")
	print('─' * 40)
	run_fact_checker(fact_checker, output_dir)

	# ── 第 4 步：润色编辑 ──
	print(f"\n{'─' * 40}")
	print("第 4/5 步：润色编辑 (polisher)")
	print('─' * 40)
	run_polisher(polisher, output_dir)

	# ── 第 5 步：审稿主编 ──
	print(f"\n{'─' * 40}")
	print("第 5/5 步：审稿主编 (reviewer)")
	print('─' * 40)
	run_reviewer(reviewer, output_dir)

	# ── 生成最终文章 ──
	print(f"\n{'─' * 40}")
	print("生成最终文章...")
	print('─' * 40)

	with open(output_dir / "polisher_output.json", encoding="utf-8") as f:
		polisher_output: PolisherOutput = PolisherOutput.model_validate(json.load(f))
	with open(output_dir / "reviewer_output.json", encoding="utf-8") as f:
		reviewer_output: Any = json.load(f)

	final_article: Path = output_dir / "final_article.md"
	with open(final_article, "w", encoding="utf-8") as f:
		f.write(f"# {topic}\n\n")
		f.write(f"> 作者：AI 写作工作室\n")
		f.write(f"> 目标读者：{audience}\n")
		f.write(f"> 综合评分：{reviewer_output.get('overall_score', 'N/A')}\n\n")
		f.write("---\n\n")
		f.write(polisher_output.content)
		f.write("\n\n---\n\n")
		f.write("## 审稿意见\n\n")
		f.write(f"**决策**: {reviewer_output.get('decision', 'N/A')}\n\n")
		f.write(f"**总结**: {reviewer_output.get('summary', 'N/A')}\n\n")

		if reviewer_output.get("strengths"):
			f.write("**优点**:\n")
			for s in reviewer_output["strengths"]:
				f.write(f"- {s}\n")
			f.write("\n")

		if reviewer_output.get("issues"):
			f.write("**问题**:\n")
			for s in reviewer_output["issues"]:
				f.write(f"- {s}\n")
			f.write("\n")

		if reviewer_output.get("suggestions"):
			f.write("**改进建议**:\n")
			for s in reviewer_output["suggestions"]:
				f.write(f"- {s}\n")

	# ── 流水线总结 ──
	print("\n" + "=" * 60)
	print("流水线执行完毕！")
	print("=" * 60)
	print(f"\n📁 所有输出文件:")
	for name in [
		"planner_output.json",
		"writer_output.json",
		"fact_checker_output.json",
		"polisher_output.json",
		"reviewer_output.json",
		"final_article.md"
	]:
		print(f"  • {output_dir / name}")
	print()


# ============================================================
# 角色运行方法
#
# 每个 run_xxx 方法遵循统一模式：
#   1. 检查并加载前序角色的输出文件（按依赖链）
#   2. 构造当前角色的输入模型
#   3. 调用 agent.run() 执行
#   4. 通过 _save_result 展示并保存结果
#
# 依赖关系：
#   planner       ← 无依赖（仅需 CLI 参数）
#                  → 输出 planner_output.json + planner_input.json
#   writer        ← planner_input.json + planner_output.json
#   fact_checker  ← planner_output.json + writer_output.json
#   polisher      ← planner_output.json + writer_output.json
#   reviewer      ← planner_input.json + polisher_output.json
# ============================================================

def _load_json(output_dir: Path, filename: str, model: type[BaseModel]) -> Any:
	"""加载并校验 JSON 文件为 Pydantic 模型，失败时退出。

	Args:
		output_dir: 文件所在目录
		filename: 文件名
		model: 目标 Pydantic 模型类

	Returns:
		校验后的模型实例
	"""
	file: Path = output_dir / filename
	if not file.exists():
		print(f"[错误] 未找到 {filename}")
		sys.exit(1)
	with open(file, encoding="utf-8") as f:
		instance: Any = model.model_validate(json.load(f))
	print(f"从 {filename} 加载")
	return instance


def _save_json(model: BaseModel, output_dir: Path, filename: str) -> None:
	"""展示并保存运行结果。

	Args:
		model: Pydantic 模型实例
		output_dir: 输出目录
		filename: 输出文件名
	"""
	json_raw: str = model.model_dump_json(indent=4, ensure_ascii=False)
	print("=" * 60)
	print(json_raw)
	print("=" * 60)
	output_file: Path = output_dir / filename
	output_file.write_text(json_raw, encoding="utf-8")
	print(f"\n✓ 输出已保存到 {output_file}")


def run_planner(
		agent: PlannerAgent,
		topic: str,
		audience: str,
		goal: str,
		words: str,
		tone: str,
		requirements: list[str] | None,
		constraints: list[str] | None,
		output_dir: Path
) -> None:
	"""运行策划编辑 —— 依赖链起点，无前序文件依赖。

	输出 planner_output.json（策划结果）+ planner_input.json（用户原始输入，供 Reviewer 使用）。
	"""

	task: PlannerInput = PlannerInput(
		topic=topic,
		audience=audience,
		goal=goal,
		word_count=words,
		tone=tone,
		requirements=requirements,
		constraints=constraints,
	)

	print("正在执行策划编辑...\n")
	_save_json(task, output_dir, "planner_input.json")
	_save_json(agent.run(task), output_dir, "planner_output.json")


def run_writer(agent: WriterAgent, output_dir: Path) -> None:
	"""运行内容作者 —— 依赖 planner_input.json + planner_output.json。"""

	pi: PlannerInput = _load_json(output_dir, "planner_input.json", PlannerInput)
	po: PlannerOutput = _load_json(output_dir, "planner_output.json", PlannerOutput)

	task: WriterInput = WriterInput(
		topic=pi.topic,
		word_count=pi.word_count,
		tone=pi.tone,
		audience_analysis=po.audience_analysis,
		core_message=po.core_message,
		outline=po.outline,
		writing_guidelines=po.writing_guidelines,
	)

	print("正在执行内容撰写...\n")
	_save_json(agent.run(task), output_dir, "writer_output.json")


def run_fact_checker(agent: FactCheckerAgent, output_dir: Path) -> None:
	"""运行事实核查员 —— 依赖 planner_output.json + writer_output.json。"""

	pi: PlannerInput = _load_json(output_dir, "planner_input.json", PlannerInput)
	po: PlannerOutput = _load_json(output_dir, "planner_output.json", PlannerOutput)
	wo: WriterOutput = _load_json(output_dir, "writer_output.json", WriterOutput)

	task: FactCheckerInput = FactCheckerInput(
		topic=pi.topic,
		content=wo.content,
		core_message=po.core_message,
		audience_analysis=po.audience_analysis,
		outline=po.outline,
		writer_notes=wo.notes,
	)

	print("正在执行事实核查...\n")
	_save_json(agent.run(task), output_dir, "fact_checker_output.json")


def run_polisher(agent: PolisherAgent, output_dir: Path) -> None:
	"""运行润色编辑 —— 依赖 planner_output.json + writer_output.json。"""

	pi: PlannerInput = _load_json(output_dir, "planner_input.json", PlannerInput)
	po: PlannerOutput = _load_json(output_dir, "planner_output.json", PlannerOutput)
	wo: WriterOutput = _load_json(output_dir, "writer_output.json", WriterOutput)

	task: PolisherInput = PolisherInput(
		topic=pi.topic,
		content=wo.content,
		core_message=po.core_message,
		audience_analysis=po.audience_analysis,
		outline=po.outline,
		writing_guidelines=po.writing_guidelines,
	)

	print("正在执行润色编辑...\n")
	_save_json(agent.run(task), output_dir, "polisher_output.json")


def run_reviewer(agent: ReviewerAgent, output_dir: Path) -> None:
	"""运行审稿主编 —— 依赖 planner_input.json + polisher_output.json。

	使用用户原始需求（非 Planner 策划结果）作为审稿基准。
	"""

	pi: PlannerInput = _load_json(output_dir, "planner_input.json", PlannerInput)
	po: PolisherOutput = _load_json(output_dir, "polisher_output.json", PolisherOutput)

	task: ReviewerInput = ReviewerInput(
		topic=pi.topic,
		audience=pi.audience,
		goal=pi.goal,
		word_count=pi.word_count,
		tone=pi.tone,
		requirements=pi.requirements,
		constraints=pi.constraints,
		content=po.content,
	)

	print("正在执行终审...\n")
	_save_json(agent.run(task), output_dir, "reviewer_output.json")


# ============================================================
# 命令行参数
# ============================================================

def parse_args() -> argparse.Namespace:
	"""解析命令行参数。

	参数分为四组：
	  模式选择  —— --list-roles / --show-role / --run-role / --workflow / --pipeline
	  通用输入  —— --topic / --audience / --goal / --words / --tone
	  文件输入  —— --outline-file / --content-file / --fact-check-file 等
	  全局配置  —— --config

	Returns:
		argparse.Namespace: 解析后的命令行参数
	"""
	parser = argparse.ArgumentParser(
		description="写作工作室角色分工设计",
		formatter_class=argparse.RawDescriptionHelpFormatter,
	)

	# ── 模式选择 ──
	parser.add_argument("--list-roles", action="store_true", help="列出所有角色")
	parser.add_argument("--show-role", metavar="ROLE_ID", help="查看角色详情")
	parser.add_argument("--run-role", metavar="ROLE_ID", help="测试单个角色")
	parser.add_argument("--workflow", action="store_true", help="生成协作流程图")
	parser.add_argument("--pipeline", action="store_true", help="一键运行完整写作流水线（需 --topic）")
	parser.add_argument("--config", metavar="FILE", help="配置文件路径（默认 config.yaml）")

	# ── 通用输入（主要用于 planner）──
	parser.add_argument("--topic", metavar="TEXT", help="文章主题")
	parser.add_argument("--audience", metavar="TEXT", help="目标读者")
	parser.add_argument("--goal", metavar="TEXT", help="写作目标")
	parser.add_argument("--words", metavar="TEXT", help="字数要求")
	parser.add_argument("--tone", metavar="TEXT", help="语气风格")
	parser.add_argument("--requirements", metavar="TEXT", nargs="*", help="必须包含的内容")
	parser.add_argument("--constraints", metavar="TEXT", nargs="*", help="应该避免的内容")

	# ── 高级输入：手动指定前序文件（覆盖默认依赖链）──
	parser.add_argument("--outline-file", metavar="FILE", help="大纲文件（JSON）")
	parser.add_argument("--content-file", metavar="FILE", help="文章内容文件（文本或JSON）")
	parser.add_argument("--fact-check-file", metavar="FILE", help="事实核查报告（JSON）")
	parser.add_argument("--polisher-notes-file", metavar="FILE", help="润色说明（文本或JSON）")

	# ── 完全自定义输入：绕过所有角色，直接加载完整任务 ──
	parser.add_argument("--input-file", metavar="FILE", help="从 JSON 文件加载完整任务输入")

	return parser.parse_args()


# ============================================================
# 主入口
# ============================================================

def main() -> None:
	"""CLI 主入口。

	执行流程：
	  1. 解析命令行参数
	  2. 加载配置 & 初始化 LLM 客户端
	  3. 初始化全部 5 个角色实例（共享 LLM + PromptManager）
	  4. 根据模式参数分发到对应命令

	Raises:
		SystemExit: 角色不存在或前置依赖文件缺失时退出（exit code 1）
	"""
	args: argparse.Namespace = parse_args()

	# ── 初始化基础组件 ──
	prj_root: Path = get_prj_root()

	cfg: Config = Config.from_yaml(args.config)

	llm: LLMClient = LLMClient(
		api_key=cfg.llm.api_key_env,
		base_url=cfg.llm.base_url,
		model=cfg.llm.model,
		temperature=cfg.generation.temperature,
		top_p=cfg.generation.top_p,
		max_tokens=cfg.generation.max_tokens,
	)

	pm: PromptManager = PromptManager(prj_root / "prompts")

	# ── 初始化全部 5 个角色（共享 LLM + PromptManager）──
	planner: PlannerAgent = PlannerAgent(llm, pm)
	writer: WriterAgent = WriterAgent(llm, pm)
	fact_checker: FactCheckerAgent = FactCheckerAgent(llm, pm)
	polisher: PolisherAgent = PolisherAgent(llm, pm)
	reviewer: ReviewerAgent = ReviewerAgent(llm, pm)

	# ── 命令分发 ──
	if args.list_roles:
		cmd_list_roles()

	elif args.show_role:
		if args.show_role == planner.meta().role_id:
			cmd_show_role(planner)
		elif args.show_role == writer.meta().role_id:
			cmd_show_role(writer)
		elif args.show_role == fact_checker.meta().role_id:
			cmd_show_role(fact_checker)
		elif args.show_role == polisher.meta().role_id:
			cmd_show_role(polisher)
		elif args.show_role == reviewer.meta().role_id:
			cmd_show_role(reviewer)
		else:
			print(f"[错误] 角色不存在：{args.show_role}")
			sys.exit(1)

	elif args.workflow:
		cmd_workflow(prj_root / "output")

	elif args.pipeline:
		if not args.topic:
			print("[错误] --pipeline 需要 --topic 参数")
			sys.exit(1)

		pipeline_dir: Path = prj_root / "output" / "pipeline"
		cmd_pipeline(
			topic=args.topic,
			audience=args.audience or "有一定技术背景的读者",
			goal=args.goal or "清晰解释概念，提供实用建议",
			words=args.words or "2000-3000",
			tone=args.tone or "专业、易懂",
			requirements=args.requirements,
			constraints=args.constraints,
			planner=planner,
			writer=writer,
			fact_checker=fact_checker,
			polisher=polisher,
			reviewer=reviewer,
			output_dir=pipeline_dir,
		)

	elif args.run_role:

		output_dir: Path = prj_root / "output"
		output_dir.mkdir(parents=True, exist_ok=True)

		if args.run_role == PlannerAgent.meta().role_id:

			if not args.topic:
				print("[错误] planner 角色需要 --topic 参数")
				sys.exit(1)

			run_planner(
				planner,
				args.topic,
				args.audience or "有一定技术背景的读者",
				args.goal or "清晰解释概念，提供实用建议",
				args.words or "2000-3000",
				args.tone or "专业、易懂",
				args.requirements,
				args.constraints,
				output_dir
			)
		elif args.run_role == WriterAgent.meta().role_id:
			run_writer(writer, output_dir)
		elif args.run_role == FactCheckerAgent.meta().role_id:
			run_fact_checker(fact_checker, output_dir)
		elif args.run_role == PolisherAgent.meta().role_id:
			run_polisher(polisher, output_dir)
		elif args.run_role == ReviewerAgent.meta().role_id:
			run_reviewer(reviewer, output_dir)
		else:
			print(f"[错误] 角色不存在：{args.run_role}")
			sys.exit(1)

	else:
		print("[提示] 请使用 --list-roles / --show-role / --run-role / --workflow 子命令")
		print("      使用 --help 查看完整帮助")


if __name__ == "__main__":
	main()
