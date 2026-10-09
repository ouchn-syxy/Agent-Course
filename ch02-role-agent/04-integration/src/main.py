"""
角色模拟智能体综合实践 — 交互式对话入口。

在提示词设计（实验 2）、记忆机制（实验 3）、工具调用（实验 4）
的基础上整合全部模块，提供统一的对话体验。

用法:
    python main.py                          # 交互式对话（默认鲁迅 + 记忆 + CoT）
    python main.py --profile luxun          # 指定角色
    python main.py --list                   # 列出可用角色
    python main.py --no-memory              # 关闭记忆
    python main.py --tts                    # 启用 TTS 语音输出
    python main.py --few-shot               # 启用 Few-shot 示例
    python main.py --no-cot                 # 关闭 CoT 思考链
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

import yaml

from agents.role_play.role_play_agent import RolePlayAgent
from agents.role_play.profile_extractor_agent import ExtractProfile, ProfileExtractorAgent
from config import Config
from inherit.llm.client import LLMClient
from inherit.llm.tool_client import ToolLLMClient
from inherit.prompt.prompt_manager import PromptManager
from inherit.tools.read_url import ReadUrl
from inherit.tools.save_yaml import SaveYaml
from inherit.tools.tavily_search import TavilySearch
from inherit.tools.wikipedia_search import WikipediaSearch
from inherit.utils.path import get_prj_root
from tts.client import TTSClient


# ============================================================
# 命令行参数
# ============================================================

def parse_args() -> argparse.Namespace:
	"""解析命令行参数。"""
	parser: argparse.ArgumentParser = argparse.ArgumentParser(
		description="角色模拟智能体综合实践",
		formatter_class=argparse.RawDescriptionHelpFormatter,
		epilog="""
示例:
    python main.py --profile luxun          # 与指定角色对话
    python main.py --discover 林徽因         # 自动搜索提炼新角色 → 对话
    python main.py --list                   # 列出可用角色
    python main.py --no-memory              # 关闭记忆
    python main.py --tts                    # 启用 TTS
    python main.py --few-shot               # 启用 Few-shot 示例
    python main.py --no-cot                 # 关闭 CoT 思考链
		""",
	)
	parser.add_argument(
		"--profile", default=None,
		help="角色名称（如 luxun）",
	)
	parser.add_argument(
		"--discover", default=None, metavar="NAME",
		help="自动搜索提炼新角色并进入对话（如 --discover 林徽因）",
	)
	parser.add_argument(
		"--list", action="store_true",
		help="列出所有可用角色",
	)
	parser.add_argument(
		"--no-memory", action="store_true",
		help="关闭短期+长期记忆",
	)
	parser.add_argument(
		"--tts", action="store_true",
		help="启用 TTS 语音输出（需配置好 TTS 服务）",
	)
	parser.add_argument(
		"--few-shot", action="store_true",
		help="在 system prompt 中注入 Few-shot 对话示例",
	)
	parser.add_argument(
		"--no-cot", action="store_true",
		help="关闭 CoT（Chain-of-Thought）思考链引导",
	)
	return parser.parse_args()


# ============================================================
# 列出角色
# ============================================================

def list_profiles() -> None:
	"""扫描 data/profiles/ 目录，列出所有可用角色。"""
	profiles_dir: Path = get_prj_root() / "data" / "profiles"

	if not profiles_dir.exists():
		print("未找到任何角色 Profile 文件。请在 data/profiles/ 目录下创建。")
		return

	print("\n可用角色：")
	for p in sorted(profiles_dir.glob("*.yaml")):
		with open(p, encoding="utf-8") as f:
			c: dict[str, Any] = yaml.safe_load(f)
		print(f"  🎭 {p.stem:12s} — {c.get('identity', '未知')}")
	print()


# ============================================================
# 自动提炼角色
# ============================================================


def _run_discover(agent: ProfileExtractorAgent, name: str) -> None:
	"""执行角色特征提炼，含已有角色覆盖确认。

	失败时直接抛出异常，由上层处理。

	:param agent: 已配置好工具和提示词管理器的 ProfileExtractor 实例
	:param name:  目标人物名称（如 "鲁迅"）
	"""
	output_dir: Path = get_prj_root() / "data" / "profiles"
	profile_path: Path = output_dir / f"{name}.yaml"

	# 已有角色 → 询问是否覆盖
	if profile_path.exists():
		print(f"\n角色 {name} 已经存在。")
		answer: str = input("是否覆盖？(y/N): ").strip().lower()
		if answer != "y":
			print("已跳过提炼，直接进入对话。")
			return

	print(f"\n🔍 正在提炼 {name} 的角色特征...")

	result: str = agent.run(name)
	if not profile_path.exists():
		raise RuntimeError(f"角色提炼未生成画像文件：{result}")

	print(f"\n✅ 角色提炼完成")
	print(f"  生成文件: {profile_path}")
	print()


# ============================================================
# 交互式对话
# ============================================================

def chat_loop(agent: RolePlayAgent) -> None:
	"""交互式对话循环。"""

	while True:
		try:
			user_input: str = input("你: ").strip()
		except (EOFError, KeyboardInterrupt):
			print("\n再见！")
			break

		if not user_input:
			continue

		if user_input.lower() == "/quit":
			print("再见！")
			break

		if user_input.lower() == "/reset":
			agent.reset()
			print("[系统] 对话已重置\n")
			continue

		if user_input.lower() == "/memory":
			panel: str | None = agent.visualize_memory()
			if panel:
				print(panel)
			else:
				print("[系统] 记忆功能未启用\n")
			print()
			continue

		print()
		try:
			reply: str = agent.chat(user_input)
			print(f"角色: {reply}\n")
		except Exception as e:
			print(f"[错误] {e}\n")


# ============================================================
# 主入口
# ============================================================

def main() -> None:
	"""主入口。"""
	if hasattr(sys.stdout, "reconfigure"):
		sys.stdout.reconfigure(errors="replace")

	from inherit.memory.conversation_memory import ConversationMemory

	args: argparse.Namespace = parse_args()

	# --list
	if args.list:
		list_profiles()
		return

	# 加载配置
	cfg: Config = Config.from_yaml()

	# 构造 LLM 客户端
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

	# 构造 TTS 客户端（--tts 时启用）
	tts_client: TTSClient | None = None
	tts_voice_ref_path: Path | None = None
	if args.tts:
		if cfg.tts is None or not cfg.tts.voice_ref_path:
			print("错误：--tts 需要在 config.yaml 的 tts.voice_ref_path 配置参考音频文件。")
			return
		tts_voice_ref_path = Path(cfg.tts.voice_ref_path)
		if not tts_voice_ref_path.is_file():
			print(f"错误：找不到 TTS 参考音频文件：{tts_voice_ref_path}")
			return
		tts_client = TTSClient(base_url=cfg.tts.base_url)

	pm: PromptManager = PromptManager(get_prj_root() / "prompts")

	output_dir: Path = get_prj_root() / "data" / "profiles"

	# 初始化工具
	# -- Tavily Search --
	tavily_search: TavilySearch = TavilySearch(
		api_key=cfg.tavily.api_key,
		max_results=cfg.tavily.max_results,
		include_answer=cfg.tavily.include_answer,
	)
	# -- saver --
	save_yaml: SaveYaml = SaveYaml(output_dir)
	# -- Wikipedia Query --
	wikipedia_search: WikipediaSearch = WikipediaSearch()
	# -- Read URL --
	read_url: ReadUrl = ReadUrl()
	# -- Feature Extractor --
	extract_profile: ExtractProfile = ExtractProfile(tool_llm, pm)

	# 初始化智能体
	profile_extractor_agent: ProfileExtractorAgent = ProfileExtractorAgent(
		llm=tool_llm,
		prompt_manager=pm,
		max_iterations=10,
		tavily_search=tavily_search,
		wikipedia_search=wikipedia_search,
		read_url=read_url,
		save_yaml=save_yaml,
		extract_profile=extract_profile,
	)

	# --discover: 自动提炼角色 → 聊天
	if args.discover:
		_run_discover(profile_extractor_agent, args.discover)
		args.profile = args.discover

	# --profile 为必填（除非 --list）
	if not args.profile:
		print("错误：请通过 --profile 或 --discover 指定角色名称")
		return

	# 初始化智能体
	role_play_agent: RolePlayAgent = RolePlayAgent(
		profile_name=args.profile,
		llm=llm,
		enable_memory=not args.no_memory,
		enable_cot=not args.no_cot,
		enable_few_shot=args.few_shot,
		max_turns=cfg.memory.max_turns,
		max_tokens=cfg.memory.max_tokens,
		tts_client=tts_client,
		tts_voice_ref_path=tts_voice_ref_path,
	)

	# 启动交互
	print("=" * 60)
	print(f"  🎭 角色模拟智能体综合实践 — {role_play_agent.profile_name}")
	print(f"  模型: {llm.model}")
	flags: list[str] = []
	if not args.no_memory:
		flags.append("记忆 ✓")
	if not args.no_cot:
		flags.append("CoT ✓")
	if args.few_shot:
		flags.append("Few-shot ✓")
	if tts_client:
		flags.append("TTS ✓")
	if flags:
		print(f"  功能: {' | '.join(flags)}")
	print("=" * 60)
	print("  输入对话内容，按 Enter 发送。")
	print("  输入 /quit 退出，/reset 重置对话，/memory 查看记忆面板。")
	print("=" * 60)

	memory: ConversationMemory | None = role_play_agent.memory
	if memory is not None and memory.turn_count > 0:
		print(f"[系统] 已恢复 {memory.turn_count} 轮历史对话记忆")
	print()
	chat_loop(role_play_agent)


if __name__ == "__main__":
	main()
