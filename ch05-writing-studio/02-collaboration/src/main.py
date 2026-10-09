"""实验14：多智能体协作机制实现 — CLI 入口。

支持运行模式：
  python src/main.py --topic "主题" --audience "读者" --goal "目标"
  
核心功能：
  1. 加载配置和初始化 LLM 客户端
  2. 创建工作流上下文（用户输入）
  3. 初始化工作流编排器
  4. 执行完整协作流程（5 个 Agent + 质量门禁 + 退回重做）
  5. 保存结果并展示执行报告
"""

import argparse
import sys
from pathlib import Path

from config import Config
from inherit.llm.client import LLMClient
from inherit.prompt.prompt_manager import PromptManager
from inherit.utils.path import get_prj_root
from agents.write_studio.workflow.context import WorkflowContext
from agents.write_studio.workflow.orchestrator import WorkflowOrchestrator


def parse_args() -> argparse.Namespace:
	"""解析命令行参数。"""
	parser = argparse.ArgumentParser(
		description="多智能体协作写作系统",
		formatter_class=argparse.RawDescriptionHelpFormatter,
		epilog="""
示例：
  # 基本使用
  python src/main.py --topic "为什么 Rust 越来越受欢迎"

  # 完整参数
  python src/main.py \\
      --topic "AI 智能体的未来发展趋势" \\
      --audience "技术管理者和架构师" \\
      --goal "分析 AI Agent 的技术演进路径" \\
      --words "3000-4000" \\
      --tone "专业、前瞻" \\
      --max-retries 2

  # 自定义配置文件
  python src/main.py --topic "主题" --config custom_config.yaml
		""",
	)
	
	# 必需参数
	parser.add_argument(
		"--topic",
		required=True,
		help="文章主题（必需）",
	)
	
	# 可选参数
	parser.add_argument(
		"--audience",
		default="有一定技术背景的读者",
		help="目标读者（默认：有一定技术背景的读者）",
	)
	
	parser.add_argument(
		"--goal",
		default="清晰解释概念，提供实用建议",
		help="写作目标（默认：清晰解释概念，提供实用建议）",
	)
	
	parser.add_argument(
		"--words",
		default="2000-3000",
		help="字数要求（默认：2000-3000）",
	)
	
	parser.add_argument(
		"--tone",
		default="专业、易懂",
		help="语气风格（默认：专业、易懂）",
	)
	
	parser.add_argument(
		"--requirements",
		nargs="*",
		help="必须包含的内容（可选，多个用空格分隔）",
	)
	
	parser.add_argument(
		"--constraints",
		nargs="*",
		help="应该避免的内容（可选，多个用空格分隔）",
	)
	
	parser.add_argument(
		"--max-retries",
		type=int,
		default=3,
		help="每个阶段最多重试次数（默认：3）",
	)
	
	parser.add_argument(
		"--output-dir",
		type=Path,
		help="输出目录（默认：output/）",
	)
	
	parser.add_argument(
		"--config",
		type=Path,
		help="配置文件路径（默认：config.yaml）",
	)
	
	return parser.parse_args()


def main() -> None:
	"""CLI 主入口。
	
	执行流程：
	  1. 解析命令行参数
	  2. 加载配置并初始化 LLM 客户端
	  3. 创建工作流上下文（包含用户输入）
	  4. 初始化工作流编排器
	  5. 执行完整协作流程
	  6. 展示执行结果
	"""
	args = parse_args()
	
	# ── 初始化基础组件 ──
	prj_root = get_prj_root()
	
	try:
		cfg = Config.from_yaml(args.config)
	except FileNotFoundError as e:
		print(f"[错误] {e}")
		sys.exit(1)
	
	llm = LLMClient(
		api_key=cfg.llm.api_key_env,
		base_url=cfg.llm.base_url,
		model=cfg.llm.model,
		temperature=cfg.generation.temperature,
		top_p=cfg.generation.top_p,
		max_tokens=cfg.generation.max_tokens,
	)
	
	pm = PromptManager(prj_root / "prompts")
	
	# ── 创建工作流上下文 ──
	ctx = WorkflowContext(
		topic=args.topic,
		audience=args.audience,
		goal=args.goal,
		word_count=args.words,
		tone=args.tone,
		requirements=args.requirements,
		constraints=args.constraints,
		max_retries=args.max_retries,
	)
	
	# ── 初始化工作流编排器 ──
	output_dir = args.output_dir or (prj_root / "output")
	orchestrator = WorkflowOrchestrator(
		llm=llm,
		pm=pm,
		max_retries=args.max_retries,
		output_dir=output_dir,
	)
	
	# ── 执行工作流 ──
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
	
	# ── 展示最终状态 ──
	if ctx.current_state.value == "completed":
		print("✓ 写作流程成功完成！")
		sys.exit(0)
	else:
		print(f"✗ 写作流程未完成（最终状态：{ctx.current_state.value}）")
		sys.exit(1)


if __name__ == "__main__":
	main()
