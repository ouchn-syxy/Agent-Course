"""
带记忆的鲁迅角色模拟对话入口。

在实验 1（提示词设计）的基础上集成短期记忆（滑动窗口 + 摘要压缩 + 文件持久化）。

用法：
	python main.py                    # 交互式对话
	python main.py --profile luxun    # 指定角色
	python main.py --list             # 列出可用角色
	python main.py --memory-panel     # 每轮显示记忆面板
	python main.py --eval             # 运行记忆准确性评估
	python main.py --tiktoken-demo    # 运行 tiktoken 演示
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

import yaml

from config import Config
from evaluator import run_evaluation
from inherit.llm.client import LLMClient
from inherit.prompt.prompt_manager import PromptManager
from inherit.utils.path import get_prj_root
from llm.memory_chat_session import MemoryChatSession
from llm.token_counter import estimate_tokens, MODEL_ENCODING
from memory.conversation_memory import ConversationMemory

# ============================================================
# 配置常量
# ============================================================

DEFAULT_PROFILE: str = "luxun"


# ============================================================
# 路径工具
# ============================================================

def _get_profiles_dir() -> Path:
	"""获取角色数据目录。"""
	return get_prj_root() / "data" / "profiles"


def _get_prompts_dir() -> Path:
	"""获取提示词模板目录。"""
	return get_prj_root() / "prompts"


def _get_memories_dir() -> Path:
	"""获取记忆持久化存储目录。"""
	return get_prj_root() / "data" / "memories"


# ============================================================
# 命令行参数
# ============================================================

def parse_args() -> argparse.Namespace:
	"""解析命令行参数。"""
	parser: argparse.ArgumentParser = argparse.ArgumentParser(
		description="带记忆的角色模拟智能体",
		formatter_class=argparse.RawDescriptionHelpFormatter,
		epilog="""
示例：
	python main.py                     # 交互式对话
	python main.py --profile luxun     # 指定角色
	python main.py --list              # 列出可用角色
	python main.py --memory-panel      # 显示记忆面板
	python main.py --eval              # 运行记忆评估
	python main.py --tiktoken-demo     # tiktoken 演示
		""",
	)
	parser.add_argument(
		"--profile", default=DEFAULT_PROFILE,
		help=f"角色名称（默认: {DEFAULT_PROFILE}）",
	)
	parser.add_argument(
		"--list", action="store_true",
		help="列出所有可用角色",
	)
	parser.add_argument(
		"--memory-panel", action="store_true",
		help="每轮对话后显示记忆面板",
	)
	parser.add_argument(
		"--eval", action="store_true",
		help="运行记忆准确性 LLM-as-Judge 评估",
	)
	parser.add_argument(
		"--tiktoken-demo", action="store_true",
		help="运行 tiktoken 演示后退出",
	)
	parser.add_argument(
		"--few-shot", action="store_true",
		help="启用 Few-shot 示例",
	)
	parser.add_argument(
		"--cot", action="store_true",
		help="启用 Chain-of-Thought 推理",
	)
	return parser.parse_args()


# ============================================================
# Token 演示
# ============================================================

def _run_tiktoken_demo() -> None:
	"""运行 tiktoken 与 DeepSeek 估算对比演示（教学用）。"""
	test_texts: list[tuple[str, str]] = [
		("英文短句", "Hello, how are you?"),
		("中文短句", "你好，今天天气不错。"),
		("鲁迅风格文本", "我向来是不惮以最坏的恶意来推测中国人的。"),
		("混合文本", "鲁迅（Lu Xun）生于1881年，是伟大的文学家、思想家。"),
	]

	tiktoken_models: list[str] = [m for m in MODEL_ENCODING if m.startswith("gpt-")]

	print("=" * 60)
	print("  Token 计数对比演示")
	print("=" * 60)

	for label, text in test_texts:
		print(f"\n[{label}]: {text}")
		for model in tiktoken_models:
			count: int = estimate_tokens(text, model=model)
			print(f"  {model} (tiktoken): {count} tokens")
		deepseek_count: int = estimate_tokens(text)
		print(f"  DeepSeek (估算):  {deepseek_count} tokens")

	print("\n" + "=" * 60)
	print("  tiktoken 精确计数  vs  DeepSeek 字符估算")
	print("  算法来源: DeepSeek 官方文档")
	print("    1 英文字符 ≈ 0.3 token / 1 中文字符 ≈ 0.6 token")
	print("=" * 60)


# ============================================================
# 列出角色
# ============================================================

def list_profiles() -> None:
	"""扫描 profiles/ 目录，列出所有可用角色。"""
	profiles_dir: Path = _get_profiles_dir()

	if not profiles_dir.exists():
		print("未找到任何角色 YAML 文件。请在 data/profiles/ 目录下创建。")
		return

	print("\n可用角色：")
	for p in sorted(profiles_dir.glob("*.yaml")):
		with open(p, encoding="utf-8") as f:
			c: dict[str, Any] = yaml.safe_load(f)
		print(f"  🎭 {p.stem:12s} — {c.get('identity', '未知')}")
	print()


# ============================================================
# 角色加载
# ============================================================

def load_profile(name: str) -> dict[str, Any]:
	"""加载指定角色的 YAML 数据。

	Raises:
		FileNotFoundError: 角色文件不存在。
	"""
	profile_path: Path = _get_profiles_dir() / f"{name}.yaml"
	with open(profile_path, encoding="utf-8") as f:
		return yaml.safe_load(f)


# ============================================================
# 交互式对话
# ============================================================

def chat_loop(profile_name: str, session: MemoryChatSession, show_memory_panel: bool = False) -> None:
	"""
	交互式对话循环。

	支持 /quit 退出、/reset 重置对话、/memory 查看记忆面板。
	"""

	print("=" * 60)
	print(f"  🧠 带记忆的角色模拟智能体 — {profile_name}")
	print(f"  模型: {session.llm.info()}")
	print("=" * 60)
	print("  输入对话内容，按 Enter 发送。")
	print("  输入 /quit 退出，/reset 重置对话，/memory 查看记忆面板。")
	print("=" * 60)
	if session.memory.turn_count > 0:
		print(f"[系统] 已恢复 {session.memory.turn_count} 轮历史对话记忆")
	print()

	while True:
		# 读取用户输入（EOF / Ctrl+C 优雅退出）
		try:
			user_input: str = input("你: ").strip()
		except (EOFError, KeyboardInterrupt):
			print("\n再见！")
			break

		if not user_input:
			continue

		# 处理特殊命令
		if user_input.lower() == "/quit":
			print("再见！")
			break

		if user_input.lower() == "/reset":
			session.reset()
			print("[系统] 对话已重置\n")
			continue

		if user_input.lower() == "/memory":
			print(session.memory.visualize())
			print()
			continue

		# 发送消息并显示回复
		print()
		try:
			reply: str = session.send(user_input)
			print(f"角色: {reply}\n")
		except Exception as e:
			print(f"[错误] {e}\n")

		if show_memory_panel:
			print(session.memory.visualize())
			print()


# ============================================================
# 主入口
# ============================================================


def main() -> None:
	"""程序入口。"""
	if hasattr(sys.stdout, "reconfigure"):
		sys.stdout.reconfigure(errors="replace")
	args: argparse.Namespace = parse_args()

	# --tiktoken-demo 不需要初始化 LLM
	if args.tiktoken_demo:
		_run_tiktoken_demo()
		return

	# --list 不需要初始化 LLM
	if args.list:
		list_profiles()
		return

	# --eval 不需要初始化 LLM（但需透传 few_shot / cot 开关）
	if args.eval:
		run_evaluation(args.profile, enable_few_shot=args.few_shot, enable_cot=args.cot)
		return

	cfg: Config = Config.from_yaml()

	# 初始化 LLM 客户端
	llm: LLMClient = LLMClient(
		api_key=cfg.llm.api_key_env,
		base_url=cfg.llm.base_url,
		model=cfg.llm.model,
		temperature=cfg.generation.temperature,
		top_p=cfg.generation.top_p,
		max_tokens=cfg.generation.max_tokens,
	)

	# 加载角色
	try:
		profile: dict[str, Any] = load_profile(args.profile)
	except FileNotFoundError:
		available: list[str] = sorted(
			p.stem for p in _get_profiles_dir().glob("*.yaml")
		)
		print(f"错误：角色文件不存在 — data/profiles/{args.profile}.yaml")
		if available:
			print(f"可用角色：{', '.join(available)}")
		else:
			print("没有找到任何角色文件。")
		sys.exit(1)

	# 初始化提示词管理器 + 构建 system prompt
	pm: PromptManager = PromptManager(_get_prompts_dir())
	system_prompt: str = pm.render(
		"profile.j2",
		profile=profile,
		user_name=cfg.profile.user_name_placeholder,
		enable_few_shot=args.few_shot,
		enable_cot=args.cot,
	)

	# 初始化记忆管理器（以角色名作为会话标识符，自动加载/落盘记忆）
	memory: ConversationMemory = ConversationMemory(
		storage_dir=_get_memories_dir(),
		session_id=args.profile,
		llm_client=llm,
		prompt_manager=pm,
		max_turns=cfg.memory.max_turns,
		max_tokens=cfg.memory.max_tokens,
	)

	# 初始化对话会话
	session: MemoryChatSession = MemoryChatSession(llm, system_prompt, memory)

	# 启动
	print("开始对话...\n")
	chat_loop(args.profile, session, show_memory_panel=args.memory_panel)


if __name__ == "__main__":
	main()
