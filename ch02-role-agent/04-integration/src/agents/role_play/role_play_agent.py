"""
角色模拟智能体统一入口（Facade）。

整合提示词工程、记忆机制、TTS 语音输出三大模块，
对外提供简洁的 chat() 接口。

用法:
    llm = LLMClient(...)
    agent = RolePlayAgent(profile_name="luxun", llm=llm, enable_memory=True)
    reply = agent.chat("先生，您当年为什么决定弃医从文？")
"""

from __future__ import annotations

import platform
import subprocess
from pathlib import Path

from inherit.agents.role_play.models.profile import Profile
from inherit.llm.chat_session import ChatSession
from inherit.llm.client import LLMClient
from inherit.llm.memory_chat_session import MemoryChatSession
from inherit.memory.conversation_memory import ConversationMemory
from inherit.prompt.prompt_manager import PromptManager
from inherit.utils.path import get_prj_root
from tts.client import TTSClient


# ============================================================
# RolePlayAgent
# ============================================================

class RolePlayAgent:
	"""角色模拟智能体 — 统一入口（Facade 模式）。

	组装提示词、记忆、TTS 等模块，对外暴露 chat() 方法。
	"""


	def __init__(
			self,
			profile_name: str,
			llm: LLMClient,
			enable_memory: bool = True,
			enable_cot: bool = True,
			enable_few_shot: bool = False,
			max_turns: int = 20,
			max_tokens: int = 3000,
			tts_client: TTSClient | None = None,
			tts_voice_ref_path: Path | None = None,
	) -> None:
		"""初始化角色模拟智能体。

		Args:
			profile_name: 角色名（对应 data/profiles/ 下的 YAML 文件名，不含扩展名）。
			llm: 预配置的大模型客户端。
			enable_memory: 是否启用短期 + 长期记忆。
			enable_cot: 是否在 system prompt 中注入 CoT 思考链引导。
			enable_few_shot: 是否在 system prompt 中注入 Few-shot 对话示例。
			max_turns: 记忆窗口最多保留的对话轮数（仅 enable_memory=True 时生效）。
			max_tokens: 触发摘要压缩的 token 阈值（仅 enable_memory=True 时生效）。
			tts_client: 预配置的 TTS 客户端，None 则不启用语音合成。
			tts_voice_ref_path: 音色克隆参考音频路径，None 则跳过合成。
		"""
		self._profile_name: str = profile_name
		self._enable_memory: bool = enable_memory
		self._enable_cot: bool = enable_cot
		self._enable_few_shot: bool = enable_few_shot
		self._max_turns: int = max_turns
		self._max_tokens: int = max_tokens

		# 1. 加载角色 Profile
		self._profile: Profile = self._load_profile(profile_name)

		# 2. 注入 LLM 客户端
		self._llm: LLMClient = llm

		# 3. 初始化提示词管理器
		self._pm: PromptManager = PromptManager(self._get_prompts_dir())

		# 4. 渲染 system prompt
		self._system_prompt: str = self._pm.render(
			"agents/role_play/role_play_agent/system.j2",
			profile=self._profile,
			user_name="来访者",
			enable_cot=self._enable_cot,
			enable_few_shot=self._enable_few_shot,
		)

		# 5. 创建对话会话（根据开关选择记忆 / 无记忆模式）
		self._session: ChatSession = self._create_session()

		# 6. 注入 TTS 客户端及参考音频
		if tts_client is not None and tts_voice_ref_path is None:
			raise ValueError("tts_voice_ref_path 不能为 None（已传入 tts_client）")
		self._tts: TTSClient | None = tts_client
		self._tts_voice_ref_path: Path | None = tts_voice_ref_path


	# ============================================================
	# 属性
	# ============================================================

	@property
	def profile_name(self) -> str:
		"""角色名称。"""
		return self._profile_name


	@property
	def memory(self) -> ConversationMemory | None:
		"""记忆管理器（仅 enable_memory=True 时可用）。"""
		if isinstance(self._session, MemoryChatSession):
			return self._session.memory
		return None


	@property
	def turn_count(self) -> int:
		"""当前对话轮数。"""
		if isinstance(self._session, MemoryChatSession):
			return self._session.memory.turn_count
		return self._session.turn_count


	# ============================================================
	# 核心方法
	# ============================================================

	def chat(self, user_input: str) -> str:
		"""发送消息并获取角色回复。

		Args:
			user_input: 用户输入的文本。

		Returns:
			角色回复的文本。
		"""
		reply: str = self._session.send(user_input)

		# TTS 语音输出（可选）
		if self._tts is not None:
			output_path: Path | None = self._synthesize_speech(reply)
			if output_path is not None:
				self._play_audio(output_path)

		return reply


	def reset(self) -> None:
		"""重置对话历史。"""
		self._session.reset()


	def visualize_memory(self) -> str | None:
		"""查看记忆面板（仅 enable_memory=True 时可用）。"""
		if isinstance(self._session, MemoryChatSession):
			return self._session.memory.visualize()
		return None


	# ============================================================
	# 内部方法
	# ============================================================

	def _load_profile(self, name: str) -> Profile:
		"""加载角色 YAML 并转换为 Profile。"""
		profile_path: Path = self._get_profiles_dir() / f"{name}.yaml"
		return Profile.from_yaml(profile_path)


	def _create_session(self) -> ChatSession:
		"""创建对话会话（记忆模式或普通模式）。"""
		if self._enable_memory:
			memory: ConversationMemory = ConversationMemory(
				storage_dir=self._get_memories_dir(),
				session_id=self._profile_name,
				llm_client=self._llm,
				prompt_manager=self._pm,
				max_turns=self._max_turns,
				max_tokens=self._max_tokens,
			)
			return MemoryChatSession(self._llm, self._system_prompt, memory)

		return ChatSession(self._llm, self._system_prompt)


	def _synthesize_speech(self, text: str) -> Path | None:
		"""将文本合成为语音文件并保存。返回输出路径，失败时返回 None。"""

		if self._tts is None:
			return None

		if self._tts_voice_ref_path is None:
			return None

		tts_voice_ref_path: Path = self._tts_voice_ref_path

		tts_output_dir: Path = self._get_tts_output_dir()
		tts_output_dir.mkdir(parents=True, exist_ok=True)
		output_path: Path = tts_output_dir / f"reply_{self.turn_count}.wav"

		try:
			self._tts.generate_single(
				output_path=output_path,
				text=text,
				voice_ref_path=tts_voice_ref_path,
			)
			print(f"[TTS] 语音已保存至 {output_path}")
			return output_path
		except Exception as e:
			print(f"[TTS] 语音合成失败: {e}")
			return None


	@staticmethod
	def _play_audio(filepath: Path) -> None:
		"""播放音频文件（macOS / Windows）。"""

		system = platform.system()
		if system == "Darwin":
			subprocess.run(["afplay", str(filepath)], check=False)
		elif system == "Windows":
			subprocess.run(
				["powershell", "-c", f"(New-Object Media.SoundPlayer '{filepath}').PlaySync()"],
				check=False,
			)


	# ============================================================
	# 路径常量
	# ============================================================

	@staticmethod
	def _get_profiles_dir() -> Path:
		"""角色 Profile 数据目录。"""
		return get_prj_root() / "data" / "profiles"


	@staticmethod
	def _get_prompts_dir() -> Path:
		"""提示词模板目录。"""
		return get_prj_root() / "prompts"


	@staticmethod
	def _get_memories_dir() -> Path:
		"""记忆持久化存储目录。"""
		return get_prj_root() / "data" / "memories"


	@staticmethod
	def _get_tts_output_dir() -> Path:
		"""语音输出目录。"""
		return get_prj_root() / "output" / "tts"


# ============================================================
# Demo
# ============================================================

if __name__ == "__main__":
	from config import Config

	cfg: Config = Config.from_yaml()
	llm = LLMClient(
		api_key=cfg.llm.api_key_env,
		base_url=cfg.llm.base_url,
		model=cfg.llm.model,
		temperature=cfg.generation.temperature,
		top_p=cfg.generation.top_p,
		max_tokens=cfg.generation.max_tokens,
	)

	# TTS 客户端（通过 --tts 启用，需配置 tts 节）
	tts: TTSClient | None = TTSClient(base_url=cfg.tts.base_url) if cfg.tts else None
	tts_voice_ref_path: Path | None = Path(cfg.tts.voice_ref_path) if cfg.tts else None
	agent = RolePlayAgent(
		profile_name="luxun", llm=llm, enable_memory=True,
		tts_client=tts, tts_voice_ref_path=tts_voice_ref_path
	)

	print(f"🎭 {agent.profile_name} — {llm.model}")
	print()

	reply = agent.chat("先生，您当年为什么决定弃医从文？")
	print(f"角色: {reply}")
	print()

	if agent.memory is not None:
		print(agent.visualize_memory())
