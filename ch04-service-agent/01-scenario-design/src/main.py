"""
电商客服场景分析与流程设计 — CLI 入口。

集成消息分类、策略决策、回复生成三大模块，
提供交互式演示与工作流输出两种运行模式。

用法:
    python main.py                  # 交互式演示
    python main.py --workflow       # 输出 Mermaid 流程图 DSL
"""

from __future__ import annotations

import argparse

from agents.eshop_service.message_category_manager import MessageCategoryManager
from agents.eshop_service.message_classifier import MessageClassifier
from agents.eshop_service.models.types import (
	ConversationMessage,
	HandlingStrategy,
	MessageClassificationResult,
	ResponseMode,
)
from agents.eshop_service.reply_generator import ReplyGenerator
from agents.eshop_service.strategy_engine import StrategyEngine
from agents.eshop_service.workflow_render import render_mermaid
from config import Config
from evaluator import evaluate
from inherit.llm.client import LLMClient
from inherit.llm.tool_client import ToolLLMClient
from inherit.prompt.prompt_manager import PromptManager
from inherit.utils.path import get_prj_root


# ============================================================
# 命令行参数
# ============================================================

def parse_args() -> argparse.Namespace:
	"""解析命令行参数。"""
	parser: argparse.ArgumentParser = argparse.ArgumentParser(
		description="电商客服消息分类与策略引擎",
		formatter_class=argparse.RawDescriptionHelpFormatter,
		epilog="""
示例:
    python main.py                  # 交互式演示
    python main.py --workflow       # 输出 Mermaid 流程图
    python main.py --eval           # 评估分类器准确率
		""",
	)
	parser.add_argument(
		"--workflow", action="store_true",
		help="输出 Mermaid 流程图 DSL",
	)
	parser.add_argument(
		"--eval", action="store_true",
		help="基于 sample_messages.json 评估分类器准确率",
	)
	return parser.parse_args()


# ============================================================
# 格式化工具
# ============================================================

_MODE_LABELS: dict[ResponseMode, str] = {
	ResponseMode.AUTO: "✅ 自动回复",
	ResponseMode.AUTO_WITH_ESCALATION: "⚠️ 自动回复（可升级转人工）",
	ResponseMode.HUMAN: "❌ 转人工处理",
	ResponseMode.IGNORE: "🚫 忽略不回复",
}


def _fmt_result(result: MessageClassificationResult, decision: HandlingStrategy) -> str:
	"""格式化输出分类+策略结果。"""
	lines = [
		"─" * 50,
		f" 分类: {result.parent} / {result.name}",
		f"🎯 置信度: {result.confidence:.2f}",
		f"😊 情感: {result.sentiment}  |  ⚡ 紧急度: {result.urgency}",
	]
	if result.key_info:
		lines.append(f"🔑 关键信息: {result.key_info}")
	lines.append("")
	lines.append("📋 策略决策:")
	lines.append(f"   回复模式: {_MODE_LABELS.get(decision.response_mode, str(decision.response_mode))}")
	if decision.escalation_reason:
		lines.append(f"   转人工原因: {decision.escalation_reason}")
	lines.append(f"   查商品:   {'是' if decision.need_product_query else '否'}")
	lines.append(f"   查订单:   {'是' if decision.need_order_query else '否'}")
	if decision.reply_template:
		lines.append(f"   回复模板: {decision.reply_template}")
	if decision.action_hints:
		lines.append(f"   操作提示: {', '.join(decision.action_hints)}")
	lines.append("─" * 50)
	return "\n".join(lines)


# ============================================================
# 交互式演示
# ============================================================

def interactive_mode(
		classifier: MessageClassifier,
		engine: StrategyEngine,
		generator: ReplyGenerator,
) -> None:
	"""交互式分类演示：逐条输入消息，查看分类、策略和生成回复。"""

	while True:
		try:
			message: str = input("👤 客户消息: ").strip()
		except (EOFError, KeyboardInterrupt):
			print("\n👋 再见！")
			break

		if not message:
			continue
		if message.lower() in ("quit", "exit", "q"):
			print("👋 再见！")
			break

		conversation: list[ConversationMessage] = [ConversationMessage(role="customer", content=message)]
		result: MessageClassificationResult = classifier.classify(conversation)
		decision: HandlingStrategy = engine.decide(conversation, result)

		print(f"📨 {message}")
		print(_fmt_result(result, decision))

		if decision.response_mode in (ResponseMode.AUTO, ResponseMode.AUTO_WITH_ESCALATION):
			print("\n⏳ 正在生成回复...")
			reply: str = generator.generate(conversation, result, decision)
			print(f"🤖 AI 回复:\n{reply}")
		print()


# ============================================================
# 输出工作流
# ============================================================

def workflow_mode(mgr: MessageCategoryManager) -> None:
	"""输出 Mermaid 流程图 DSL。"""
	mermaid: str = render_mermaid(mgr)
	print(mermaid)


# ============================================================
# 主入口
# ============================================================

def main() -> None:
	"""程序入口。"""
	args: argparse.Namespace = parse_args()
	cfg: Config = Config.from_yaml()

	category_mgr: MessageCategoryManager = MessageCategoryManager(
		get_prj_root() / "data" / "eshop_service" / "message_category"
	)

	# --workflow 无需 LLM，直接输出
	if args.workflow:
		workflow_mode(category_mgr)
		return

	# ── 构造 LLM 客户端 ──
	llm: LLMClient = LLMClient(
		api_key=cfg.llm.api_key_env,
		base_url=cfg.llm.base_url,
		model=cfg.llm.model,
		temperature=cfg.generation.temperature,
		top_p=cfg.generation.top_p,
		max_tokens=cfg.generation.max_tokens,
	)
	tool_llm: ToolLLMClient = ToolLLMClient(
		api_key=cfg.llm.api_key_env,
		base_url=cfg.llm.base_url,
		model=cfg.llm.model,
		temperature=cfg.generation.temperature,
		top_p=cfg.generation.top_p,
		max_tokens=cfg.generation.max_tokens,
	)
	pm: PromptManager = PromptManager(get_prj_root() / "prompts")

	# ── 构造三大模块 ──
	classifier: MessageClassifier = MessageClassifier(llm=llm, pm=pm, category_mgr=category_mgr)
	engine: StrategyEngine = StrategyEngine(category_mgr, llm, pm)
	generator: ReplyGenerator = ReplyGenerator(tool_llm, pm)

	# --eval 评估模式
	if args.eval:
		evaluate(classifier, engine)
		return

	# ── 启动 ──
	print("=" * 50)
	print("  🛒 电商客服场景分析与流程设计")
	print(f"  模型: {cfg.llm.model}")
	print("=" * 50)

	print("  模式: 交互式演示")
	print("  输入客户消息查看分类、策略和 AI 回复")
	print("  输入 quit 退出")
	print("=" * 50)
	print()
	interactive_mode(classifier, engine, generator)


if __name__ == "__main__":
	main()
