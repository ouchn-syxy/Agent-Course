"""
实验 2：角色模拟智能体提示词设计 — 主入口

用法：
    python main.py                     # 默认：与鲁迅交互对话
    python main.py --profile luxun     # 显式指定角色
    python main.py --list              # 列出所有可用角色
    python main.py --eval              # 运行 LLM-as-Judge 评估
"""

import argparse
import sys
from pathlib import Path
from typing import Any

import yaml

from config import Config
from evaluator import run_evaluation
from llm.chat_session import ChatSession
from llm.client import LLMClient
from prompt.prompt_manager import PromptManager
from utils.path import get_prj_root

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


# ============================================================
# 命令行参数
# ============================================================

def parse_args() -> argparse.Namespace:
	"""解析命令行参数。"""
	parser: argparse.ArgumentParser = argparse.ArgumentParser(
		description="角色模拟智能体 — 提示词设计实验",
		formatter_class=argparse.RawDescriptionHelpFormatter,
		epilog="""
示例：
	python main.py                     # 交互式对话
	python main.py --profile luxun     # 指定角色
	python main.py --list              # 列出可用角色
	python main.py --eval              # 运行评估
		""",
	)
	parser.add_argument(
		"--profile", default=DEFAULT_PROFILE,
		help=f"角色名称（默认: {DEFAULT_PROFILE}）"
	)
	parser.add_argument(
		"--list", action="store_true",
		help="列出所有可用角色"
	)
	parser.add_argument(
		"--eval", action="store_true",
		help="运行 LLM-as-Judge 评估"
	)
	parser.add_argument(
		"--few-shot", action="store_true",
		help="启用 Few-shot 示例"
	)
	parser.add_argument(
		"--cot", action="store_true",
		help="启用 Chain-of-Thought 推理"
	)
	return parser.parse_args()


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

def chat_loop(profile_name: str, session: ChatSession) -> None:
	"""
	交互式对话循环。

	支持 /quit 退出、/reset 重置对话。
	"""

	print("=" * 60)
	print(f"  🎭 角色模拟智能体 — {profile_name}")
	print(f"  模型: {session.llm.info()}")
	print("=" * 60)
	print("  输入对话内容，按 Enter 发送。")
	print("  输入 /quit 退出，/reset 重置对话。")
	print("=" * 60)
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

		# 发送消息并显示回复
		print()
		try:
			reply: str = session.send(user_input)
			print(f"角色: {reply}\n")
		except Exception as e:
			print(f"[错误] {e}\n")


# ============================================================
# 主入口
# ============================================================


def main() -> None:
	"""程序入口。"""
	# Windows 终端默认编码可能为 GBK；不可编码的图标替换输出，保证命令不中断。
	if hasattr(sys.stdout, "reconfigure"):
		sys.stdout.reconfigure(errors="replace")
	args: argparse.Namespace = parse_args()

	# --list 模式不需要初始化 LLM
	if args.list:
		list_profiles()
		return

	# --eval 不需要初始化 LLM（但需透传 few_shot / cot 开关）
	if args.eval:
		run_evaluation(args.profile, enable_few_shot=args.few_shot, enable_cot=args.cot)
		return

	# 初始化 LLM 客户端
	cfg = Config.from_yaml()
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

	# 初始化对话会话
	session: ChatSession = ChatSession(llm, system_prompt)

	# 启动
	print("开始对话...\n")
	chat_loop(args.profile, session)


if __name__ == "__main__":
	main()
