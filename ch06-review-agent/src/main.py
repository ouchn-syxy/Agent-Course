#!/usr/bin/env python3
"""复习助手智能体 — CLI 入口。

用法：
    python main.py                  # 执行当日学习任务（默认）
    python main.py --init           # 初始化新学习会话
    python main.py --session ID     # 指定会话 ID
    python main.py --status         # 查看当前状态
    python main.py --list           # 列出所有会话
    python main.py --reset ID       # 删除指定会话
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from agents.review.review_agent import ReviewAgent
from agents.review.tools.lookup_knowledge_point import LookupKnowledgePoint
from agents.review.tools.search_fact_check import SearchFactCheck
from agents.review.tools.search_reference_questions import SearchReferenceQuestions
from config import Config
from inherit.llm.client import LLMClient
from inherit.llm.tool_client import ToolLLMClient
from inherit.prompt.prompt_manager import PromptManager
from inherit.utils.path import get_prj_root


def _find_latest_session(sessions_dir: Path) -> str | None:
	"""查找最近的会话 ID。"""
	if not sessions_dir.exists():
		return None
	files = sorted(sessions_dir.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
	if files:
		return files[0].stem
	return None


def main() -> None:
	if hasattr(sys.stdout, "reconfigure"):
		sys.stdout.reconfigure(errors="replace")
	parser = argparse.ArgumentParser(
		description="复习助手智能体 — 21 天数据结构复习计划",
		formatter_class=argparse.RawDescriptionHelpFormatter,
	)
	parser.add_argument("--init", action="store_true", help="初始化新学习会话")
	parser.add_argument("--session", "-s", type=str, default=None, help="指定会话 ID")
	parser.add_argument("--status", action="store_true", help="查看当前状态")
	parser.add_argument("--list", action="store_true", help="列出所有会话")
	parser.add_argument("--reset", type=str, default=None, metavar="ID", help="删除指定会话")
	parser.add_argument("--config", "-c", type=str, default=None, help="配置文件路径")
	parser.add_argument("--syllabus", type=str, default=None, help="大纲 JSON 文件路径")
	args = parser.parse_args()

	# 加载配置
	try:
		config = Config.from_yaml(args.config)
	except FileNotFoundError as e:
		print(f"❌ {e}")
		sys.exit(1)

	api_key = os.getenv(config.llm.api_key_env, config.llm.api_key_env)
	llm = LLMClient(
		api_key=api_key,
		base_url=config.llm.base_url,
		model=config.llm.model,
		temperature=config.generation.temperature,
		top_p=config.generation.top_p,
		max_tokens=config.generation.max_tokens,
	)
	# 工具调用客户端与基础客户端共享同一连接配置
	tool_llm = ToolLLMClient(
		api_key=api_key,
		base_url=config.llm.base_url,
		model=config.llm.model,
		temperature=config.generation.temperature,
		top_p=config.generation.top_p,
		max_tokens=config.generation.max_tokens,
	)
	pm = PromptManager(get_prj_root() / "prompts")

	agent = ReviewAgent(
		llm, tool_llm, pm,
		search_reference_questions=SearchReferenceQuestions(
			tavily_api_key=config.tavily.api_key,
			max_results=config.tavily.max_results,
		),
		lookup_knowledge_point=LookupKnowledgePoint(),
		search_fact_check=SearchFactCheck(
			tavily_api_key=config.tavily.api_key,
			max_results=config.tavily.max_results,
		),
	)
	sessions_dir = get_prj_root() / "data" / "sessions"

	# --list
	if args.list:
		sessions = agent.list_sessions()
		if not sessions:
			print("📭 没有找到任何会话。运行 `python main.py --init` 创建第一个会话。")
		else:
			print(f"\n📋 共 {len(sessions)} 个会话：\n")
			for s in sessions:
				progress = f"{s.current_day}/{s.total_days}"
				print(f"   [{s.session_id}] {s.exam_name}")
				print(f"       进度：{progress} 天  |  更新时间：{s.updated_at[:19]}")
		return

	# --reset
	if args.reset:
		agent.reset_session(args.reset)
		return

	# --init
	if args.init:
		syllabus_path = Path(args.syllabus) if args.syllabus else get_prj_root() / "data" / "data_structure_exam.json"
		agent.init_session(syllabus_path)
		return

	# --status 或 daily
	session_id = args.session
	if session_id is None:
		session_id = _find_latest_session(sessions_dir)

	if session_id is None:
		print("❌ 没有找到任何会话。请先运行 `python main.py --init` 初始化。")
		sys.exit(1)

	try:
		state = agent.load_state(session_id)
	except FileNotFoundError:
		print(f"❌ 会话 {session_id} 不存在。")
		sys.exit(1)

	if args.status:
		agent.show_status(state)
	else:
		agent.run_daily(state)


if __name__ == "__main__":
	main()
