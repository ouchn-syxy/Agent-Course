"""
实验 4：人物特征提取与工具调用 — 主入口

用法：
    python main.py --extract 鲁迅         # 自动搜索 + 提取 + 保存角色 YAML
    python main.py --search 鲁迅 生平     # 单独测试 Tavily 搜索
    python main.py --list-tools          # 列出所有已注册工具
    python main.py --eval 鲁迅          # 评估角色提取质量（对比参考 YAML）
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from agents.role_play.profile_extractor_agent import ProfileExtractorAgent
from agents.role_play.tools.extract_profile import ExtractProfile
from config import Config
from evaluator import run_evaluation
from inherit.prompt.prompt_manager import PromptManager
from inherit.utils.path import get_prj_root
from llm.tool_client import ToolLLMClient
from llm.tool_registry import ToolRegistry
from tools.read_url import ReadUrl
from tools.save_yaml import SaveYaml
from tools.tavily_search import TavilySearch
from tools.wikipedia_search import WikipediaSearch


# ============================================================
# 路径工具
# ============================================================

def _get_prompts_dir() -> Path:
	"""获取提示词模板目录。"""
	return get_prj_root() / "prompts"


# ============================================================
# 命令行参数
# ============================================================

def parse_args() -> argparse.Namespace:
	"""解析命令行参数。"""
	parser: argparse.ArgumentParser = argparse.ArgumentParser(
		description="人物特征提取与工具调用",
		formatter_class=argparse.RawDescriptionHelpFormatter,
		epilog="""
用法：
    python main.py --extract 鲁迅         # 自动搜索 + 提取 + 保存角色 YAML
    python main.py --search 鲁迅 生平     # 单独测试 Tavily 搜索
    python main.py --list-tools          # 列出所有已注册工具
    python main.py --eval 鲁迅          # 评估提取质量（对比参考 YAML）
        """,
	)
	parser.add_argument(
		"--extract",
		metavar="NAME",
		help="自动搜索并提取角色特征（如 '鲁迅'）",
	)
	parser.add_argument(
		"--search",
		nargs="+",
		metavar="TERMS",
		help="单独测试 Tavily 搜索（如 '鲁迅 生平'）",
	)
	parser.add_argument(
		"--list-tools",
		action="store_true",
		help="列出所有已注册工具",
	)
	parser.add_argument(
		"--eval",
		metavar="NAME",
		help="评估提取质量（如 'luxun'，对比参考 YAML）",
	)
	return parser.parse_args()


# ============================================================
# 运行模式
# ============================================================

def _run_extract(
		agent: ProfileExtractorAgent,
		name: str,
) -> None:
	"""--extract 模式：自动搜索 + 提取 + 保存。"""

	print("=" * 60)
	print(f"  🤖 特征提取智能体 — 目标人物：{name}")
	print("=" * 60)
	print()

	result = agent.run(name=name)

	print()
	print("=" * 60)
	print("  任务完成！")
	print("=" * 60)
	print(result)
	print()
	print(f"  生成文件: output/{name}.yaml")


def _run_search(tool: TavilySearch, terms: list[str]) -> None:
	"""--search 模式：单独测试 Tavily 搜索。"""

	query = " ".join(terms)

	print(f"🔍 搜索: {query}")
	print()
	results = tool.search(query)
	for i, r in enumerate(results, 1):
		if "error" in r:
			print(f"  ❌ {r['error']}")
		elif "message" in r:
			print(f"  ℹ️ {r['message']}")
		else:
			print(f"  {i}. {r.get('title', '无标题')}")
			print(f"     {r.get('content', '')[:100]}...")
			print(f"     {r.get('url', '')}")
			print()


def _format_tools(registry: ToolRegistry) -> str:
	"""将已注册工具格式化为人类可读的文本。"""
	tools = registry.list()
	if not tools:
		return "（尚未注册任何工具）"
	lines: list[str] = []
	for tool in tools:
		param_strs: list[str] = []
		for pname, pinfo in tool.parameters.items():
			req = "（必填）" if pname in tool.required else ""
			param_strs.append(
				f"    {pname}: {pinfo.get('type', 'any')} {req}"
				f"— {pinfo.get('description', '')}"
			)
		lines.append(f"🔧 {tool.name}")
		lines.append(f"   {tool.description}")
		lines.append("\n".join(param_strs))
		lines.append("")
	return "\n".join(lines)


def _run_list_tools(tool_registry: ToolRegistry) -> None:
	"""--list-tools 模式。"""
	print("已注册工具：")
	print()
	print(_format_tools(tool_registry))


# ============================================================
# 主入口
# ============================================================


def main() -> None:
	if hasattr(sys.stdout, "reconfigure"):
		sys.stdout.reconfigure(errors="replace")
	args: argparse.Namespace = parse_args()

	# --eval 不需要初始化 LLM 和工具
	if args.eval:
		run_evaluation(args.eval)
		return

	cfg: Config = Config.from_yaml()

	# 初始化 LLM 客户端
	tool_llm: ToolLLMClient = ToolLLMClient(
		api_key=cfg.llm.api_key_env,
		base_url=cfg.llm.base_url,
		model=cfg.llm.model,
		temperature=cfg.generation.temperature,
		top_p=cfg.generation.top_p,
		max_tokens=cfg.generation.max_tokens,
	)

	# 初始化提示词管理器
	pm: PromptManager = PromptManager(_get_prompts_dir())

	# 初始化工具
	# -- Tavily Search --
	tavily_search: TavilySearch = TavilySearch(
		api_key=cfg.tavily.api_key,
		max_results=cfg.tavily.max_results,
		include_answer=cfg.tavily.include_answer,
	)
	# -- saver --
	save_yaml: SaveYaml = SaveYaml(output_dir=get_prj_root() / "output")
	# -- Wikipedia Query --
	wikipedia_search: WikipediaSearch = WikipediaSearch()
	# -- Read URL --
	read_url: ReadUrl = ReadUrl()
	# -- Feature Extractor --
	extract_profile: ExtractProfile = ExtractProfile(tool_llm, pm)

	# 注册工具
	tool_registry: ToolRegistry = ToolRegistry()
	tool_registry.register(tavily_search.to_tool_def())
	tool_registry.register(save_yaml.to_tool_def())
	tool_registry.register(wikipedia_search.to_tool_def())
	tool_registry.register(read_url.to_tool_def())
	tool_registry.register(extract_profile.to_tool_def())

	if args.list_tools:
		_run_list_tools(tool_registry)
		return

	if args.search:
		_run_search(tavily_search, args.search)
		return

	if args.extract:
		profile_extractor_agent: ProfileExtractorAgent = ProfileExtractorAgent(
			tool_llm, pm,
			max_iterations=5,
			tavily_search=tavily_search,
			wikipedia_search=wikipedia_search,
			read_url=read_url,
			save_yaml=save_yaml,
			extract_profile=extract_profile,
		)
		_run_extract(profile_extractor_agent, args.extract)
		return

	# 无参数 → 显示帮助
	print("请指定运行模式。使用 --help 查看可用选项。")
	print()
	print("常用命令：")
	print("  python main.py --extract 鲁迅        # 自动提取角色特征")
	print("  python main.py --search 鲁迅 生平     # 单独测试 Tavily 搜索")
	print("  python main.py --list-tools         # 列出工具")
	print("  python main.py --eval 鲁迅         # 评估提取质量（对比参考 YAML）")


if __name__ == "__main__":
	main()
