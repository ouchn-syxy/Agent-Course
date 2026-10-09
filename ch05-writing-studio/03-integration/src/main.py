"""实验15：写作工作室智能体综合实践 — CLI 入口。

支持两种模式：
  1. generate：生成文章
     python src/main.py generate --topic "主题" [--enable-researcher]
  
  2. evaluate：评估文章
     python src/main.py evaluate --article output/xxx/final_article.md --workflow output/xxx/workflow_summary.json
"""

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

from config import Config
from inherit.llm.client import LLMClient
from inherit.prompt.prompt_manager import PromptManager
from inherit.utils.path import get_prj_root
from agents.write_studio.workflow.context import WorkflowContext
from agents.write_studio.workflow.orchestrator import WorkflowOrchestrator
from agents.write_studio.evaluation.workflow_evaluator import WorkflowEvaluator


def create_parser() -> argparse.ArgumentParser:
	"""创建命令行参数解析器（支持子命令）。"""
	parser = argparse.ArgumentParser(
		description="多智能体协作写作系统（集成 Researcher 和评估工具）",
		formatter_class=argparse.RawDescriptionHelpFormatter,
	)
	
	# 全局参数
	parser.add_argument(
		"--config",
		type=Path,
		default=Path("config.yaml"),
		help="配置文件路径（默认：config.yaml）",
	)
	
	# 创建子命令
	subparsers = parser.add_subparsers(dest="mode", required=True, help="运行模式")
	
	# ── 子命令 1：generate（生成文章）──
	generate_parser = subparsers.add_parser(
		"generate",
		help="生成文章",
		formatter_class=argparse.RawDescriptionHelpFormatter,
		epilog="""
示例：
  # 基础模式（命令行参数）
  python src/main.py generate --topic "为什么 Rust 越来越受欢迎"

  # 从 JSON 文件读取参数
  python src/main.py generate --from-file data/topics/example1.json

  # 从文件读取并启用 Researcher
  python src/main.py generate --from-file data/topics/example2.json --enable-researcher

  # 文件参数 + 命令行覆盖（命令行参数优先）
  python src/main.py generate \\
      --from-file data/topics/example1.json \\
      --words "4000-5000" \\
      --enable-researcher

  # 完整命令行参数
  python src/main.py generate \\
      --topic "量子计算的最新进展" \\
      --audience "技术管理者" \\
      --goal "分析技术突破和应用前景" \\
      --words "3000-4000" \\
      --enable-researcher
		""",

	)
	
	# generate 必需参数（可以从文件读取或直接指定）
	generate_parser.add_argument(
		"--topic",
		help="文章主题（与 --from-file 二选一）",
	)
	
	generate_parser.add_argument(
		"--from-file",
		type=Path,
		help="从 JSON 文件读取主题参数（与 --topic 二选一，如 data/topics/example1.json）",
	)
	
	# generate 可选参数
	generate_parser.add_argument(
		"--audience",
		default="有一定技术背景的读者",
		help="目标读者",
	)
	
	generate_parser.add_argument(
		"--goal",
		default="清晰解释概念，提供实用建议",
		help="写作目标",
	)
	
	generate_parser.add_argument(
		"--words",
		default="2000-3000",
		help="字数要求",
	)
	
	generate_parser.add_argument(
		"--tone",
		default="专业、易懂",
		help="语气风格",
	)
	
	generate_parser.add_argument(
		"--requirements",
		nargs="*",
		help="必须包含的内容（多个用空格分隔）",
	)
	
	generate_parser.add_argument(
		"--constraints",
		nargs="*",
		help="应该避免的内容（多个用空格分隔）",
	)
	
	generate_parser.add_argument(
		"--enable-researcher",
		action="store_true",
		help="启用 Researcher 智能体（收集背景资料）",
	)
	
	generate_parser.add_argument(
		"--max-retries",
		type=int,
		default=3,
		help="每个阶段最多重试次数（默认：3）",
	)
	
	generate_parser.add_argument(
		"--output-dir",
		type=Path,
		default=Path("output"),
		help="输出目录（默认：output/）",
	)
	
	# ── 子命令 2：evaluate（评估文章）──
	evaluate_parser = subparsers.add_parser(
		"evaluate",
		help="评估文章质量",
		formatter_class=argparse.RawDescriptionHelpFormatter,
		epilog="""
示例：
  # 评估已生成的文章（指定工作流输出目录）
  python src/main.py evaluate --workflow-dir output/20260726_203145

  # 评估并指定评估报告输出位置
  python src/main.py evaluate \\
      --workflow-dir output/20260726_203145 \\
      --output-dir evaluations
		""",
	)
	
	# evaluate 必需参数
	evaluate_parser.add_argument(
		"--workflow-dir",
		type=Path,
		required=True,
		help="工作流输出目录（必需，包含 final_article.md 和 workflow_summary.json）",
	)
	
	# evaluate 可选参数
	evaluate_parser.add_argument(
		"--output-dir",
		type=Path,
		default=Path("output"),
		help="评估报告输出目录（默认：output/）",
	)
	
	return parser


def load_topic_from_file(filepath: Path) -> dict:
	"""从 JSON 文件加载主题参数并映射字段名。"""
	try:
		with open(filepath, encoding="utf-8") as f:
			data = json.load(f)
	except FileNotFoundError:
		print(f"[错误] 文件不存在：{filepath}")
		sys.exit(1)
	except json.JSONDecodeError as e:
		print(f"[错误] JSON 格式错误：{e}")
		sys.exit(1)
	
	# 字段映射：JSON文件字段 -> 程序参数名
	field_mapping = {
		"topic": "topic",
		"target_audience": "audience",
		"writing_goal": "goal",
		"word_count": "words",
		"tone": "tone",
		"requirements": "requirements",
		"constraints": "constraints",
	}
	
	# 映射字段
	mapped_data = {}
	for json_field, param_name in field_mapping.items():
		if json_field in data:
			mapped_data[param_name] = data[json_field]
	
	return mapped_data


def run_generate(args: argparse.Namespace, cfg: Config, prj_root: Path) -> None:
	"""执行生成文章模式。"""
	print("\n" + "=" * 70)
	print("模式：生成文章")
	print("=" * 70)
	
	# 处理参数来源：从文件读取 or 命令行参数
	if args.from_file:
		# 从文件读取
		print(f"从文件读取主题参数：{args.from_file}")
		file_data = load_topic_from_file(args.from_file)
		
		# 合并：文件数据作为基础，命令行参数可覆盖
		topic = args.topic or file_data.get("topic")
		audience = args.audience if args.audience != "有一定技术背景的读者" else file_data.get("audience", args.audience)
		goal = args.goal if args.goal != "清晰解释概念，提供实用建议" else file_data.get("goal", args.goal)
		words = args.words if args.words != "2000-3000" else file_data.get("words", args.words)
		tone = args.tone if args.tone != "专业、易懂" else file_data.get("tone", args.tone)
		requirements = args.requirements or file_data.get("requirements")
		constraints = args.constraints or file_data.get("constraints")
		
		if not topic:
			print("[错误] JSON 文件必须包含 'topic' 字段")
			sys.exit(1)
		
		print(f"主题：{topic}")
		
	elif args.topic:
		# 从命令行读取
		topic = args.topic
		audience = args.audience
		goal = args.goal
		words = args.words
		tone = args.tone
		requirements = args.requirements
		constraints = args.constraints
	else:
		print("[错误] 必须指定 --topic 或 --from-file 参数")
		sys.exit(1)
	
	# 初始化 LLM 和 PromptManager
	llm = LLMClient(
		api_key=cfg.llm.api_key_env,
		base_url=cfg.llm.base_url,
		model=cfg.llm.model,
		temperature=cfg.generation.temperature,
		top_p=cfg.generation.top_p,
		max_tokens=cfg.generation.max_tokens,
	)
	
	pm = PromptManager(prj_root / "prompts")
	
	# 创建工作流上下文
	ctx = WorkflowContext(
		topic=topic,
		audience=audience,
		goal=goal,
		word_count=words,
		tone=tone,
		requirements=requirements,
		constraints=constraints,
		max_retries=args.max_retries,
	)
	
	# 初始化工作流编排器
	orchestrator = WorkflowOrchestrator(
		llm=llm,
		pm=pm,
		max_retries=args.max_retries,
		output_dir=args.output_dir,
		enable_researcher=args.enable_researcher,
		tavily_api_key=cfg.tavily.api_key if args.enable_researcher else "",
	)
	
	# 执行工作流
	try:
		ctx = orchestrator.run(ctx)
	except KeyboardInterrupt:
		print("\n\n[中断] 用户终止执行")
		sys.exit(1)
	except Exception as e:
		print(f"\n\n[错误] 工作流执行失败: {e}")
		import traceback
		traceback.print_exc()
		sys.exit(1)
	
	# 展示最终状态
	if ctx.current_state.value == "completed":
		print("\n✓ 写作流程成功完成！")
		if args.enable_researcher:
			print("✓ Researcher 增强模式已启用")
		
		# 提示评估命令
		output_dir = args.output_dir / ctx.workflow_id
		print(f"\n文章已保存到：{output_dir / 'final_article.md'}")
		print(f"\n如需评估文章质量，运行：")
		print(f"  python src/main.py evaluate --workflow-dir {output_dir}")
		
		sys.exit(0)
	else:
		print(f"\n✗ 写作流程未完成（最终状态：{ctx.current_state.value}）")
		sys.exit(1)


def run_evaluate(args: argparse.Namespace, cfg: Config, prj_root: Path) -> None:
	"""执行评估模式（综合评估）。"""
	print("\n" + "=" * 70)
	print("模式：综合评估（输出质量 + 角色表现 + 协作效果）")
	print("=" * 70)
	
	# 检查工作流目录是否存在
	if not args.workflow_dir.exists():
		print(f"[错误] 工作流目录不存在：{args.workflow_dir}")
		sys.exit(1)
	
	# 构建文件路径
	workflow_path = args.workflow_dir / "workflow_summary.json"
	
	# 检查文件是否存在
	if not workflow_path.exists():
		print(f"[错误] 工作流摘要不存在：{workflow_path}")
		print(f"请确保工作流目录包含 workflow_summary.json")
		sys.exit(1)
	
	print(f"工作流目录：{args.workflow_dir}")
	print(f"工作流摘要：{workflow_path}")
	
	# 加载工作流摘要
	try:
		with open(workflow_path, encoding="utf-8") as f:
			workflow_summary = json.load(f)
	except Exception as e:
		print(f"[错误] 无法加载工作流摘要：{e}")
		sys.exit(1)
	
	# 初始化 LLM 和 PromptManager（用于评估）
	llm = LLMClient(
		api_key=cfg.llm.api_key_env,
		base_url=cfg.llm.base_url,
		model=cfg.llm.model,
		temperature=0.3,  # 评估用较低温度
		max_tokens=2000,
	)
	
	pm = PromptManager(prj_root / "prompts")
	
	# 创建工作流评估器
	evaluator = WorkflowEvaluator(llm, pm)
	
	# 执行综合评估
	try:
		report = evaluator.evaluate_workflow(
			workflow_dir=args.workflow_dir,
			workflow_summary=workflow_summary,
		)
		
		# 打印评估报告摘要
		evaluator.print_report_summary(report)
		
		# 保存评估报告
		report_file = args.workflow_dir / "evaluation_report.json"
		evaluator.save_report(report, report_file)
		
		print(f"\n✓ 评估完成！详细报告已保存到：{report_file}")
		sys.exit(0)
		
	except Exception as e:
		print(f"\n[错误] 评估失败：{e}")
		import traceback
		traceback.print_exc()
		sys.exit(1)


def main() -> None:
	"""CLI 主入口。"""
	parser = create_parser()
	args = parser.parse_args()
	
	# 加载配置（两种模式都需要）
	try:
		cfg = Config.from_yaml(args.config)
	except FileNotFoundError as e:
		print(f"[错误] {e}")
		print(f"请确保配置文件存在：{args.config}")
		sys.exit(1)
	except Exception as e:
		print(f"[错误] 配置文件加载失败：{e}")
		sys.exit(1)
	
	prj_root = get_prj_root()
	
	# 根据模式分发
	if args.mode == "generate":
		run_generate(args, cfg, prj_root)
	
	elif args.mode == "evaluate":
		run_evaluate(args, cfg, prj_root)
	
	else:
		parser.print_help()
		sys.exit(1)


if __name__ == "__main__":
	main()
